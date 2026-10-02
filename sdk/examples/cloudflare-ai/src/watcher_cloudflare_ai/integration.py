"""Import downloaded Cloudflare AI Gateway Logpush records through the public SDK.

The gateway exports completed requests. This importer decrypts bounded records,
converts complete textual Chat exchanges and submits transcripts. It cannot
intercept a response, enforce tool permissions or prove hosted Logpush delivery.
"""

import asyncio
import base64
import gzip
import hashlib
import os
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import typer
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel

from watcher_cloudflare_ai.chat import UnsupportedExchange, decode_json, exchange_messages
from watcher_sdk import AsyncWatcherClient

MAX_RECORD_BYTES = 1024 * 1024
MAX_RECORDS = 10000


class ImportReceipt(BaseModel):
    """Count accepted submissions; this is not a durable Watcher storage receipt."""

    submitted: int
    conversation_ids: list[str]


def private_key(path: Path) -> rsa.RSAPrivateKey:
    """Read a local RSA PEM key; the key is never sent to Watcher or printed."""
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("An RSA private key is required")
    return key


def decrypt_body(value: object, key: rsa.RSAPrivateKey) -> object:
    """Decode Cloudflare's RSA-OAEP-SHA256/AES-GCM envelope and authenticate its tag.

    Plaintext JSON strings/objects are also accepted for downloaded unencrypted
    records. A malformed encrypted envelope never falls back to plaintext.
    """
    if isinstance(value, dict) and "key" in value:
        envelope = cast(dict[str, object], value)
        wrapped_key = envelope.get("key")
        encoded_nonce = envelope.get("iv")
        encoded_data = envelope.get("data")
        if not isinstance(wrapped_key, str) or not isinstance(encoded_nonce, str) or not isinstance(encoded_data, str):
            raise ValueError("Incomplete encryption envelope")
        aes_key = key.decrypt(
            base64.b64decode(wrapped_key, validate=True),
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )
        if len(aes_key) != 32:
            raise ValueError("Expected an AES-256 key")
        nonce = base64.b64decode(encoded_nonce, validate=True)
        if len(nonce) != 12:
            raise ValueError("Expected a 96-bit GCM nonce")
        value = AESGCM(aes_key).decrypt(nonce, base64.b64decode(encoded_data, validate=True), None)
    if isinstance(value, (bytes, str)):
        return decode_json(value)
    if isinstance(value, dict):
        return value
    raise ValueError("Unsupported log body")


def records(path: Path) -> Iterator[bytes]:
    """Read bounded JSONL records from a plain or gzipped downloaded Logpush file."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as stream:
        for index in range(MAX_RECORDS + 1):
            line = stream.readline(MAX_RECORD_BYTES + 1)
            if not line:
                return
            if index == MAX_RECORDS:
                raise ValueError("Too many records; split this download before importing")
            if len(line) > MAX_RECORD_BYTES:
                raise ValueError("Log record exceeds the configured size limit")
            if line.strip():
                yield line


async def import_records(
    client: AsyncWatcherClient, path: Path, key: rsa.RSAPrivateKey, *, gateway_id: str, object_key: str
) -> ImportReceipt:
    """Submit each supported completed log as a separate transcript snapshot.

    ``gateway_id`` is an operator-chosen namespace, not a client-supplied session
    header. ``object_key`` is the original storage object's unique key. That key,
    record ordinal and content distinguish even identical plaintext requests.
    Re-importing the same object bytes reuses its identifiers. Import stops on
    the first failure; earlier submissions may
    already have been accepted and must be checked before retrying a file.
    """
    if not gateway_id.strip() or not object_key.strip():
        raise ValueError("A gateway namespace and storage object key are required")
    permission = await client.check_permissions(["sessions:ingest"])
    if permission.granted is not True or permission.missing:
        raise PermissionError("Watcher sessions:ingest permission is required")
    ids = []
    for ordinal, raw in enumerate(records(path)):
        record = decode_json(raw)
        if not isinstance(record, dict):
            raise ValueError("Log record must be a JSON object")
        request = decrypt_body(record["RequestBody"], key)
        response = decrypt_body(record["ResponseBody"], key)
        messages = exchange_messages(request, response)
        scope = "\0".join((gateway_id, object_key, str(ordinal))).encode()
        identity = "cloudflare:" + hashlib.sha256(scope + b"\0" + raw).hexdigest()
        outcome = await client.pre_tool_use_hook(messages=messages, external_ids={"other": identity})
        if outcome != []:
            raise UnsupportedExchange("Unexpected transcript submission response")
        ids.append(identity)
    return ImportReceipt(submitted=len(ids), conversation_ids=ids)


app = typer.Typer(invoke_without_command=True, no_args_is_help=True, pretty_exceptions_enable=False)


@app.command("import-file")
def import_command(path: Path, private_key_file: Path, gateway_id: str, object_key: str) -> None:
    """Import a downloaded Logpush file; print identifiers without transcript content."""

    async def run() -> ImportReceipt:
        async with AsyncWatcherClient(os.environ["WATCHER_BASE_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
            return await import_records(
                client, path, private_key(private_key_file), gateway_id=gateway_id, object_key=object_key
            )

    typer.echo(asyncio.run(run()).model_dump_json(indent=2))


@app.command("help", hidden=True)
def help_command(context: typer.Context) -> None:
    """Show the importer command help."""
    typer.echo(context.parent.get_help() if context.parent else context.get_help())


def main() -> None:
    """Run the local-file importer without modifying gateway configuration."""
    app()
