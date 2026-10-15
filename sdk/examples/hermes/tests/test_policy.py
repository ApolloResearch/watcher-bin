"""Every Watcher outcome maps to exactly one Hermes pre_tool_call directive, and doubtful ones block."""

import pytest
from watcher_hermes.policy import PROCEED, directive


def outcome(**changes):
    base = {
        "tool_use_id": "c1",
        "decision": "allow",
        "judged_decision": "allow",
        "enforcement_mode": "enforce",
        "decision_source": "triage",
        "verdict": {"summary": "Triage: risky", "explanation": "Deletes files."},
        "latency_ms": 1,
    }
    base.update(changes)
    return {k: v for k, v in base.items() if v is not ...}


def test_enforce_allow_proceeds():
    assert directive(outcome(), "c1") == PROCEED


def test_enforce_deny_blocks_with_watcher_reason():
    result = directive(outcome(decision="deny", judged_decision="deny"), "c1")
    assert result == {"action": "block", "message": "Watcher denied this tool call: Triage: risky. Deletes files"}


def test_enforce_escalate_asks_hermes_prompt_with_a_key_that_never_repeats():
    result = directive(outcome(decision="escalate", judged_decision="escalate"), "c1")
    assert result["action"] == "approve"
    again = directive(outcome(decision="escalate", judged_decision="escalate"), "c1")
    assert result["rule_key"].startswith("watcher:") and result["rule_key"] != again["rule_key"]
    assert "Deletes files" in result["message"]


def test_escalate_as_block_refuses():
    result = directive(outcome(decision="escalate", judged_decision="escalate"), "c1", escalate_as_block=True)
    assert result["action"] == "block" and "requires a person" in result["message"]


def test_missing_explanation_has_fallback_text():
    result = directive(outcome(decision="deny", judged_decision="deny", verdict=None), "c1")
    assert result["message"].endswith("No explanation was given")


@pytest.mark.parametrize(
    "changes",
    [
        {"decision": "deferred", "enforcement_mode": "observe", "judged_decision": "deny"},
        {"decision": "deferred", "enforcement_mode": "paused", "decision_source": "bypass", "judged_decision": None},
        {
            "decision_source": "grading_error",
            "grading_error": {"code": "timeout", "message": "Grading timed out"},
        },
    ],
)
def test_deferred_and_configured_grading_failure_outcomes_proceed(changes):
    assert directive(outcome(**changes), "c1") == PROCEED


@pytest.mark.parametrize(
    "changes",
    [
        {"tool_use_id": "another"},
        {"decision_source": "grading_error", "grading_error": None},
        {"decision_source": "grading_error", "grading_error": {"code": "novel", "message": "x"}},
        {"grading_error": {"code": "timeout", "message": "x"}},
        {"decision": "deferred", "enforcement_mode": "observe", "judged_decision": None},
        {"decision": "deferred", "enforcement_mode": "enforce"},
        {"enforcement_mode": "observe"},
        {"decision_source": "unknown-stage"},
        {"decision": "maybe", "judged_decision": "maybe"},
        {"judged_decision": "deny"},
        {"judged_decision": ...},
    ],
)
def test_inconsistent_outcomes_raise(changes):
    with pytest.raises(PermissionError):
        directive(outcome(**changes), "c1")
