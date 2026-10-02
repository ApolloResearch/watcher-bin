"""Native format edge cases that must not silently lose or mislink context."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from watcher_aider.integration import convert

FIXTURE = json.loads((Path(__file__).parent / "fixtures/fixture.json").read_text())


def test_compacted_or_attached_history_is_not_flattened():
    for field, value in [("images", [{"data": "AA=="}]), ("context_boundary", "compaction")]:
        rows = deepcopy(FIXTURE)
        rows[0][field] = value
        with pytest.raises(ValueError):
            convert(rows)
