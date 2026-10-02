"""Native format edge cases that must not silently lose or mislink context."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from watcher_amp.integration import convert

FIXTURE = json.loads((Path(__file__).parent / "fixtures/fixture.json").read_text())


def test_compaction_is_not_replayed_as_linear_history():
    with pytest.raises(ValueError):
        convert(FIXTURE + [{"type": "system", "subtype": "compact_boundary"}])


def test_malformed_tool_input_is_not_coerced():
    rows = deepcopy(FIXTURE)
    rows[1]["message"]["content"][0]["input"] = []
    with pytest.raises(ValueError):
        convert(rows)


def test_tool_error_retains_identity():
    rows = deepcopy(FIXTURE)
    rows[2]["message"]["content"][0]["is_error"] = True
    failed = [message for message in convert(rows) if message.get("error")]
    assert failed[0]["tool_call_id"] == "call-b"
