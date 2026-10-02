"""Native format edge cases that must not silently lose or mislink context."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from watcher_openclaw_bridge.integration import convert

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "fixture.json").read_text())


def test_custom_role_and_image_block_fail_explicitly():
    with pytest.raises(ValueError):
        convert([{"role": "custom", "content": "unhandled"}])
    rows = deepcopy(FIXTURE)
    rows[1]["content"].append({"type": "image", "data": "AA=="})
    with pytest.raises(ValueError):
        convert(rows)


def test_error_result_is_still_linked():
    rows = deepcopy(FIXTURE)
    rows[2]["isError"] = True
    assert [m["tool_call_id"] for m in convert(rows) if m.get("error")] == ["call-b"]
