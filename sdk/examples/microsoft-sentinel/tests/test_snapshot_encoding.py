"""Verify session/transcript rows against the packaged Azure table and DCR contracts."""

import json
from datetime import UTC, datetime
from importlib.resources import files
from uuid import UUID

import pytest
from watcher_microsoft_sentinel import SessionSnapshot, encode_record


@pytest.mark.parametrize("kind", ["session_summary", "transcript"])
def test_azure_snapshot_rows_match_table_and_dcr(kind):
    record = SessionSnapshot(
        session_id=UUID("68c777a8-48d8-4ebf-8992-6d9b5c770b60"),
        occurred_at=datetime(2026, 9, 1, tzinfo=UTC),
        record_type=kind,
        trajectory_id="native-hash" if kind == "transcript" else None,
        payload={"messages": [{"role": "user", "content": "Explicit fixture content"}]}
        if kind == "transcript"
        else {"max_score": 9},
    )
    row = json.loads(encode_record(record))
    assert row["RecordType"] == kind and row["Snapshot"] == record.payload
    assert row["ToolCallId"] is None
    table = json.loads(files("watcher_microsoft_sentinel").joinpath("config/table.json").read_text())
    dcr = json.loads(files("watcher_microsoft_sentinel").joinpath("config/dcr.json").read_text())
    columns = {item["name"]: item["type"] for item in table["properties"]["schema"]["columns"]}
    assert set(row) == set(columns) and columns["Snapshot"] == "dynamic"
    assert columns == {
        item["name"]: item["type"]
        for item in dcr["properties"]["streamDeclarations"]["Custom-WatcherDecisions"]["columns"]
    }
