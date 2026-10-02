"""Verify HEC envelopes for explicit session/transcript export."""

import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from watcher_splunk import SessionSnapshot, encode_event


@pytest.mark.parametrize("kind", ["session_summary", "transcript"])
def test_hec_identifies_snapshot_class_and_retains_native_payload(kind):
    record = SessionSnapshot(
        session_id=UUID("68c777a8-48d8-4ebf-8992-6d9b5c770b60"),
        occurred_at=datetime(2026, 9, 1, tzinfo=UTC),
        record_type=kind,
        trajectory_id="native-hash" if kind == "transcript" else None,
        payload={"messages": [{"role": "user", "content": "Explicit fixture content"}]}
        if kind == "transcript"
        else {"max_score": 9},
    )
    event = json.loads(encode_event(record, index="watcher"))
    assert event["sourcetype"] == "watcher:" + kind
    assert event["event"]["event_type"] == "watcher." + kind
    assert event["event"]["payload"] == record.payload
    assert event["event"]["record_fingerprint"] == record.fingerprint()
    assert "tool_call_id" not in event["event"]
    assert event["index"] == "watcher"
