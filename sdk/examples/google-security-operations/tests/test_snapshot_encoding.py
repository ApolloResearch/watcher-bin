"""Check UDM snapshots without inventing threat detections or human identities."""

import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from google.protobuf.json_format import ParseDict
from google.protobuf.struct_pb2 import Struct
from watcher_google_security_operations import SessionSnapshot, encode_records


@pytest.mark.parametrize("kind", ["session_summary", "transcript"])
def test_udm_generic_event_preserves_snapshot_fields(kind):
    record = SessionSnapshot(
        session_id=UUID("68c777a8-48d8-4ebf-8992-6d9b5c770b60"),
        occurred_at=datetime(2026, 9, 1, tzinfo=UTC),
        record_type=kind,
        trajectory_id="native-hash" if kind == "transcript" else None,
        payload={"messages": [{"role": "user", "content": "Explicit fixture content"}]}
        if kind == "transcript"
        else {"max_score": 9},
    )
    event = json.loads(encode_records([record]))["inlineSource"]["events"][0]["udm"]
    assert event["metadata"]["eventType"] == "GENERIC_EVENT"
    assert event["metadata"]["productEventType"] == kind
    assert event["additional"]["watcher_snapshot"] == record.payload
    assert event["additional"]["watcher_record_fingerprint"] == record.fingerprint()
    assert not {"securityResult", "principal", "target"} & event.keys()
    assert ParseDict(event["additional"], Struct())
