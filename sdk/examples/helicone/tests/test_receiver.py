"""Verify Helicone event authentication, complete-body retrieval and SDK ingestion."""

import hashlib
import hmac
import json
from unittest.mock import create_autospec
from uuid import uuid4

import httpx
import pytest
from watcher_helicone.conversion import UnsupportedExchange
from watcher_helicone.receiver import TRUNCATED_BODY, fetch_bodies, ingest_webhook, verify_signature

from watcher_sdk import AsyncWatcherClient

SECRET = "local-fixture-webhook-secret"


def sign(body):
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def event():
    return {
        "request_id": str(uuid4()),
        "request_body": {"model": "fixture", "messages": [{"role": "user", "content": "Local café transcript"}]},
        "response_body": {
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "native-call",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": '{"flag":true,"integer":1,"fraction":1.0,"empty":null}',
                                },
                            }
                        ],
                    },
                }
            ]
        },
    }


@pytest.mark.parametrize("request_string,response_string", [(False, False), (False, True), (True, False), (True, True)])
async def test_authentic_object_and_string_bodies_record_without_retrospective_decisions(
    event, request_string, response_string
):
    original = dict(event)
    if request_string:
        event["request_body"] = json.dumps(event["request_body"])
    if response_string:
        event["response_body"] = json.dumps(event["response_body"])
    body = json.dumps(event, ensure_ascii=False).encode()
    captured = []

    def sdk(request):
        payload = json.loads(request.content)
        captured.append(payload)
        assert payload.get("input") is None and payload.get("settings_overrides") is None
        assert payload["external_ids"] == {"other": "helicone:" + event["request_id"]}
        call = payload["messages"][-1]["tool_calls"][0]
        assert call["id"] == "native-call"
        assert type(call["arguments"]["integer"]) is int
        assert type(call["arguments"]["fraction"]) is float
        assert type(call["arguments"]["flag"]) is bool
        return httpx.Response(200, json=[])

    async with (
        AsyncWatcherClient(
            "http://watcher.invalid",
            httpx_client=httpx.AsyncClient(base_url="http://watcher.invalid", transport=httpx.MockTransport(sdk)),
        ) as watcher,
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: pytest.fail("Inline bodies must not fetch storage"))
        ) as storage,
    ):
        assert (
            await ingest_webhook(watcher, body, sign(body), secret=SECRET, storage_client=storage)
            == "helicone:" + original["request_id"]
        )
        assert (
            await ingest_webhook(watcher, body, sign(body), secret=SECRET, storage_client=storage)
            == "helicone:" + original["request_id"]
        )
    assert len(captured) == 2 and captured[0] == captured[1]


@pytest.mark.parametrize("signature", ["", "bad", "0" * 64])
async def test_invalid_signature_cannot_fetch_or_ingest(event, signature):
    body = json.dumps(event).encode()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: pytest.fail("Unauthenticated network fetch"))
    ) as storage:
        with pytest.raises(PermissionError):
            await ingest_webhook(
                create_autospec(AsyncWatcherClient, instance=True),
                body,
                signature,
                secret=SECRET,
                storage_client=storage,
            )


def test_signature_checks_raw_bytes_not_reserialized_json(event):
    compact = json.dumps(event, separators=(",", ":")).encode()
    pretty = json.dumps(event, indent=2).encode()
    with pytest.raises(PermissionError):
        verify_signature(pretty, sign(compact), SECRET)
    verify_signature(compact, sign(compact), SECRET)


@pytest.mark.parametrize("string_bodies", [False, True])
async def test_truncated_inline_body_fetches_allowlisted_complete_object_without_credentials(event, string_bodies):
    stored = {"request": event["request_body"], "response": event["response_body"]}
    if string_bodies:
        stored = {key: json.dumps(value) for key, value in stored.items()}
    event["request_body"] = TRUNCATED_BODY
    event["request_response_url"] = "https://storage.invalid/body?signature=fixture"
    fetches = []

    def storage_reply(request):
        fetches.append(request)
        assert "Authorization" not in request.headers and "Cookie" not in request.headers
        assert request.headers["Accept-Encoding"] == "identity"
        return httpx.Response(200, json=stored)

    body = json.dumps(event).encode()
    async with (
        AsyncWatcherClient(
            "http://watcher.invalid",
            httpx_client=httpx.AsyncClient(
                base_url="http://watcher.invalid", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[]))
            ),
        ) as watcher,
        httpx.AsyncClient(
            transport=httpx.MockTransport(storage_reply),
            headers={"Authorization": "must-not-leak"},
            cookies={"session": "must-not-leak"},
            auth=("must-not", "leak"),
        ) as storage,
    ):
        await ingest_webhook(
            watcher,
            body,
            sign(body),
            secret=SECRET,
            body_origins=("https://storage.invalid",),
            storage_client=storage,
        )
    assert len(fetches) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://other.invalid/body",
        "https://storage.invalid.evil/body",
        "https://secret@storage.invalid/body",
        "https://:@storage.invalid/body",
        "file:///etc/passwd",
    ],
)
async def test_full_body_origin_rejects_other_hosts_credentials_and_schemes(url):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: pytest.fail("Rejected URL fetched"))
    ) as storage:
        with pytest.raises((PermissionError, UnsupportedExchange)):
            await fetch_bodies(url, origins=("https://storage.invalid",), client=storage)


async def test_caller_enabled_redirects_do_not_forward_to_another_origin():
    calls = []

    def reply(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://other.invalid/body"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(reply), follow_redirects=True) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_bodies("https://storage.invalid/body", origins=("https://storage.invalid",), client=client)
    assert calls == ["https://storage.invalid/body"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, headers={"Content-Length": str(9 * 1024 * 1024)}, content=b"{}"),
        httpx.Response(200, headers={"Content-Encoding": "br"}, content=b""),
        httpx.Response(404, content=b"missing"),
    ],
)
async def test_full_body_failure_never_becomes_partial_success(response):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response)) as client:
        with pytest.raises((UnsupportedExchange, httpx.HTTPError)):
            await fetch_bodies("https://storage.invalid/body", origins=("https://storage.invalid",), client=client)


@pytest.mark.parametrize(
    "field,value",
    [("request_id", "not-a-uuid"), ("request_body", {"model": "fixture"}), ("response_body", {"choices": []})],
)
async def test_missing_identity_privacy_omission_or_incomplete_payload_cannot_ingest(event, field, value):
    event[field] = value
    body = json.dumps(event).encode()
    async with httpx.AsyncClient() as storage:
        with pytest.raises((ValueError, UnsupportedExchange)):
            await ingest_webhook(
                create_autospec(AsyncWatcherClient, instance=True),
                body,
                sign(body),
                secret=SECRET,
                storage_client=storage,
            )
