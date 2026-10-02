"""Native conversion rejects ambiguous identities rather than inventing links."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from watcher_pi_bridge.integration import convert

FIXTURE = json.loads((Path(__file__).parent / "fixtures/fixture.json").read_text())


def test_duplicate_pending_ids_and_repeated_results_are_rejected():
    rows = deepcopy(FIXTURE)
    rows[1]["content"][1]["id"] = "call-a"
    with pytest.raises(ValueError):
        convert(rows)
    rows = deepcopy(FIXTURE)
    rows.insert(3, deepcopy(rows[2]))
    with pytest.raises(ValueError):
        convert(rows)


def test_unmatched_result_is_rejected():
    with pytest.raises(ValueError):
        convert(FIXTURE[2:])
