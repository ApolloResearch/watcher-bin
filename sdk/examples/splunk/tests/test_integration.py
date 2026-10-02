"""Verify destination serialization, delivery ambiguity and bounded retries."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from uuid import UUID

import httpx
import pytest
from watcher_splunk import ExportError, HecSink, export_window

from watcher_sdk import AsyncWatcherClient

START = datetime(2026, 7, 1, tzinfo=UTC)
END = datetime(2026, 7, 2, tzinfo=UTC)


def row(index=1, **updates):
    return {
        "tool_call_id": str(UUID(int=index)),
        "session_id": str(UUID(int=100)),
        "occurred_at": "2026-07-01T10:00:00.123456+00:00",
        "tool_use_id": "PRIVATE_CALL_ID",
        "message_ref": "PRIVATE_REF",
        "tool_name": "PRIVATE_TOOL_NAME",
        "severity_score": 7,
        "coverage_state": "decided",
        "decision_category": "auto_denied",
        "content_state": "available",
        "user_email": "person@example.invalid",
        "tool_input_preview": "PRIVATE_ARGUMENTS",
        **updates,
    }


def page(rows=None, offset=0, limit=200, total=None):
    rows = [row()] if rows is None else rows
    return {"tool_calls": rows, "total": len(rows) if total is None else total, "offset": offset, "limit": limit}


def sink(http, url="https://receiver.test", **options):
    return HecSink(http, url, "fixture-token", **options)


def success():
    return httpx.Response(200, json={"code": 0})


async def test_real_sdk_http_to_destination_preserves_order_and_excludes_private_fields(http_fixture):
    source = []
    received = []

    def source_handler(method, path, headers, body):
        assert method == "POST" and path == "/v1/tool-calls/search"
        query = json.loads(body)
        source.append(query)
        offset = query["offset"]
        return 200, {"Content-Type": "application/json"}, page([row(offset + 1)], offset=offset, limit=1, total=2)

    def sink_handler(method, path, headers, body):
        assert method == "POST" and path == "/services/collector/event"
        assert headers["Authorization"] == "Splunk fixture-token"
        assert headers["Content-Type"] == "application/json"
        received.append(body)
        return 200, {"Content-Type": "application/json"}, {"code": 0}

    async with (
        http_fixture(source_handler) as source_url,
        http_fixture(sink_handler) as receiver_url,
        AsyncWatcherClient(source_url, max_retries=0) as watcher,
        httpx.AsyncClient(trust_env=False) as http,
    ):
        receipt = await export_window(
            watcher, sink(http, receiver_url), start=START, end=END, page_size=1, batch_size=1
        )
    assert receipt.records == 2 and receipt.batches == 2
    assert [query["offset"] for query in source] == [0, 1]
    assert source[0]["sort_by"] == "occurred_at" and source[0]["sort_order"] == "asc"
    assert source[0]["filters"]["start_date"] == START.isoformat()
    assert source[0]["filters"]["end_date"] == END.isoformat()
    assert all(b"PRIVATE" not in body and b"person@example" not in body for body in received)
    decoded = [json.loads(body)["event"] for body in received]
    assert [record["tool_call_id"] for record in decoded] == [str(UUID(int=1)), str(UUID(int=2))]
    assert all(record["record_fingerprint"] for record in decoded)


@pytest.mark.parametrize(
    "url",
    [
        "http://outside.test",
        "/relative",
        "ftp://127.0.0.1",
        "https://a:b@receiver.test",
        "https://receiver.test/path",
        "https://receiver.test?key=secret",
        "https://receiver.test#fragment",
    ],
)
def test_invalid_endpoint(url):
    with pytest.raises(ValueError):
        sink(httpx.AsyncClient(), url)


@pytest.mark.parametrize("token", ["", "a b", "a\nb", "a\rb"])
def test_invalid_token(token):
    with pytest.raises(ValueError):
        HecSink(
            httpx.AsyncClient(),
            "https://receiver.test",
            token,
        )


@pytest.mark.parametrize("kind", ["timeout", "cancel"])
async def test_transport_ambiguity_is_not_retried(kind):
    calls = []

    def handler(request):
        calls.append(request)
        if kind == "cancel":
            raise asyncio.CancelledError
        raise httpx.ReadTimeout("fixture")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(asyncio.CancelledError if kind == "cancel" else httpx.ReadTimeout):
            await sink(http).send(b'{"event":{"fixture":true}}')
        assert not http.is_closed
    assert len(calls) == 1


@pytest.mark.parametrize("value", ["nan", "inf", "bad", "31", "60", "100"])
async def test_bad_retry_header_never_retries_early(value):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": value}, json={"code": 26})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ExportError):
            await sink(http).send(b'{"event":{"fixture":true}}')
    assert len(calls) == 1


async def test_retry_after_http_date_replays_identical_bytes():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            value = format_datetime(datetime.now(UTC) - timedelta(seconds=1))
            return httpx.Response(429, headers={"Retry-After": value}, json={"code": 26})
        return success()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await sink(http).send(b'{"event":{"fixture":true}}')
    assert len(calls) == 2 and calls[0].content == calls[1].content


async def test_empty_window_sends_nothing():
    def handler(request):
        assert request.url.host == "watcher.test"
        return httpx.Response(200, json=page([]))

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http,
        AsyncWatcherClient(
            "https://watcher.test",
            max_retries=0,
            httpx_client=httpx.AsyncClient(base_url="https://watcher.test", transport=httpx.MockTransport(handler)),
        ) as watcher,
    ):
        receipt = await export_window(watcher, sink(http), start=START, end=END)
        assert receipt.records == receipt.batches == 0
        await sink(http).send(b"")


async def test_source_error_precedes_any_delivery():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.host == "watcher.test"
        return httpx.Response(200, json=page([row(1, occurred_at="2025-01-01T00:00:00Z")]))

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http,
        AsyncWatcherClient(
            "https://watcher.test",
            max_retries=0,
            httpx_client=httpx.AsyncClient(base_url="https://watcher.test", transport=httpx.MockTransport(handler)),
        ) as watcher,
    ):
        with pytest.raises(ExportError):
            await export_window(watcher, sink(http), start=START, end=END)
    assert len(calls) == 1


async def test_single_record_oversize_rejected_before_destination_write():
    def handler(request):
        assert request.url.host == "watcher.test"
        return httpx.Response(200, json=page())

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http,
        AsyncWatcherClient(
            "https://watcher.test",
            max_retries=0,
            httpx_client=httpx.AsyncClient(base_url="https://watcher.test", transport=httpx.MockTransport(handler)),
        ) as watcher,
    ):
        with pytest.raises(ExportError):
            await export_window(watcher, sink(http), start=START, end=END, max_batch_bytes=100)


async def test_byte_budget_splits_complete_records():
    bodies = []

    def handler(request):
        if request.url.host == "watcher.test":
            return httpx.Response(200, json=page([row(i) for i in range(1, 4)]))
        bodies.append(request.content)
        return success()

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http,
        AsyncWatcherClient(
            "https://watcher.test",
            max_retries=0,
            httpx_client=httpx.AsyncClient(base_url="https://watcher.test", transport=httpx.MockTransport(handler)),
        ) as watcher,
    ):
        receipt = await export_window(watcher, sink(http), start=START, end=END, max_batch_bytes=700)
    assert receipt.records == 3 and receipt.batches == 3
    assert all(len(body) <= 700 for body in bodies)


async def test_later_failure_does_not_report_complete_receipt_or_resend_earlier_batch():
    bodies = []

    def handler(request):
        if request.url.host == "watcher.test":
            return httpx.Response(200, json=page([row(1), row(2)]))
        bodies.append(request.content)
        return success() if len(bodies) == 1 else httpx.Response(400, json={"code": 6, "text": "PRIVATE_ERROR"})

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http,
        AsyncWatcherClient(
            "https://watcher.test",
            max_retries=0,
            httpx_client=httpx.AsyncClient(base_url="https://watcher.test", transport=httpx.MockTransport(handler)),
        ) as watcher,
    ):
        with pytest.raises(ExportError) as error:
            await export_window(watcher, sink(http), start=START, end=END, batch_size=1)
    assert len(bodies) == 2 and "PRIVATE" not in str(error.value)


async def test_real_http_hec_batch_contains_two_complete_ordered_events(http_fixture):
    """A successful request contains distinct HEC envelopes, not a JSON array."""
    source_requests = []
    receiver_requests = []
    expected = [
        {
            "time": 1782900000.123456,
            "source": "watcher",
            "sourcetype": "watcher:decision",
            "event": {
                "tool_call_id": "00000000-0000-0000-0000-000000000001",
                "session_id": "00000000-0000-0000-0000-000000000064",
                "occurred_at": "2026-07-01T10:00:00.123456Z",
                "severity_score": 7,
                "coverage_state": "decided",
                "decision_category": "auto_denied",
                "content_state": "available",
                "event_type": "watcher.tool_call.decision",
                "record_fingerprint": "ae9cadfed50a41e06a9e73b83426e6373e7c7bf73479d0706396c03b87fbb983",
            },
            "index": "watcher",
        },
        {
            "time": 1782900001.0,
            "source": "watcher",
            "sourcetype": "watcher:decision",
            "event": {
                "tool_call_id": "00000000-0000-0000-0000-000000000002",
                "session_id": "00000000-0000-0000-0000-000000000064",
                "occurred_at": "2026-07-01T10:00:01Z",
                "severity_score": 3,
                "coverage_state": "decided",
                "decision_category": "cleared",
                "content_state": "available",
                "event_type": "watcher.tool_call.decision",
                "record_fingerprint": "faff55907ae26c522626aa420e03e9bc442be963728675c585803aa65d563b04",
            },
            "index": "watcher",
        },
    ]
    expected_wire = b"\n".join(json.dumps(event, separators=(",", ":")).encode() for event in expected)

    def source_handler(method, path, headers, body):
        assert method == "POST" and path == "/v1/tool-calls/search"
        query = json.loads(body)
        source_requests.append(query)
        assert query["offset"] == 0 and query["limit"] == 200
        return (
            200,
            {"Content-Type": "application/json"},
            page(
                [
                    row(1),
                    row(2, occurred_at="2026-07-01T10:00:01+00:00", severity_score=3, decision_category="cleared"),
                ]
            ),
        )

    def receiver_handler(method, path, headers, body):
        assert method == "POST" and path == "/services/collector/event"
        assert headers["Authorization"] == "Splunk fixture-token"
        assert headers["Content-Type"] == "application/json"
        assert int(headers["Content-Length"]) == len(expected_wire)
        receiver_requests.append(body)
        lines = body.split(b"\n")
        assert len(lines) == 2
        assert [json.loads(line) for line in lines] == expected
        assert body == expected_wire
        assert b"PRIVATE" not in body and b"person@example" not in body
        return 200, {"Content-Type": "application/json"}, {"text": "Success", "code": 0}

    async with (
        http_fixture(source_handler) as source_url,
        http_fixture(receiver_handler) as receiver_url,
        AsyncWatcherClient(source_url, max_retries=0) as watcher,
        httpx.AsyncClient(trust_env=False) as http,
    ):
        receipt = await export_window(
            watcher,
            sink(http, receiver_url, index="watcher"),
            start=START,
            end=END,
        )
    assert len(source_requests) == len(receiver_requests) == 1
    assert receipt.records == 2 and receipt.batches == 1
    assert receipt.start == START and receipt.end == END
