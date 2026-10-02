"""Verify conversion of a captured network-contained Goose 1.50.0 session."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from watcher_goose.enforcement import pending_messages
from watcher_goose.integration import convert


def test_native_shell_result_and_final_tail():
    records = json.loads((Path(__file__).parent / "fixtures/native-recording.json").read_text())
    messages = convert(records)
    results = [message for message in messages if message["role"] == "tool"]
    assert len(results) == 1
    assert results[0]["tool_call_id"] == "sdk50-native-call"
    assert results[0]["content"][0]["text"] == "/tmp/native-workspace"
    assert "error" not in results[0]
    assert messages[-1]["content"][0]["text"] == "sdk50 native completed"


@pytest.mark.parametrize("call_already_recorded", [False, True])
def test_pending_snapshot_matches_completed_native_history_prefix(call_already_recorded):
    """Goose may invoke its hook before persisting the assistant's pending call."""
    records = json.loads((Path(__file__).parent / "fixtures/native-recording.json").read_text())
    index, native = next(
        (index, part)
        for index, record in enumerate(records)
        for part in record["content"]
        if part["type"] == "toolRequest"
    )
    call = {
        "id": native["id"],
        "function": native["toolCall"]["value"]["name"],
        "arguments": native["toolCall"]["value"]["arguments"],
    }
    prefix = convert(records[: index + int(call_already_recorded)])
    original = deepcopy(prefix)
    pending = pending_messages(prefix, call)
    completed = convert(records)
    assert pending == completed[: len(pending)]
    assert prefix == original
    assert completed[len(pending)]["role"] == "tool"
    assert completed[len(pending)]["tool_call_id"] == call["id"]
