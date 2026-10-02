"""Real SDK/HTTP contracts for finite exports and documented Chronicle v1 UDM JSON.

Google's public REST Event, UDM and Metadata definitions specify the envelope and
field names. Official protobuf Timestamp and Struct types check their respective
JSON shapes independently. Google-hosted UDM semantic validation is not exercised.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from uuid import UUID

import httpx
import pytest
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Struct
from google.protobuf.timestamp_pb2 import Timestamp
from pydantic import ValidationError
from watcher_google_security_operations import (
    DecisionRecord,
    ExportError,
    GoogleSecOpsSink,
    encode_records,
    export_window,
    fetch_records,
)

from watcher_sdk import AsyncWatcherClient

START = datetime(2026, 7, 1, tzinfo=UTC)
END = datetime(2026, 7, 2, tzinfo=UTC)
PARENT = "projects/example-project/locations/us/instances/00000000-0000-0000-0000-000000000001"
ENDPOINT = "https://us-chronicle.googleapis.com"
TOKEN = "synthetic-fixture-token"


def row(index=1, **updates):
    return {
        "tool_call_id": str(UUID(int=index)),
        "session_id": str(UUID(int=100)),
        "occurred_at": "2026-07-01T10:00:00.123456+00:00",
        "tool_use_id": "PRIVATE_TOOL_USE_ID",
        "message_ref": "PRIVATE_MESSAGE_REF",
        "tool_name": "PRIVATE_TOOL_NAME",
        "severity_score": 7,
        "coverage_state": "decided",
        "decision_category": "auto_denied",
        "content_state": "available",
        "user_email": "PRIVATE_EMAIL@example.invalid",
        "user_first_name": "PRIVATE_NAME",
        "tool_input_preview": "PRIVATE_ARGUMENTS",
        "decision_summary": "PRIVATE_SUMMARY",
        **updates,
    }


def page(rows=None, *, total=None, offset=0, limit=200):
    rows = [row()] if rows is None else rows
    return {"tool_calls": rows, "total": len(rows) if total is None else total, "offset": offset, "limit": limit}


def records():
    return [DecisionRecord.model_validate(row())]


def sink(client, **kwargs):
    return GoogleSecOpsSink(client, endpoint=ENDPOINT, parent=PARENT, access_token=TOKEN, **kwargs)


def assert_udm(payload):
    """Check exactly the documented public REST fields plus official well-known types."""
    assert set(payload) == {"inlineSource"}
    assert set(payload["inlineSource"]) == {"events"}
    for event in payload["inlineSource"]["events"]:
        assert set(event) == {"udm"}
        udm = event["udm"]
        assert set(udm) == {"metadata", "additional"}
        metadata = udm["metadata"]
        assert set(metadata) == {
            "eventTimestamp",
            "eventType",
            "vendorName",
            "productName",
            "productEventType",
            "productLogId",
            "description",
        }
        assert metadata["eventType"] == "GENERIC_EVENT"
        assert metadata["productName"] == "Watcher"
        assert metadata["vendorName"] == "Apollo Research"
        assert metadata["productEventType"] == "tool_call_decision"
        assert metadata["description"] == "Watcher recorded a tool-call decision."
        assert len(metadata["description"].encode()) <= 1024
        assert len(metadata["productEventType"].encode()) <= 64
        assert len(metadata["productLogId"].encode()) <= 256
        UUID(metadata["productLogId"])
        timestamp = Timestamp()
        timestamp.FromJsonString(metadata["eventTimestamp"])
        assert timestamp.seconds == 1782900000 and timestamp.nanos == 123456000
        additional = json_format.ParseDict(udm["additional"], Struct())
        assert additional["watcher_tool_call_id"] == metadata["productLogId"]
        assert set(udm["additional"]) <= {
            "watcher_tool_call_id",
            "watcher_session_id",
            "watcher_record_fingerprint",
            "watcher_coverage_state",
            "watcher_content_state",
            "watcher_severity_score",
            "watcher_decision_category",
        }
        assert "PRIVATE" not in json.dumps(event)


async def test_actual_public_sdk_to_strict_google_http_fixture(http_fixture):
    source_requests = []
    destination_requests = []

    def source(method, path, headers, body):
        assert method == "POST" and path == "/v1/tool-calls/search"
        assert headers["x-api-key"] == "fixture-watcher-key"
        request = json.loads(body)
        source_requests.append(request)
        offset = request["offset"]
        return 200, {"Content-Type": "application/json"}, page([row(offset + 1)], total=2, offset=offset, limit=1)

    def destination(method, path, headers, body):
        assert method == "POST" and path == f"/v1/{PARENT}/events:import"
        assert headers["Authorization"] == "Bearer " + TOKEN
        assert headers["Content-Type"] == "application/json"
        payload = json.loads(body)
        assert_udm(payload)
        destination_requests.append(payload)
        return 200, {"Content-Type": "application/json"}, {}

    async with (
        http_fixture(source) as watcher_url,
        http_fixture(destination) as destination_url,
        AsyncWatcherClient(watcher_url, api_key="fixture-watcher-key", max_retries=0) as watcher,
        httpx.AsyncClient(trust_env=False) as client,
    ):
        result = await export_window(
            watcher,
            GoogleSecOpsSink(client, endpoint=destination_url, parent=PARENT, access_token=TOKEN),
            start=START,
            end=END,
            page_size=1,
            batch_size=1,
        )
    assert result.records == 2 and result.batches == 2
    assert [request["offset"] for request in source_requests] == [0, 1]
    assert source_requests[0]["filters"]["start_date"] == START.isoformat()
    assert source_requests[0]["filters"]["end_date"] == END.isoformat()
    assert source_requests[0]["sort_by"] == "occurred_at" and source_requests[0]["sort_order"] == "asc"
    assert len(destination_requests) == 2


async def test_scrubbed_row_without_tool_fields_through_public_sdk(http_fixture):
    scrubbed = {
        "tool_call_id": str(UUID(int=1)),
        "session_id": str(UUID(int=100)),
        "occurred_at": "2026-07-01T10:00:00.123456+00:00",
        "content_state": "scrubbed",
    }
    destination_requests = []

    def source(method, path, headers, body):
        assert method == "POST" and path == "/v1/tool-calls/search"
        return 200, {"Content-Type": "application/json"}, page([scrubbed])

    def destination(method, path, headers, body):
        assert method == "POST" and path == f"/v1/{PARENT}/events:import"
        payload = json.loads(body)
        assert_udm(payload)
        destination_requests.append(payload)
        return 200, {"Content-Type": "application/json"}, {}

    async with (
        http_fixture(source) as watcher_url,
        http_fixture(destination) as destination_url,
        AsyncWatcherClient(watcher_url, max_retries=0) as watcher,
        httpx.AsyncClient(trust_env=False) as client,
    ):
        receipt = await export_window(
            watcher,
            GoogleSecOpsSink(client, endpoint=destination_url, parent=PARENT, access_token=TOKEN),
            start=START,
            end=END,
        )
    assert receipt.records == 1 and receipt.batches == 1
    additional = destination_requests[0]["inlineSource"]["events"][0]["udm"]["additional"]
    assert additional["watcher_content_state"] == "scrubbed"
    assert "watcher_severity_score" not in additional
    assert "watcher_decision_category" not in additional


@pytest.mark.parametrize("content_state", ["available", "scrubbed"])
def test_unscored_record_omits_severity_and_category(content_state):
    record = DecisionRecord.model_validate(
        row(content_state=content_state, severity_score=None, decision_category=None)
    )
    body = json.loads(encode_records([record]))
    assert_udm(body)
    additional = body["inlineSource"]["events"][0]["udm"]["additional"]
    assert "watcher_severity_score" not in additional
    assert "watcher_decision_category" not in additional


@pytest.mark.parametrize(
    "category", ["auto_denied", "cleared", "human_allowed", "human_denied", "would_denied", "would_escalated"]
)
def test_categories_remain_source_values_not_claims_of_execution(category):
    body = json.loads(encode_records([DecisionRecord.model_validate(row(decision_category=category))]))
    event = body["inlineSource"]["events"][0]["udm"]
    assert event["additional"]["watcher_decision_category"] == category
    assert "securityResult" not in event and "principal" not in event and "target" not in event


@pytest.mark.parametrize("score", [1, 7, 10, 101, -1])
async def test_source_score_is_forwarded_without_range_or_scale_conversion(score):
    exported = []

    def source(request):
        return httpx.Response(200, json=page([row(severity_score=score)]))

    def destination(request):
        exported.append(json.loads(request.content))
        return httpx.Response(200, json={})

    async with (
        AsyncWatcherClient(
            "https://watcher.test",
            max_retries=0,
            httpx_client=httpx.AsyncClient(base_url="https://watcher.test", transport=httpx.MockTransport(source)),
        ) as watcher,
        httpx.AsyncClient(transport=httpx.MockTransport(destination)) as client,
    ):
        receipt = await export_window(watcher, sink(client), start=START, end=END)
    assert receipt.records == 1
    event = exported[0]["inlineSource"]["events"][0]["udm"]
    assert event["additional"]["watcher_severity_score"] == score
    assert "securityResult" not in event


def test_fingerprint_ignores_content_but_detects_changed_decision():
    original = DecisionRecord.model_validate(row())
    assert (
        original.fingerprint()
        == DecisionRecord.model_validate(row(user_email="different@private.invalid")).fingerprint()
    )
    assert original.fingerprint() != DecisionRecord.model_validate(row(severity_score=3)).fingerprint()


@pytest.mark.parametrize(
    "updates",
    [
        {"coverage_state": "PRIVATE_NEW_VALUE"},
        {"decision_category": "PRIVATE_NEW_VALUE"},
        {"content_state": "PRIVATE_NEW_VALUE"},
        {"severity_score": True},
        {"severity_score": 7.0},
        {"severity_score": False},
        {"severity_score": "7"},
        {"tool_call_id": "PRIVATE_ID"},
        {"occurred_at": "2026-07-01T10:00:00"},
        {"occurred_at": "1969-12-31T23:59:59Z"},
    ],
)
def test_invalid_source_values_rejected(updates):
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(row(**updates))


async def run_pages(pages, *, max_pages=100, max_request_bytes=1048576, batch_size=1):
    source_calls = []
    destination_calls = []

    def source(request):
        source_calls.append(request)
        return httpx.Response(200, json=pages[len(source_calls) - 1])

    def destination(request):
        destination_calls.append(request)
        return httpx.Response(200, json={})

    async with (
        AsyncWatcherClient(
            "https://watcher.test",
            max_retries=0,
            httpx_client=httpx.AsyncClient(base_url="https://watcher.test", transport=httpx.MockTransport(source)),
        ) as watcher,
        httpx.AsyncClient(transport=httpx.MockTransport(destination)) as client,
    ):
        try:
            return await export_window(
                watcher,
                sink(client, max_request_bytes=max_request_bytes),
                start=START,
                end=END,
                page_size=1,
                max_pages=max_pages,
                batch_size=batch_size,
            )
        except Exception:
            assert not destination_calls
            raise


@pytest.mark.parametrize(
    "mutation",
    ["total", "duplicate", "offset", "limit", "outside", "empty", "maximum", "too-many", "negative", "invalid-score"],
)
async def test_bad_source_aborts_before_destination_writes(mutation):
    pages = [page([row(1)], total=2, limit=1), page([row(2)], total=2, offset=1, limit=1)]
    maximum = 100
    if mutation == "total":
        pages[1]["total"] = 3
    elif mutation == "duplicate":
        pages[1]["tool_calls"] = [row(1)]
    elif mutation == "offset":
        pages[1]["offset"] = 0
    elif mutation == "limit":
        pages[1]["limit"] = 5
    elif mutation == "outside":
        pages[1]["tool_calls"] = [row(2, occurred_at="2026-01-01T00:00:00Z")]
    elif mutation == "empty":
        pages[1]["tool_calls"] = []
    elif mutation == "maximum":
        maximum = 1
    elif mutation == "negative":
        pages[0]["total"] = -1
    elif mutation == "invalid-score":
        pages[1]["tool_calls"] = [row(2, severity_score="not-an-integer")]
    else:
        pages[1]["tool_calls"] = [row(2), row(3)]
    with pytest.raises(ExportError):
        await run_pages(pages, max_pages=maximum)


@pytest.mark.parametrize(
    "field,value", [("offset", False), ("limit", True), ("total", True), ("total", "1"), ("total", 1.0)]
)
async def test_pagination_metadata_requires_actual_integers(field, value):
    malformed = page([row()], total=1, offset=0, limit=1)
    malformed[field] = value
    with pytest.raises(ExportError, match="pagination metadata"):
        await run_pages([malformed])


async def test_empty_window_is_not_sent():
    receipt = await run_pages([page([], total=0, limit=1)])
    assert receipt.records == 0 and receipt.batches == 0


async def test_size_failure_before_any_send():
    with pytest.raises(ExportError, match="byte bound"):
        await run_pages(
            [page([row(1)], total=2, limit=1), page([row(2)], total=2, offset=1, limit=1)], max_request_bytes=1
        )


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://us-chronicle.googleapis.com",
        "https://evil.example",
        "https://us-chronicle.googleapis.com.evil.test",
        "https://u:secret@us-chronicle.googleapis.com",
        "https://us-chronicle.googleapis.com?token=secret",
        "https://us-chronicle.googleapis.com#fragment",
        "https://us-chronicle.googleapis.com/custom",
        "https://us-chronicle.googleapis.com:444",
        "ftp://localhost",
        "/v1/events:import",
    ],
)
def test_rejects_nonregional_or_credential_leaking_endpoint(endpoint):
    with pytest.raises(ValueError):
        GoogleSecOpsSink(httpx.AsyncClient(), endpoint=endpoint, parent=PARENT, access_token=TOKEN)


@pytest.mark.parametrize(
    "parent", ["", "projects/x", PARENT + "/events/x", PARENT + "?a=b", PARENT.replace("example-project", "..")]
)
def test_parent_is_resource_name_not_url(parent):
    with pytest.raises(ValueError):
        GoogleSecOpsSink(httpx.AsyncClient(), endpoint=ENDPOINT, parent=parent, access_token=TOKEN)


@pytest.mark.parametrize("token", ["", "has space", "line\nbreak", "tab\tvalue"])
def test_empty_or_invalid_tokens_rejected(token):
    with pytest.raises(ValueError):
        GoogleSecOpsSink(httpx.AsyncClient(), endpoint=ENDPOINT, parent=PARENT, access_token=token)


@pytest.mark.parametrize(
    "settings", [{"attempts": 0}, {"attempts": 6}, {"max_request_bytes": 0}, {"max_request_bytes": 1048577}]
)
def test_sink_bounds(settings):
    with pytest.raises(ValueError):
        sink(httpx.AsyncClient(), **settings)


@pytest.mark.parametrize(
    "status,expected_calls",
    [(400, 1), (401, 1), (403, 1), (413, 1), (429, 3), (500, 1), (502, 1), (503, 1), (504, 1), (302, 1), (204, 1)],
)
async def test_no_blind_retries_or_redirects(status, expected_calls):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, text="PRIVATE_REMOTE_BODY", headers={"Retry-After": "0", "Location": "https://other.invalid"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ExportError) as caught:
            await sink(client).send(records())
    assert len(calls) == expected_calls
    assert "PRIVATE" not in str(caught.value) and TOKEN not in str(caught.value)


@pytest.mark.parametrize("status", [302, 307, 308])
async def test_redirect_override_blocks_caller_enabled_redirects(http_fixture, status):
    origin_requests = []
    target_requests = []

    def target(method, path, headers, body):
        target_requests.append((method, path, headers, body))
        return 200, {"Content-Type": "application/json"}, {}

    async with http_fixture(target) as target_url:

        def origin(method, path, headers, body):
            origin_requests.append((method, path, headers, body))
            assert method == "POST" and path == f"/v1/{PARENT}/events:import"
            assert headers["Authorization"] == "Bearer " + TOKEN
            return status, {"Location": target_url + "/redirect-target"}, b""

        async with (
            http_fixture(origin) as origin_url,
            httpx.AsyncClient(follow_redirects=True, trust_env=False) as client,
        ):
            destination = GoogleSecOpsSink(client, endpoint=origin_url, parent=PARENT, access_token=TOKEN)
            with pytest.raises(ExportError, match=f"HTTP {status}"):
                await destination.send(records())

    assert len(origin_requests) == 1
    assert target_requests == []


async def test_explicit_rate_limit_retries_identical_bytes(monkeypatch):
    calls = []
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", sleep)

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "1.5"}) if len(calls) == 1 else httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await sink(client).send(records())
    assert sleeps == [1.5]
    assert calls[0].content == calls[1].content


@pytest.mark.parametrize("header", ["nan", "inf", "31", "nonsense", "Thu, 17 Sep 2026 00:00:00"])
async def test_bad_retry_headers_fail_without_replay(header):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": header})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ExportError):
            await sink(client).send(records())
    assert len(calls) == 1


@pytest.mark.parametrize("header", [None, "-1", format_datetime(datetime.now(UTC) - timedelta(seconds=5), usegmt=True)])
async def test_retry_default_or_elapsed_date_is_bounded(header, monkeypatch):
    delays = []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", sleep)

    def handler(request):
        return httpx.Response(429, headers={} if header is None else {"Retry-After": header})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ExportError):
            await sink(client).send(records())
    assert delays == ([0.25, 0.5] if header is None else [0, 0])


@pytest.mark.parametrize(
    "body,content_type",
    [
        (b"{bad", "application/json"),
        (b"[]", "application/json"),
        (b"null", "application/json"),
        (b'{"error":"PRIVATE"}', "application/json"),
        (b'{"partialSuccess":{"accepted":1}}', "application/json"),
        (b"{}", "text/html"),
        (b"x" * 4097, "application/json"),
    ],
)
async def test_unexpected_partial_or_malformed_acknowledgment_fails(body, content_type):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=body, headers={"Content-Type": content_type})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ExportError) as caught:
            await sink(client).send(records())
    assert len(calls) == 1 and "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize("body", [b"", b"  ", b"{}", b" { } \n"])
async def test_empty_acknowledgments_accepted(body):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=body, headers={"Content-Type": "application/json"})
        )
    ) as client:
        await sink(client).send(records())


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError])
async def test_ambiguous_transport_not_retried(error):
    calls = []

    def handler(request):
        calls.append(request)
        raise error("PRIVATE_TOKEN_PAYLOAD", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ExportError, match="acceptance is unknown") as caught:
            await sink(client).send(records())
    assert len(calls) == 1 and "PRIVATE" not in str(caught.value)


async def test_direct_empty_and_oversized_send_do_not_connect():
    def handler(request):
        pytest.fail("unexpected request")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        destination = sink(client, max_request_bytes=1)
        await destination.send([])
        with pytest.raises(ExportError, match="byte bound"):
            await destination.send(records())
        assert TOKEN not in repr(destination.access_token)


async def test_later_batch_failure_reports_earlier_acknowledgments():
    destination_requests = []

    def source(request):
        return httpx.Response(200, json=page([row(1), row(2)], total=2))

    def destination(request):
        destination_requests.append(request)
        return httpx.Response(200, json={}) if len(destination_requests) == 1 else httpx.Response(503)

    async with (
        AsyncWatcherClient(
            "https://watcher.test",
            max_retries=0,
            httpx_client=httpx.AsyncClient(base_url="https://watcher.test", transport=httpx.MockTransport(source)),
        ) as watcher,
        httpx.AsyncClient(transport=httpx.MockTransport(destination)) as client,
    ):
        with pytest.raises(ExportError) as caught:
            await export_window(watcher, sink(client), start=START, end=END, batch_size=1)
    assert caught.value.acknowledged_records == 1 and caught.value.acknowledged_batches == 1
    assert len(destination_requests) == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"start": END},
        {"end": START},
        {"start": START.replace(tzinfo=None)},
        {"end": END.replace(tzinfo=None)},
        {"start": datetime(1969, 1, 1, tzinfo=UTC)},
        {"page_size": 0},
        {"page_size": 1001},
        {"max_pages": 0},
    ],
)
async def test_invalid_fetch_bounds_fail_before_calls(changes):
    settings = {"start": START, "end": END, **changes}
    async with AsyncWatcherClient("https://watcher.test", max_retries=0) as watcher:
        with pytest.raises(ValueError):
            await fetch_records(watcher, **settings)


@pytest.mark.parametrize("batch_size", [0, 1001])
async def test_invalid_batch_bound_fails_before_source(batch_size):
    async with AsyncWatcherClient("https://watcher.test", max_retries=0) as watcher, httpx.AsyncClient() as client:
        with pytest.raises(ValueError):
            await export_window(watcher, sink(client), start=START, end=END, batch_size=batch_size)
