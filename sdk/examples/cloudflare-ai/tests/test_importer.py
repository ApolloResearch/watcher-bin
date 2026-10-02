"""Verify encrypted export import, content fidelity and public-SDK submissions."""

import base64
import gzip
import json
import os

import httpx
import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from watcher_cloudflare_ai.integration import decrypt_body, import_records, records

from watcher_sdk import AsyncWatcherClient


@pytest.fixture(scope="module")
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def encrypted(value, key):
    aes_key, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
    ciphertext = AESGCM(aes_key).encrypt(nonce, json.dumps(value).encode(), None)
    wrapped = key.public_key().encrypt(
        aes_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    return {
        name: base64.b64encode(value).decode()
        for name, value in (("key", wrapped), ("iv", nonce), ("data", ciphertext))
    }


def exchange():
    request = {
        "model": "fixture",
        "messages": [
            {"role": "user", "content": "Read the fixture"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-native",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"count":0,"ratio":1.0,"enabled":false,"empty":null}',
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-native", "content": "actual fixture result"},
        ],
    }
    response = {
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Finished"}}]
    }
    return {"RequestBody": request, "ResponseBody": response}


@pytest.mark.parametrize("compressed", [False, True])
async def test_decrypted_history_and_tail_reach_public_hook(tmp_path, key, compressed):
    record = {name: encrypted(value, key) for name, value in exchange().items()}
    raw = (json.dumps(record) + "\n").encode()
    path = tmp_path / ("logs.jsonl.gz" if compressed else "logs.jsonl")
    path.write_bytes(gzip.compress(raw) if compressed else raw)
    seen = []

    def handler(request):
        if request.url.path == "/v1/auth/check-permissions":
            return httpx.Response(200, json={"granted": True, "missing": []})
        body = json.loads(request.content)
        seen.append(body)
        assert body.get("input") is None
        assert body.get("settings_overrides") is None
        assert body["messages"][-1]["content"] == "Finished"
        call = body["messages"][1]["tool_calls"][0]
        assert call["id"] == "call-native" and call["function"] == "read_file"
        assert type(call["arguments"]["count"]) is int
        assert type(call["arguments"]["ratio"]) is float
        assert call["arguments"]["enabled"] is False and call["arguments"]["empty"] is None
        assert body["messages"][2]["tool_call_id"] == "call-native"
        return httpx.Response(200, json=[])

    async with AsyncWatcherClient(
        "http://fixture",
        httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(handler)),
    ) as client:
        receipt = await import_records(client, path, key, gateway_id="gateway-a", object_key="exports/object-1")
    assert receipt.submitted == 1 and receipt.conversation_ids == [seen[0]["external_ids"]["other"]]


async def test_identical_records_are_separate_and_retry_identity_is_stable(tmp_path, key):
    path = tmp_path / "logs.jsonl"
    line = json.dumps(exchange()) + "\n"
    path.write_text(line + line)

    def handler(request):
        return httpx.Response(
            200, json={"granted": True, "missing": []} if request.url.path.endswith("check-permissions") else []
        )

    async with AsyncWatcherClient(
        "http://fixture",
        httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(handler)),
    ) as client:
        first = await import_records(client, path, key, gateway_id="gateway-a", object_key="object-1")
        again = await import_records(client, path, key, gateway_id="gateway-a", object_key="object-1")
        other = await import_records(client, path, key, gateway_id="gateway-a", object_key="object-2")
    assert len(set(first.conversation_ids)) == 2
    assert first.conversation_ids == again.conversation_ids
    assert set(first.conversation_ids).isdisjoint(other.conversation_ids)


def test_tampered_ciphertext_cannot_be_imported(key):
    value = encrypted({"sensitive": "fixture"}, key)
    data = bytearray(base64.b64decode(value["data"]))
    data[-1] ^= 1
    value["data"] = base64.b64encode(data).decode()
    with pytest.raises(InvalidTag):
        decrypt_body(value, key)


def test_wrong_rsa_key_fails(key):
    value = encrypted({"fixture": True}, key)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(ValueError):
        decrypt_body(value, other)


@pytest.mark.parametrize("value", [{"key": "invalid"}, {"key": 1, "data": "", "iv": ""}, [], None, 1])
def test_invalid_envelope_does_not_fall_back_to_plaintext(value, key):
    with pytest.raises(ValueError):
        decrypt_body(value, key)


@pytest.mark.parametrize("compressed", [False, True])
def test_record_limit_applies_after_decompression(tmp_path, compressed):
    path = tmp_path / ("oversize.gz" if compressed else "oversize.jsonl")
    content = b"x" * (1024 * 1024 + 1)
    path.write_bytes(gzip.compress(content) if compressed else content)
    with pytest.raises(ValueError, match="size limit"):
        list(records(path))


async def test_permission_failure_sends_no_transcript(tmp_path, key):
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={"granted": False, "missing": ["sessions:ingest"]})

    async with AsyncWatcherClient(
        "http://fixture",
        httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(handler)),
    ) as client:
        with pytest.raises(PermissionError):
            await import_records(client, tmp_path / "unused", key, gateway_id="g", object_key="o")
    assert seen == ["/v1/auth/check-permissions"]


async def test_incomplete_response_is_not_claimed_as_full_transcript(tmp_path, key):
    record = exchange()
    record["ResponseBody"]["choices"][0]["finish_reason"] = "length"
    path = tmp_path / "partial.jsonl"
    path.write_text(json.dumps(record))

    def handler(request):
        assert request.url.path.endswith("check-permissions")
        return httpx.Response(200, json={"granted": True, "missing": []})

    async with AsyncWatcherClient(
        "http://fixture",
        httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(handler)),
    ) as client:
        with pytest.raises(ValueError, match="incomplete"):
            await import_records(client, path, key, gateway_id="g", object_key="o")
