"""Azure DCR wiring, payload limits and no credential-discovery behavior."""

import json
from importlib.resources import files
from uuid import UUID

import httpx
import pytest
from watcher_microsoft_sentinel import DecisionRecord, ExportError, LogsIngestionSink, encode_record


@pytest.mark.parametrize(
    "status,attempts",
    [
        (200, 1),
        (202, 1),
        (400, 1),
        (401, 1),
        (403, 1),
        (404, 1),
        (413, 1),
        (429, 3),
        (500, 3),
        (502, 3),
        (503, 3),
        (504, 3),
        (302, 1),
    ],
)
async def test_only_204_acknowledges_and_retries_are_bounded(status, attempts):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            headers={"Retry-After": "0", "Location": "https://other.test"},
            json={"error": {"message": "PRIVATE_ERROR"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as http:
        with pytest.raises(ExportError) as error:
            await LogsIngestionSink(http, "https://receiver.test", "fixture", rule_id="dcr-fixture").send(
                b'[{"fixture":true}]'
            )
    assert len(calls) == attempts and "PRIVATE_ERROR" not in str(error.value)
    assert len({request.headers["x-ms-client-request-id"] for request in calls}) == 1


@pytest.mark.parametrize(
    "options",
    [
        {"rule_id": "/subscriptions/foo"},
        {"rule_id": "dcr-a/b"},
        {"rule_id": "dcr-a?x"},
        {"rule_id": "dcr-"},
        {"rule_id": "dcr-ok", "stream": "Custom-A/B"},
        {"rule_id": "dcr-ok", "stream": "Microsoft-Wrong"},
        {"rule_id": "dcr-ok", "attempts": 0},
    ],
)
def test_invalid_resource_configuration(options):
    with pytest.raises(ValueError):
        LogsIngestionSink(httpx.AsyncClient(), "https://receiver.test", "fixture", **options)


async def test_oversized_body_never_leaves_client_and_empty_is_noop():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pytest.fail("request sent"))) as http:
        sink = LogsIngestionSink(http, "https://receiver.test", "fixture", rule_id="dcr-ok")
        with pytest.raises(ValueError):
            await sink.send(b"x" * 1_000_001)
        await sink.send(b"[]")


async def test_unexpected_204_body_is_not_silently_ignored():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(204, content=b"partial"))
    ) as http:
        with pytest.raises(ExportError):
            await LogsIngestionSink(http, "https://receiver.test", "fixture", rule_id="dcr-ok").send(b"[{}]")


def test_schema_assets_match_encoded_record():
    record = DecisionRecord(
        tool_call_id=UUID(int=1),
        session_id=UUID(int=2),
        occurred_at="2026-07-01T00:00:00Z",
        coverage_state="not_evaluated",
        content_state="scrubbed",
    )
    body = json.loads(encode_record(record))
    fixtures = files("watcher_microsoft_sentinel").joinpath("config")
    dcr = json.loads((fixtures / "dcr.json").read_text())["properties"]
    columns = dcr["streamDeclarations"]["Custom-WatcherDecisions"]["columns"]
    table = json.loads((fixtures / "table.json").read_text())["properties"]["schema"]
    assert {column["name"] for column in columns} == set(body)
    assert table["columns"] == columns and table["name"] == "WatcherDecisions_CL"
    assert dcr["dataFlows"][0]["outputStream"] == "Custom-WatcherDecisions_CL"
    assert body["SeverityScore"] is None and body["DecisionCategory"] is None


async def test_hyphenated_custom_stream_uses_exact_local_http_path(http_fixture):
    requests = []

    def handler(method, path, headers, body):
        assert method == "POST"
        assert path == "/dataCollectionRules/dcr-fixture/streams/Custom-Watcher-Decisions?api-version=2023-01-01"
        assert headers["Authorization"] == "Bearer fixture"
        requests.append(json.loads(body))
        return 204, {}, b""

    async with http_fixture(handler) as endpoint, httpx.AsyncClient(trust_env=False) as http:
        sink = LogsIngestionSink(http, endpoint, "fixture", rule_id="dcr-fixture", stream="Custom-Watcher-Decisions")
        await sink.send(b'[{"fixture":true}]')
    assert requests == [[{"fixture": True}]]


@pytest.mark.parametrize("stream", ["Custom-", "Custom-a?key=1", "Custom-a#fragment", "Custom-a b", "Custom-a/b"])
def test_custom_stream_stays_one_safe_path_segment(stream):
    with pytest.raises(ValueError):
        LogsIngestionSink(httpx.AsyncClient(), "https://receiver.test", "fixture", rule_id="dcr-ok", stream=stream)


def test_historical_occurrence_time_has_an_independent_column():
    record = DecisionRecord(
        tool_call_id=UUID(int=1),
        session_id=UUID(int=2),
        occurred_at="2001-02-03T04:05:06Z",
        coverage_state="not_evaluated",
        content_state="scrubbed",
    )
    body = json.loads(encode_record(record))
    assert body["TimeGenerated"] == "2001-02-03T04:05:06+00:00"
    assert body["OccurredAt"] == "2001-02-03T04:05:06+00:00"
