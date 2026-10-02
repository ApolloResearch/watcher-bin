"""Native format edge cases that must not silently lose or mislink context."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from watcher_opencode_bridge.integration import convert

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "fixture.json").read_text())


def test_running_tool_is_not_reported_as_completed():
    rows = deepcopy(FIXTURE)
    rows[1]["parts"][0]["state"]["status"] = "running"
    with pytest.raises(ValueError):
        convert(rows)


def test_native_tool_error_keeps_call_id():
    rows = deepcopy(FIXTURE)
    state = rows[1]["parts"][0]["state"]
    state["status"] = "error"
    state["error"] = "failed"
    failed = [message for message in convert(rows) if message.get("error")]
    assert failed[0]["tool_call_id"] == "call-a"


def test_unknown_part_is_not_silently_dropped():
    rows = deepcopy(FIXTURE)
    rows[0]["parts"].append({"type": "file", "url": "file:///private"})
    with pytest.raises(ValueError):
        convert(rows)
