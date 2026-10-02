"""Synthetic documented Compliance responses and real public SDK serialization."""

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from watcher_claude_compliance import ComplianceClient, ComplianceError, convert_messages, import_conversation

from watcher_sdk import AsyncWatcherClient, WatcherAPIError


def raw_message(identity="m1", role="user", content=None, **extras):
    return {
        "id": identity,
        "role": role,
        "created_at": "2026-07-01T09:00:00Z",
        "content": [{"type": "text", "text": "Inspect the test file", "truncated": False}]
        if content is None
        else content,
        **extras,
    }


def transcript():
    return [
        raw_message(),
        raw_message(
            "m2",
            "assistant",
            [
                {"type": "text", "text": "Reading"},
                {
                    "type": "tool_use",
                    "id": "call-1",
                    "name": "Read",
                    "input": '{"zero":0,"enabled":false}',
                    "truncated": False,
                },
                {"type": "tool_use", "id": "call-2", "name": "Read", "input": "{}", "truncated": False},
            ],
        ),
        raw_message(
            "m3",
            "user",
            [
                {
                    "type": "tool_result",
                    "tool_use_id": "call-2",
                    "name": "Read",
                    "is_error": True,
                    "content": [{"type": "text", "text": "Missing"}],
                },
                {
                    "type": "tool_result",
                    "tool_use_id": "call-1",
                    "name": "Read",
                    "is_error": False,
                    "content": [{"type": "text", "text": "Contents"}],
                },
            ],
        ),
        raw_message("m4", "assistant", [{"type": "text", "text": "Finished"}]),
    ]


def page(family="local", messages=None, cursor=None, identity="conversation", org="org"):
    envelope = {"id": identity, "organization_uuid": org}
    messages = transcript() if messages is None else messages
    if family == "chats":
        return {**envelope, "chat_messages": messages, "has_more": cursor is not None, "last_id": cursor}
    return {"session": envelope, "data": messages, "next_page": cursor}


@pytest.mark.parametrize("family", ["chats", "local", "remote"])
async def test_real_http_source_to_public_sdk(http_fixture, tmp_path, family):
    source_requests = []
    watcher_requests = []

    def source_handler(method, path, headers, body):
        source_requests.append(path)
        assert method == "GET" and body == b""
        query = parse_qs(urlsplit(path).query)
        assert query["order"] == ["asc"]
        suffix = "chars" if family == "chats" else "bytes"
        assert query[f"tool_use_input_max_{suffix}"] == ["-1"]
        key = "after_id" if family == "chats" else "page"
        first = key not in query
        data = transcript()[:2] if first else transcript()[2:]
        return 200, {"Content-Type": "application/json"}, page(family, data, "next" if first else None)

    def watcher_handler(method, path, headers, body):
        watcher_requests.append(json.loads(body))
        assert method == "POST" and urlsplit(path).path.endswith("/hooks/pre-tool-use")
        assert not urlsplit(path).query
        return 200, {"Content-Type": "application/json"}, []

    async with (
        http_fixture(source_handler) as source_url,
        http_fixture(watcher_handler) as watcher_url,
        httpx.AsyncClient(base_url=source_url, trust_env=False) as source_http,
        AsyncWatcherClient(watcher_url, max_retries=0) as watcher,
    ):
        receipt = await import_conversation(
            ComplianceClient(source_http),
            watcher,
            family=family,
            conversation_id="conversation",
            receipt_path=tmp_path / "receipt.json",
        )
    assert len(source_requests) == 2
    body = watcher_requests[0]
    assert body["input"] == [] and "settings_overrides" not in body
    assert body["external_ids"] == {"other": f"claude-compliance:{family}:org:conversation"}
    messages = body["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "assistant", "assistant", "tool", "tool", "assistant"]
    assert messages[2]["tool_calls"][0]["arguments"] == {"zero": 0, "enabled": False}
    assert type(messages[2]["tool_calls"][0]["arguments"]["zero"]) is int
    assert type(messages[2]["tool_calls"][0]["arguments"]["enabled"]) is bool
    assert messages[4]["tool_call_id"] == "call-2" and messages[4]["error"]["type"] == "unknown"
    assert messages[-1]["content"] == "Finished"
    assert messages[0]["metadata"]["compliance"]["created_at"] == "2026-07-01T09:00:00+00:00"
    assert "timestamp" not in messages[0]
    saved = json.loads((tmp_path / "receipt.json").read_text())
    assert saved["source_digest"] == receipt.source_digest
    assert saved["schema_version"] == 2
    assert saved["status"] == "submitted"
    assert "submitted_at" in saved and "imported_at" not in saved
    assert len(watcher_requests) == 1


async def fetch_pages(pages, *, family="local", max_pages=1000):
    requests = []

    def handler(request):
        requests.append(request)
        value = pages[min(len(requests) - 1, len(pages) - 1)]
        return httpx.Response(200, json=value)

    async with httpx.AsyncClient(base_url="https://source.test", transport=httpx.MockTransport(handler)) as client:
        result = await ComplianceClient(client, max_pages=max_pages).fetch(family, "conversation")
    return result


@pytest.mark.parametrize("family", ["chats", "local", "remote"])
async def test_short_and_empty_pages_continue_and_exact_duplicates_deduplicate(family):
    result = await fetch_pages(
        [page(family, [], "a"), page(family, [raw_message()], "b"), page(family, [raw_message(), raw_message("m2")])],
        family=family,
    )
    assert len(result.messages) == 2


@pytest.mark.parametrize("mutation", ["cursor", "message", "org", "id", "maximum", "missing-continuation"])
async def test_broken_page_walk_fails_before_import(mutation):
    pages = [page(messages=[raw_message()], cursor="a"), page(messages=[raw_message("m2")])]
    maximum = 1000
    if mutation == "cursor":
        pages[1]["next_page"] = "a"
    elif mutation == "message":
        pages[1]["data"] = [raw_message(content=[{"type": "text", "text": "changed"}])]
    elif mutation == "org":
        pages[1]["session"]["organization_uuid"] = "another"
    elif mutation == "id":
        pages[1]["session"]["id"] = "another"
    elif mutation == "maximum":
        maximum = 1
    else:
        pages[1]["next_page"] = ""
    with pytest.raises(ComplianceError):
        await fetch_pages(pages, max_pages=maximum)


def test_retains_unavailable_provenance_text_truncation_and_attachments():
    source = [
        raw_message(
            content=[{"type": "text", "text": "[system prompt content not shown]", "truncated": True}],
            provenance={"type": "synthetic_marker"},
        ),
        raw_message("m2", "assistant", [], provenance={"type": "content_unavailable", "reason": "not_captured"}),
        raw_message(
            "m3",
            "assistant",
            [{"type": "text", "text": "Visible", "thinking_redacted": True}],
            artifacts=[{"id": "artifact"}],
        ),
    ]
    original = deepcopy(source)
    converted = convert_messages(source, family="local")
    assert source == original
    assert converted.messages[1]["content"] == "[Transcript content unavailable]"
    message_metadata = converted.messages[0]["metadata"]
    assert isinstance(message_metadata, dict)
    compliance_metadata = message_metadata["compliance"]
    assert isinstance(compliance_metadata, dict)
    assert compliance_metadata["truncated"] is True
    assert len(converted.limitations) == 4


async def test_session_level_truncation_remains_explicit():
    response = page()
    response["session"]["truncated"] = True
    result = await fetch_pages([response])
    assert any("truncated session" in text for text in result.limitations)


@pytest.mark.parametrize("deleted_page", [0, 1])
async def test_deleted_chat_is_refused_before_watcher_or_receipt_update(tmp_path, deleted_page):
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text("previous receipt")
    source_requests = []

    def source_handler(request):
        source_requests.append(request)
        current = len(source_requests) - 1
        response = page("chats", [raw_message(content=[])], "next" if current < deleted_page else None)
        response["deleted_at"] = "2026-07-01T10:00:00Z" if current == deleted_page else None
        return httpx.Response(200, json=response)

    def watcher_handler(request):
        pytest.fail("A deleted chat must not be sent to Watcher")

    async with (
        httpx.AsyncClient(base_url="https://source.test", transport=httpx.MockTransport(source_handler)) as source_http,
        AsyncWatcherClient(
            "https://watcher.test",
            httpx_client=httpx.AsyncClient(
                base_url="https://watcher.test", transport=httpx.MockTransport(watcher_handler)
            ),
        ) as watcher,
    ):
        with pytest.raises(ComplianceError, match="chat was deleted"):
            await import_conversation(
                ComplianceClient(source_http),
                watcher,
                family="chats",
                conversation_id="conversation",
                receipt_path=receipt_path,
            )
    assert len(source_requests) == deleted_page + 1
    assert receipt_path.read_text() == "previous receipt"


def test_contentless_message_without_availability_marker_is_explicit():
    result = convert_messages([raw_message(content=[], provenance=None)], family="local")
    assert result.messages[0]["content"] == "[Source message has no content]"
    assert any("no content and no availability marker" in limit for limit in result.limitations)
    message_metadata = result.messages[0]["metadata"]
    assert isinstance(message_metadata, dict)
    compliance_metadata = message_metadata["compliance"]
    assert isinstance(compliance_metadata, dict)
    assert compliance_metadata["content_empty"] is True
    assert compliance_metadata["content_unavailable"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "null-call",
        "null-result",
        "truncated-input",
        "bad-json",
        "duplicate-json",
        "nonfinite",
        "overflow",
        "user-call",
        "unknown",
        "orphan",
        "duplicate-call",
        "duplicate-result",
        "nontext-result",
        "naive-time",
        "unavailable-content",
    ],
)
def test_unsupported_or_ambiguous_content_is_not_repaired(mutation):
    raw = transcript()
    call = raw[1]["content"][1]
    result = raw[2]["content"][0]
    if mutation == "null-call":
        call["id"] = None
    elif mutation == "null-result":
        result["tool_use_id"] = None
    elif mutation == "truncated-input":
        call["truncated"] = True
    elif mutation == "bad-json":
        call["input"] = "{"
    elif mutation == "duplicate-json":
        call["input"] = '{"x":1,"x":2}'
    elif mutation == "nonfinite":
        call["input"] = '{"x":NaN}'
    elif mutation == "overflow":
        call["input"] = '{"x":1e999}'
    elif mutation == "user-call":
        raw[1]["role"] = "user"
    elif mutation == "unknown":
        raw[0]["content"] = [{"type": "image", "url": "private"}]
    elif mutation == "orphan":
        result["tool_use_id"] = "missing"
    elif mutation == "duplicate-call":
        raw[1]["content"][2]["id"] = "call-1"
    elif mutation == "duplicate-result":
        raw[2]["content"][1]["tool_use_id"] = "call-2"
    elif mutation == "nontext-result":
        result["content"] = [{"type": "image"}]
    elif mutation == "naive-time":
        raw[0]["created_at"] = "2026-07-01T09:00:00"
    else:
        raw[0]["content_unavailable"] = True
    with pytest.raises(ComplianceError):
        convert_messages(raw, family="local")


@pytest.mark.parametrize(
    "status,retry_header,retries",
    [
        (401, None, 1),
        (403, None, 1),
        (404, None, 1),
        (400, None, 1),
        (429, None, 3),
        (500, None, 3),
        (500, "false", 1),
        (503, None, 3),
        (529, None, 3),
        (529, "false", 1),
        (302, None, 1),
    ],
)
async def test_http_status_retry_budget(status, retry_header, retries):
    requests = []

    def handler(request):
        requests.append(request)
        headers = {"Retry-After": "0", "Location": "https://outside.test"}
        if retry_header is not None:
            headers["x-should-retry"] = retry_header
        return httpx.Response(status, headers=headers)

    async with httpx.AsyncClient(base_url="https://source.test", transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(httpx.HTTPStatusError):
            await ComplianceClient(http).fetch("local", "conversation")
    assert len(requests) == retries


async def test_transient_backoff_starts_at_one_second(monkeypatch):
    delays = []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    async with httpx.AsyncClient(
        base_url="https://source.test", transport=httpx.MockTransport(lambda request: httpx.Response(529))
    ) as http:
        with pytest.raises(httpx.HTTPStatusError):
            await ComplianceClient(http).fetch("local", "conversation")
    assert delays == [1.0, 2.0]


async def test_replay_http_rejection_preserves_receipt_and_is_not_retried(tmp_path):
    receipt_path = tmp_path / "receipt.json"
    sent = []

    def source_handler(request):
        history = transcript()
        if sent:
            history[1]["content"][1]["input"] = '{"zero":1,"enabled":false}'
        return httpx.Response(200, json=page(messages=history))

    def watcher_handler(request):
        sent.append(json.loads(request.content))
        if len(sent) == 1:
            return httpx.Response(200, json=[])
        return httpx.Response(
            403,
            json={
                "detail": {
                    "code": "permission_denied",
                    "message": "Session ingestion permission is required",
                }
            },
        )

    async with (
        httpx.AsyncClient(base_url="https://source.test", transport=httpx.MockTransport(source_handler)) as source_http,
        AsyncWatcherClient(
            "https://watcher.test",
            httpx_client=httpx.AsyncClient(
                base_url="https://watcher.test", transport=httpx.MockTransport(watcher_handler)
            ),
        ) as watcher,
    ):
        source = ComplianceClient(source_http)
        await import_conversation(
            source, watcher, family="local", conversation_id="conversation", receipt_path=receipt_path
        )
        previous = receipt_path.read_bytes()
        with pytest.raises(WatcherAPIError) as caught:
            await import_conversation(
                source, watcher, family="local", conversation_id="conversation", receipt_path=receipt_path
            )
    assert caught.value.status_code == 403
    assert caught.value.code == "permission_denied"
    assert len(sent) == 2
    assert sent[0]["external_ids"] == sent[1]["external_ids"]
    assert sent[0]["messages"][2]["tool_calls"][0]["arguments"]["zero"] == 0
    assert sent[1]["messages"][2]["tool_calls"][0]["arguments"]["zero"] == 1
    assert receipt_path.read_bytes() == previous


@pytest.mark.parametrize("retry_after", ["120", "nan", "invalid"])
async def test_bad_or_long_retry_after_fails_without_retry(retry_after):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(429, headers={"Retry-After": retry_after})

    async with httpx.AsyncClient(base_url="https://source.test", transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ComplianceError):
            await ComplianceClient(http).fetch("local", "conversation")
    assert len(requests) == 1


async def test_retry_recovers_and_http_date_is_supported():
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                503, headers={"Retry-After": format_datetime(datetime.now(UTC) - timedelta(seconds=1))}
            )
        return httpx.Response(200, json=page())

    async with httpx.AsyncClient(base_url="https://source.test", transport=httpx.MockTransport(handler)) as http:
        assert (await ComplianceClient(http).fetch("local", "conversation")).messages
        assert not http.is_closed
    assert len(requests) == 2


@pytest.mark.parametrize("failure", ["server", "cancel", "no-messages"])
async def test_failures_preserve_previous_receipt(tmp_path, failure):
    path = tmp_path / "receipt.json"
    path.write_text("previous receipt")

    def source_handler(request):
        if failure == "cancel":
            raise asyncio.CancelledError
        return httpx.Response(200, json=page(messages=[] if failure == "no-messages" else None))

    def watcher_handler(request):
        return httpx.Response(503 if failure == "server" else 200, json=[])

    expected_error = {
        "server": WatcherAPIError,
        "cancel": asyncio.CancelledError,
        "no-messages": ComplianceError,
    }[failure]
    async with (
        httpx.AsyncClient(base_url="https://source.test", transport=httpx.MockTransport(source_handler)) as http,
        AsyncWatcherClient(
            "https://watcher.test",
            max_retries=0,
            httpx_client=httpx.AsyncClient(
                base_url="https://watcher.test", transport=httpx.MockTransport(watcher_handler)
            ),
        ) as watcher,
    ):
        with pytest.raises(expected_error):
            await import_conversation(
                ComplianceClient(http), watcher, family="local", conversation_id="conversation", receipt_path=path
            )
    assert path.read_text() == "previous receipt"


async def test_existing_receipt_does_not_skip_replay(tmp_path):
    calls = []

    def source_handler(request):
        return httpx.Response(200, json=page())

    def watcher_handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=[])

    async with (
        httpx.AsyncClient(base_url="https://source.test", transport=httpx.MockTransport(source_handler)) as http,
        AsyncWatcherClient(
            "https://watcher.test",
            httpx_client=httpx.AsyncClient(
                base_url="https://watcher.test", transport=httpx.MockTransport(watcher_handler)
            ),
        ) as watcher,
    ):
        first = await import_conversation(
            ComplianceClient(http),
            watcher,
            family="local",
            conversation_id="conversation",
            receipt_path=tmp_path / "receipt.json",
        )
        second = await import_conversation(
            ComplianceClient(http),
            watcher,
            family="local",
            conversation_id="conversation",
            receipt_path=tmp_path / "receipt.json",
        )
    assert len(calls) == 2 and calls[0] == calls[1]
    assert first.source_digest == second.source_digest
