"""Receive authenticated Helicone completion webhooks and ingest full transcripts.

The platform has already delivered these responses to its clients. This receiver
therefore submits transcript-only hook requests: it neither claims prevention nor
creates retrospective applied tool decisions. Each Helicone request ID identifies
one snapshot. HMAC verification precedes parsing or any optional full-body fetch.
"""

import asyncio
import hashlib
import hmac
import json
import os
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import typer

from watcher_helicone.conversion import UnsupportedExchange, _message, _validate_ids, decode_json, validate_request
from watcher_sdk import AsyncWatcherClient

MAX_BODY = 8 * 1024 * 1024
TRUNCATED_BODY = "Body too large for webhook, please fetch the full request and response from Helicone"


def verify_signature(body: bytes, signature: str, secret: str) -> None:
    """Verify Helicone's SHA-256 HMAC over exact bytes, without JSON normalization."""
    if not secret or len(signature) != 64:
        raise PermissionError("Invalid webhook signature")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise PermissionError("Invalid webhook signature")


def _body(value: Any) -> dict:
    """Decode a Helicone processed body, which can be an object or a JSON string."""
    if isinstance(value, str):
        value = decode_json(value)
    if not isinstance(value, dict):
        raise UnsupportedExchange("Complete request and response objects are required")
    return value


def _origin(value: str) -> tuple[str, str, int]:
    """Normalize an explicit storage origin; URL credentials never belong in it."""
    parsed = urlsplit(value)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise UnsupportedExchange("Invalid full-body origin")
    return parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == "https" else 80)


async def fetch_bodies(url: str, *, origins: tuple[str, ...], client: httpx.AsyncClient) -> tuple[dict, dict]:
    """Fetch one bounded object from an explicitly allowed origin, without redirects.

    Signed URLs are credentials. No webhook secret or Watcher key is forwarded to
    storage, and failure never falls back to truncated inline data. Operators may
    allow a plain-HTTP origin for an isolated local storage service explicitly.
    """
    if len(url) > 16384 or urlsplit(url).fragment:
        raise UnsupportedExchange("Invalid full-body URL")
    if _origin(url) not in {_origin(origin) for origin in origins}:
        raise PermissionError("Full-body origin is not allowed")
    request = httpx.Request("GET", url, headers={"Accept": "application/json", "Accept-Encoding": "identity"})
    response = await client.send(request, stream=True, follow_redirects=False, auth=None)
    try:
        response.raise_for_status()
        if response.headers.get("Content-Encoding", "identity").lower() != "identity":
            raise UnsupportedExchange("Compressed full-body objects are unsupported")
        if int(response.headers.get("Content-Length", "0")) > MAX_BODY:
            raise UnsupportedExchange("Full-body object exceeds the size limit")
        body = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=65536):
            body.extend(chunk)
            if len(body) > MAX_BODY:
                raise UnsupportedExchange("Full-body object exceeds the size limit")
    finally:
        await response.aclose()
    payload = decode_json(bytes(body))
    if not isinstance(payload, dict):
        raise UnsupportedExchange("Invalid full-body envelope")
    return _body(payload.get("request")), _body(payload.get("response"))


async def ingest_webhook(
    watcher: AsyncWatcherClient,
    body: bytes,
    signature: str,
    *,
    secret: str,
    body_origins: tuple[str, ...] = (),
    storage_client: httpx.AsyncClient,
) -> str:
    """Verify one event and submit its complete Chat Completions transcript.

    Unsupported provider formats, missing content, incomplete responses, invalid
    signatures and unavailable full-body objects fail without submitting a partial
    transcript. Returns the namespaced logged request ID after the SDK hook reply;
    that reply is not a durable storage acknowledgement. Re-delivery uses the same
    external ID, while unrelated logged requests remain separate snapshots.
    """
    if not 0 < len(body) <= MAX_BODY:
        raise UnsupportedExchange("Invalid webhook body size")
    verify_signature(body, signature, secret)
    event = decode_json(body)
    if not isinstance(event, dict) or not isinstance(event.get("request_id"), str):
        raise UnsupportedExchange("Missing logged request ID")
    identifier = str(UUID(event["request_id"]))
    inline_request, inline_response = event.get("request_body"), event.get("response_body")
    if (
        inline_request is None
        or inline_response is None
        or inline_request == TRUNCATED_BODY
        or inline_response == TRUNCATED_BODY
    ):
        url = event.get("request_response_url")
        if not isinstance(url, str):
            raise UnsupportedExchange("Complete inline bodies or a full-body URL are required")
        request, response = await fetch_bodies(url, origins=body_origins, client=storage_client)
    else:
        request, response = _body(inline_request), _body(inline_response)
    messages = validate_request(request, allow_stream=True)
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise UnsupportedExchange("One complete Chat Completions choice is required")
    choice = choices[0]
    message = _message(choice.get("message"))
    expected_finish = "tool_calls" if message.get("tool_calls") else "stop"
    if (
        message["role"] != "assistant"
        or choice.get("finish_reason") != expected_finish
        or type(choice.get("index")) is not int
        or choice["index"] != 0
    ):
        raise UnsupportedExchange("The completion is incomplete or unsupported")
    messages.append(message)
    _validate_ids(messages)
    conversation_id = "helicone:" + identifier
    result = await watcher.pre_tool_use_hook(messages=messages, external_ids={"other": conversation_id}, timeout=60)
    if result != []:
        raise UnsupportedExchange("Unexpected transcript-only hook result")
    return conversation_id


def serve(host: str, port: int, origins: tuple[str, ...], certfile: str | None, keyfile: str | None) -> None:
    """Start the receiver behind TLS, requiring an ingest-capable Watcher key.

    Use a TLS reverse proxy or supply a certificate/key pair. Configuration comes
    from HELICONE_WEBHOOK_SECRET, WATCHER_BASE_URL and WATCHER_API_KEY. Storage
    origins are exact scheme/host/port allowlist entries, never wildcard hosts.
    """
    secret = os.environ["HELICONE_WEBHOOK_SECRET"]
    if not secret:
        raise ValueError("HELICONE_WEBHOOK_SECRET cannot be empty")
    api_url, api_key = os.environ["WATCHER_BASE_URL"], os.environ["WATCHER_API_KEY"]
    for origin in origins:
        parsed = urlsplit(origin)
        _origin(origin)
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("Storage allowlist values must be origins only")

    async def check_permission() -> None:
        async with AsyncWatcherClient(api_url, api_key=api_key) as watcher:
            result = await watcher.check_permissions(["sessions:ingest"])
            if result.granted is not True or result.missing:
                raise PermissionError("Watcher credential requires sessions:ingest")

    asyncio.run(check_permission())

    class Handler(BaseHTTPRequestHandler):
        """Authenticate bounded events without logging content or signed URLs."""

        def log_message(self, format: str, *_args: Any) -> None:
            pass

        def do_POST(self) -> None:
            if self.path != "/webhook":
                self._reply(404, {"accepted": False})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY or self.headers.get("Transfer-Encoding"):
                    raise UnsupportedExchange("Invalid webhook body size")
                signatures = self.headers.get_all("Helicone-Signature", [])
                if len(signatures) != 1:
                    raise PermissionError("One webhook signature is required")
                self.connection.settimeout(30)
                body = self.rfile.read(length)
                if len(body) != length:
                    raise UnsupportedExchange("Incomplete webhook body")

                async def receive() -> str:
                    async with (
                        AsyncWatcherClient(api_url, api_key=api_key) as watcher,
                        httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as storage,
                    ):
                        return await ingest_webhook(
                            watcher,
                            body,
                            signatures[0],
                            secret=secret,
                            body_origins=origins,
                            storage_client=storage,
                        )

                conversation_id = asyncio.run(receive())
                self._reply(200, {"accepted": True, "conversation_id": conversation_id})
            except PermissionError:
                self._reply(401, {"accepted": False, "error": "Event authentication or storage origin rejected"})
            except (ValueError, TypeError, KeyError):
                self._reply(422, {"accepted": False, "error": "Unsupported or incomplete event"})
            except Exception:
                self._reply(503, {"accepted": False, "error": "Ingestion did not complete"})

        def _reply(self, status: int, payload: dict) -> None:
            encoded = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer((host, port), Handler)
    if bool(certfile) != bool(keyfile):
        raise ValueError("Both certificate and private key are required")
    if certfile and keyfile:
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(certfile, keyfile)
        server.socket = tls.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


app = typer.Typer(invoke_without_command=True, no_args_is_help=True, pretty_exceptions_enable=False)


@app.command("serve")
def serve_command(
    host: str = "127.0.0.1",
    port: int = 8766,
    body_origin: list[str] | None = None,
    certfile: str | None = None,
    keyfile: str | None = None,
) -> None:
    """Receive Helicone completion events; repeat --body-origin for trusted stores."""
    serve(host, port, tuple(body_origin or []), certfile, keyfile)


@app.command("help", hidden=True)
def help_command(context: typer.Context) -> None:
    typer.echo(context.parent.get_help() if context.parent else context.get_help())


def main() -> None:
    """Run the authenticated observation receiver CLI."""
    app()


if __name__ == "__main__":
    main()
