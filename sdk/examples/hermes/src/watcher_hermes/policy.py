"""Turn Watcher's answer for one pending Hermes tool call into a ``pre_tool_call`` directive.

Hermes shell hooks answer ``pre_tool_call`` on stdout:

- ``{}`` lets the call continue to Hermes's own approval checks;
- ``{"action": "block", "message": ...}`` refuses it and shows the message to the model;
- ``{"action": "approve", "message": ..., "rule_key": ...}`` sends it to Hermes's human
  approval prompt, the same gate dangerous shell commands use. Where no person can answer
  (gateway without an approval bridge, piped runs), Hermes refuses the call.

Watcher's enforce-mode ``allow`` maps to ``{}``, ``deny`` to block and ``escalate`` to
approve. Observe and paused modes return ``deferred``, which also maps to ``{}``: Hermes's
own permissions decide. Any answer that is incomplete, inconsistent or names another call
blocks, because the gate cannot tell what Watcher decided.
"""

from typing import Any
from uuid import uuid4

JUDGED_SOURCES = {"threshold", "rule", "triage", "policy_gateway", "grading_error"}
GRADING_FAILURES = {"timeout", "at_capacity", "allowance_exhausted", "grader_failed", "no_result"}

PROCEED: dict[str, Any] = {}


def block(message: str) -> dict[str, Any]:
    """Return the directive that refuses the pending call with ``message``."""
    return {"action": "block", "message": message}


def _explanation(outcome: dict[str, Any]) -> str:
    verdict = outcome.get("verdict")
    if not isinstance(verdict, dict):
        verdict = {}
    parts = [verdict.get("summary"), verdict.get("explanation")]
    text = ". ".join(p.strip().rstrip(".") for p in parts if isinstance(p, str) and p.strip())
    return text[:600] if text else "No explanation was given"


def directive(outcome: dict[str, Any], tool_call_id: str, *, escalate_as_block: bool = False) -> dict[str, Any]:
    """Validate one serialized ``PreToolUseHookResponse`` and return the Hermes directive.

    Raises ``PermissionError`` for an answer the gate cannot trust; the caller
    turns that into a block. ``rule_key`` on an escalation is a fresh random
    value for every request: Hermes remembers "session" and "always" answers
    by that key (the latter across sessions), and tool-call IDs can repeat
    between sessions, so a reusable key would let one answer approve a later,
    different escalation without asking. Those answers therefore cover only
    the call they were given for.

    Hermes approves an escalation without asking anyone when its own approvals
    are switched off (``--yolo``, ``approvals.mode: off``, or an unattended
    mode set to ``approve``). ``escalate_as_block`` refuses escalated calls
    instead, for deployments where that must not happen.
    """
    if outcome.get("tool_use_id") != tool_call_id:
        raise PermissionError("Watcher returned another call's decision")
    source, failure = outcome.get("decision_source"), outcome.get("grading_error")
    if source == "grading_error":
        if (
            not isinstance(failure, dict)
            or failure.get("code") not in GRADING_FAILURES
            or not isinstance(failure.get("message"), str)
        ):
            raise PermissionError("Watcher returned invalid grading-failure details")
    elif failure is not None:
        raise PermissionError("Watcher returned inconsistent grading details")
    decision, mode, judged = outcome.get("decision"), outcome.get("enforcement_mode"), outcome.get("judged_decision")
    if decision == "deferred":
        if mode == "paused" and source == "bypass" and judged is None:
            return PROCEED
        if mode == "observe" and source in JUDGED_SOURCES and judged in {"allow", "deny", "escalate"}:
            return PROCEED
        raise PermissionError("Watcher returned an inconsistent deferred decision")
    if mode != "enforce" or source not in JUDGED_SOURCES or decision not in {"allow", "deny", "escalate"}:
        raise PermissionError("Watcher returned an inconsistent decision")
    if judged != decision:
        raise PermissionError("Watcher returned an inconsistent decision")
    if decision == "allow":
        return PROCEED
    explanation = _explanation(outcome)
    if decision == "deny":
        return block(f"Watcher denied this tool call: {explanation}")
    if escalate_as_block:
        return block(f"Watcher requires a person to approve this tool call, so it was blocked: {explanation}")
    return {
        "action": "approve",
        "message": f"Watcher asks for your approval: {explanation}",
        "rule_key": f"watcher:{uuid4().hex}",
    }
