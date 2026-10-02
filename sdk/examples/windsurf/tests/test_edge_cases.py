"""Native format edge cases that must not silently lose or mislink context."""

import json
from pathlib import Path

from watcher_windsurf.integration import convert

FIXTURE = json.loads((Path(__file__).parent / "fixtures/fixture.json").read_text())


def test_action_payload_is_retained_without_false_tool_linkage():
    messages = convert(FIXTURE)
    assert messages[1]["metadata"]["native_step"] == FIXTURE[1]
    assert "tool_calls" not in messages[1]


def test_opaque_step_data_is_detached():
    messages = convert(FIXTURE)
    messages[1]["metadata"]["native_step"]["code_action"]["path"] = "different"
    assert FIXTURE[1]["code_action"]["path"] == "hello.py"
