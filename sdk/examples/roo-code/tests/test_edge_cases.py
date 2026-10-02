"""Native format edge cases that must not silently lose or mislink context."""

import json
from copy import deepcopy
from pathlib import Path

from watcher_roo_code_bridge.integration import convert

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "fixture.json").read_text())


def test_ui_updates_replace_instead_of_duplicate():
    update = deepcopy(FIXTURE[-1])
    update["action"] = "updated"
    update["message"]["text"] = "changed"
    messages = convert(FIXTURE + [update])
    assert len(messages) == 2
    assert messages[-1]["content"] == "changed"


def test_partial_and_nonchat_ui_rows_are_excluded():
    update = deepcopy(FIXTURE[-1])
    update["message"]["partial"] = True
    assert len(convert(FIXTURE + [update])) == 1
    update["message"]["partial"] = False
    update["message"]["say"] = "api_req_started"
    assert len(convert(FIXTURE + [update])) == 1
