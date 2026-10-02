"""Native format edge cases that must not silently lose or mislink context."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from watcher_qwen_code.integration import convert

FIXTURE = json.loads((Path(__file__).parent / "fixtures/fixture.json").read_text())


def test_missing_parallel_response_id_is_not_guessed_from_name():
    rows = deepcopy(FIXTURE)
    del rows[2]["message"]["parts"][0]["functionResponse"]["id"]
    with pytest.raises(KeyError):
        convert(rows)


def test_branch_rewind_is_explicit():
    with pytest.raises(ValueError):
        convert(FIXTURE + [{"type": "system", "subtype": "rewind"}])
