"""Check the actual OTLP wire representation for session and transcript snapshots."""

import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from watcher_opentelemetry import OtlpLogSink, SessionSnapshot, encode_records


def record(kind):
    return SessionSnapshot(
        session_id=UUID("68c777a8-48d8-4ebf-8992-6d9b5c770b60"),
        occurred_at=datetime(2026, 9, 1, tzinfo=UTC),
        record_type=kind,
        trajectory_id="native-hash" if kind == "transcript" else None,
        payload={"messages": [{"role": "user", "content": "Explicit fixture content"}]}
        if kind == "transcript"
        else {"max_score": 9},
    )


@pytest.mark.parametrize("kind", ["session_summary", "transcript"])
async def test_native_otlp_payload_retains_the_selected_record(kind):
    source = record(kind)
    seen = []

    def handler(request):
        decoded = ExportLogsServiceRequest.FromString(request.content)
        log = decoded.resource_logs[0].scope_logs[0].log_records[0]
        assert log.event_name == "watcher." + kind
        assert json.loads(log.body.string_value) == source.payload
        attributes = {attribute.key: attribute.value.string_value for attribute in log.attributes}
        assert attributes["watcher.session_id"] == str(source.session_id)
        assert attributes["watcher.record_fingerprint"] == source.fingerprint()
        assert "watcher.tool_call_id" not in attributes
        if kind == "transcript":
            assert attributes["watcher.trajectory_id"] == "native-hash"
        seen.append(request)
        return httpx.Response(200, content=b"", headers={"Content-Type": "application/x-protobuf"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await OtlpLogSink(http, "http://127.0.0.1:4318/v1/logs").send([source], observed_at=source.occurred_at)
    assert len(seen) == 1


def test_summary_payload_contains_no_transcript_body():
    wire = encode_records([record("session_summary")], observed_at=datetime(2026, 9, 1, tzinfo=UTC))
    assert b"Explicit fixture content" not in wire and b"messages" not in wire
