"""Real SDK and OTLP protobuf wire tests with synthetic, content-bearing source rows."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from uuid import UUID

import httpx
import pytest
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest, ExportLogsServiceResponse
from watcher_opentelemetry import (
    DecisionRecord,
    ExportError,
    OtlpLogSink,
    PartialExportError,
    encode_records,
    export_window,
    fetch_records,
)

from watcher_sdk import AsyncWatcherClient

START = datetime(2026, 7, 1, tzinfo=UTC)
END = datetime(2026, 7, 2, tzinfo=UTC)


def row(index=1, **updates):
    return {
        "tool_call_id": str(UUID(int=index)),
        "session_id": str(UUID(int=100)),
        "occurred_at": "2026-07-01T10:00:00.123456+00:00",
        "tool_use_id": f"source-call-{index}",
        "message_ref": "private-message-reference",
        "tool_name": "customer_tool",
        "severity_score": 7,
        "coverage_state": "decided",
        "decision_category": "auto_denied",
        "content_state": "available",
        "user_email": "person@example.invalid",
        "user_first_name": "Private Person",
        "tool_input_preview": "PRIVATE_ARGUMENTS",
        "decision_summary": "PRIVATE_SUMMARY",
        **updates,
    }


def page(rows=None, total=None, offset=0, limit=200):
    rows = [row()] if rows is None else rows
    return {"tool_calls": rows, "total": len(rows) if total is None else total, "limit": limit, "offset": offset}


def records():
    return [DecisionRecord.model_validate(row())]


def decode(payload):
    request = ExportLogsServiceRequest()
    request.ParseFromString(payload)
    return request


async def test_real_http_sdk_to_otlp_receiver(http_fixture):
    watcher_requests = []
    payloads = []

    def watcher_handler(method, path, headers, body):
        assert method == "POST" and path == "/v1/tool-calls/search"
        request = json.loads(body)
        watcher_requests.append(request)
        offset = request["offset"]
        return 200, {"Content-Type": "application/json"}, page([row(offset + 1)], total=2, offset=offset, limit=1)

    def otlp_handler(method, path, headers, body):
        assert method == "POST" and path == "/v1/logs"
        assert headers["Content-Type"] == "application/x-protobuf"
        payloads.append(decode(body))
        return 200, {"Content-Type": "application/x-protobuf"}, ExportLogsServiceResponse().SerializeToString()

    async with (
        http_fixture(watcher_handler) as watcher_url,
        http_fixture(otlp_handler) as otlp_url,
        AsyncWatcherClient(watcher_url, max_retries=0) as watcher,
        httpx.AsyncClient(trust_env=False) as receiver,
    ):
        receipt = await export_window(
            watcher, OtlpLogSink(receiver, otlp_url + "/v1/logs"), start=START, end=END, page_size=1, batch_size=1
        )
    assert receipt.records == 2 and receipt.batches == 2
    assert [r["offset"] for r in watcher_requests] == [0, 1]
    assert watcher_requests[0]["sort_by"] == "occurred_at" and watcher_requests[0]["sort_order"] == "asc"
    assert watcher_requests[0]["filters"]["start_date"] == START.isoformat()
    for request in payloads:
        resource = request.resource_logs[0]
        assert [(a.key, a.value.string_value) for a in resource.resource.attributes] == [
            ("service.name", "watcher-decisions")
        ]
        log = resource.scope_logs[0].log_records[0]
        attrs = {a.key: a.value for a in log.attributes}
        assert attrs["watcher.severity_score"].int_value == 7
        assert attrs["watcher.decision_category"].string_value == "auto_denied"
        assert log.event_name == "watcher.tool_call.decision"
        assert log.time_unix_nano == 1782900000123456000
        assert log.observed_time_unix_nano > log.time_unix_nano
        assert log.severity_number == 0 and not log.trace_id and not log.span_id
        serialized = str(request)
        assert all(
            secret not in serialized
            for secret in (
                "PRIVATE",
                "person@example",
                "Private Person",
                "customer_tool",
                "source-call",
                "private-message",
            )
        )


@pytest.mark.parametrize("content_state", ["available", "scrubbed"])
def test_unscored_and_scrubbed_rows_do_not_fabricate_severity(content_state):
    record = DecisionRecord.model_validate(
        row(severity_score=None, decision_category=None, content_state=content_state)
    )
    payload = decode(encode_records([record], observed_at=END))
    keys = {a.key for a in payload.resource_logs[0].scope_logs[0].log_records[0].attributes}
    assert "watcher.severity_score" not in keys and "watcher.decision_category" not in keys


def test_fingerprint_stable_but_changes_when_decision_changes():
    original = DecisionRecord.model_validate(row())
    same = DecisionRecord.model_validate(row(user_email="another@example.invalid"))
    changed = DecisionRecord.model_validate(row(severity_score=8))
    assert original.fingerprint() == same.fingerprint()
    assert original.fingerprint() != changed.fingerprint()


async def get_pages(pages, *, max_pages=100):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=pages[min(len(seen) - 1, len(pages) - 1)])

    async with AsyncWatcherClient(
        "https://watcher.test",
        max_retries=0,
        httpx_client=httpx.AsyncClient(base_url="https://watcher.test", transport=httpx.MockTransport(handler)),
    ) as watcher:
        return await fetch_records(watcher, start=START, end=END, page_size=1, max_pages=max_pages)


@pytest.mark.parametrize(
    "mutation", ["total", "duplicate", "offset", "limit", "outside", "empty", "maximum", "too-many"]
)
async def test_bad_or_mutating_source_window_is_rejected(mutation):
    pages = [page([row(1)], total=2, limit=1), page([row(2)], total=2, offset=1, limit=1)]
    maximum = 100
    if mutation == "total":
        pages[1]["total"] = 3
    elif mutation == "duplicate":
        pages[1]["tool_calls"] = [row(1)]
    elif mutation == "offset":
        pages[1]["offset"] = 0
    elif mutation == "limit":
        pages[1]["limit"] = 100
    elif mutation == "outside":
        pages[1]["tool_calls"] = [row(2, occurred_at="2026-01-01T00:00:00Z")]
    elif mutation == "empty":
        pages[1]["tool_calls"] = []
    elif mutation == "maximum":
        maximum = 1
    else:
        pages[1]["tool_calls"] = [row(2), row(3)]
    with pytest.raises(ExportError):
        await get_pages(pages, max_pages=maximum)


async def test_empty_source_window_returns_empty():
    assert await get_pages([page([], total=0, limit=1)]) == []


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://outside.example/v1/logs",
        "ftp://127.0.0.1/v1/logs",
        "/v1/logs",
        "https://name:secret@example.invalid/v1/logs",
        "https://example.invalid/v1/logs?key=secret",
        "https://example.invalid/v1/logs#fragment",
    ],
)
def test_invalid_or_insecure_endpoint_is_rejected(endpoint):
    with pytest.raises(ValueError):
        OtlpLogSink(httpx.AsyncClient(), endpoint)


@pytest.mark.parametrize(
    "status,attempts",
    [(400, 1), (401, 1), (403, 1), (413, 1), (500, 1), (429, 3), (502, 3), (503, 3), (504, 3), (302, 1)],
)
async def test_protocol_retry_statuses_are_bounded(status, attempts):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={"Retry-After": "0", "Location": "https://other.test"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(httpx.HTTPStatusError):
            await OtlpLogSink(http, "https://receiver.test/v1/logs").send(records(), observed_at=END)
    assert len(calls) == attempts


@pytest.mark.parametrize("rejected,error", [(1, "dropped"), (0, "warning")])
async def test_partial_acceptance_is_not_retried_or_reported_as_complete(rejected, error):
    calls = []

    def handler(request):
        calls.append(request)
        response = ExportLogsServiceResponse()
        response.partial_success.rejected_log_records = rejected
        response.partial_success.error_message = error
        return httpx.Response(
            200, content=response.SerializeToString(), headers={"Content-Type": "application/x-protobuf"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(PartialExportError) as caught:
            await OtlpLogSink(http, "https://receiver.test/v1/logs").send(records(), observed_at=END)
    assert caught.value.rejected_records == rejected and len(calls) == 1


@pytest.mark.parametrize("kind", ["malformed", "wrong-content-type", "negative", "too-many", "status204"])
async def test_invalid_acknowledgments_fail(kind):
    response = ExportLogsServiceResponse()
    if kind == "negative":
        response.partial_success.rejected_log_records = -1
    if kind == "too-many":
        response.partial_success.rejected_log_records = 2
    payload = b"invalid-protobuf" if kind == "malformed" else response.SerializeToString()

    def handler(request):
        return httpx.Response(
            204 if kind == "status204" else 200,
            content=payload,
            headers={"Content-Type": "application/json" if kind == "wrong-content-type" else "application/x-protobuf"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ExportError):
            await OtlpLogSink(http, "https://receiver.test/v1/logs").send(records(), observed_at=END)


@pytest.mark.parametrize("kind", ["timeout", "cancel"])
async def test_ambiguous_transport_failure_is_not_retried(kind):
    calls = []

    def handler(request):
        calls.append(request)
        if kind == "cancel":
            raise asyncio.CancelledError
        raise httpx.ReadTimeout("fixture")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(asyncio.CancelledError if kind == "cancel" else httpx.ReadTimeout):
            await OtlpLogSink(http, "https://receiver.test/v1/logs").send(records(), observed_at=END)
        assert not http.is_closed
    assert len(calls) == 1


@pytest.mark.parametrize("value", ["100", "nan", "bad"])
async def test_invalid_or_long_retry_after_does_not_retry_early(value):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503, headers={"Retry-After": value})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ExportError):
            await OtlpLogSink(http, "https://receiver.test/v1/logs").send(records(), observed_at=END)
    assert len(calls) == 1


async def test_transient_failure_recovers_with_http_date():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                429, headers={"Retry-After": format_datetime(datetime.now(UTC) - timedelta(seconds=1))}
            )
        return httpx.Response(200, content=b"", headers={"Content-Type": "application/x-protobuf"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await OtlpLogSink(http, "https://receiver.test/v1/logs").send(records(), observed_at=END)
    assert len(calls) == 2 and calls[0].content == calls[1].content


@pytest.mark.parametrize(
    "start,end", [(START, START), (END, START), (START.replace(tzinfo=None), END), (START, END.replace(tzinfo=None))]
)
async def test_invalid_time_windows_never_query_source(start, end):
    async with AsyncWatcherClient(
        "https://watcher.test",
        httpx_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pytest.fail("source queried"))),
    ) as watcher:
        with pytest.raises(ValueError):
            await fetch_records(watcher, start=start, end=end)


async def test_empty_records_do_not_send_http():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: pytest.fail("empty export sent"))
    ) as http:
        await OtlpLogSink(http, "https://receiver.test/v1/logs").send([], observed_at=END)


async def test_request_size_limit_rejects_before_http():
    sent = []

    def receive(request):
        sent.append(request)
        return httpx.Response(200, headers={"Content-Type": "application/x-protobuf"}, content=b"")

    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as http:
        payload = encode_records(records(), observed_at=END)
        with pytest.raises(ExportError, match="max_request_bytes"):
            await OtlpLogSink(http, "https://receiver.test/v1/logs", max_request_bytes=len(payload) - 1).send(
                records(), observed_at=END
            )
        assert sent == []
        await OtlpLogSink(http, "https://receiver.test/v1/logs", max_request_bytes=len(payload)).send(
            records(), observed_at=END
        )
        assert len(sent) == 1


@pytest.mark.parametrize("maximum", [0, -1])
async def test_request_size_limit_must_be_positive(maximum):
    async with httpx.AsyncClient() as http:
        with pytest.raises(ValueError, match="max_request_bytes"):
            OtlpLogSink(http, "https://receiver.test/v1/logs", max_request_bytes=maximum)


@pytest.mark.parametrize(
    "field,value", [("offset", False), ("limit", True), ("total", True), ("total", "1"), ("total", 1.0)]
)
async def test_pagination_counts_require_integers(field, value):
    malformed = page([row(1)], total=1, limit=1)
    malformed[field] = value
    with pytest.raises(ExportError, match="integers"):
        await get_pages([malformed])


async def test_later_oversized_batch_prevents_all_transmission(http_fixture):
    source_rows = [row(1, decision_category=None, severity_score=None), row(2)]
    first = DecisionRecord.model_validate(source_rows[0])
    second = DecisionRecord.model_validate(source_rows[1])
    maximum = len(encode_records([first], observed_at=END))
    assert len(encode_records([second], observed_at=END)) > maximum
    deliveries = []

    def source_handler(method, path, headers, body):
        return 200, {"Content-Type": "application/json"}, page(source_rows, total=2)

    def sink_handler(method, path, headers, body):
        deliveries.append(body)
        return 200, {"Content-Type": "application/x-protobuf"}, b""

    async with (
        http_fixture(source_handler) as source_url,
        http_fixture(sink_handler) as sink_url,
        AsyncWatcherClient(source_url, max_retries=0) as watcher,
        httpx.AsyncClient(trust_env=False) as receiver,
    ):
        sink = OtlpLogSink(receiver, sink_url + "/v1/logs", max_request_bytes=maximum)
        with pytest.raises(ExportError, match="max_request_bytes"):
            await export_window(watcher, sink, start=START, end=END, batch_size=1)
    assert deliveries == []
