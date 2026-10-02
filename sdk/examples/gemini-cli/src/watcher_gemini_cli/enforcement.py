"""Opt-in ephemeral pre-tool veto using the public Watcher SDK.

No pending transcript, grade row or decision record is stored by this call.
The independent completion observer records native history after execution.
"""

import math
import os
from copy import deepcopy

from watcher_sdk import AsyncWatcherClient


def require_opt_in():
    """Fail closed unless the operator explicitly enabled unrecorded pre-tool grading."""
    if os.environ.get("WATCHER_EPHEMERAL_PRE_TOOL") != "1":
        raise PermissionError("Set WATCHER_EPHEMERAL_PRE_TOOL=1 to use the ephemeral veto")


async def apply_policy(client: AsyncWatcherClient, session_id: str, messages: list[dict], call: dict) -> None:
    """Apply inherited Watcher policy without recording an early transcript.

    Valid observe/paused deferrals preserve native dispatch. Denials, escalations,
    malformed results and transport errors withhold execution. Configured
    grading-failure allows are honored.

    The native call ID may be absent; never invent one or match repeated calls by
    name/arguments. An available ID must be echoed exactly. This is an explicit
    ephemeral integration, never a fallback after recorded monitoring fails.
    """
    require_opt_in()
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("A native session ID is required")
    if not isinstance(call.get("function"), str) or not call["function"].strip():
        raise ValueError("A native tool name is required")
    if not isinstance(call.get("arguments"), dict):
        raise ValueError("Native tool arguments must be an object")
    call_id = call.get("id")
    if call_id is not None and (not isinstance(call_id, str) or not call_id):
        raise ValueError("A supplied native tool ID must be nonempty")
    timeout = float(os.environ.get("WATCHER_TIMEOUT_SECONDS", "420"))
    if not math.isfinite(timeout) or not 0 < timeout <= 420:
        raise ValueError("WATCHER_TIMEOUT_SECONDS must be greater than zero and at most 420")
    submitted = {"tool_name": call["function"], "tool_input": deepcopy(call["arguments"])}
    if call_id is not None:
        submitted["tool_use_id"] = call_id
    outcome = await client.pre_tool_use_hook(
        input=submitted,
        messages=deepcopy(messages),
        external_ids={"other": "gemini-cli:" + session_id},
        ephemeral=True,
        mode="full",
        timeout=timeout,
    )
    if isinstance(outcome, list):
        raise PermissionError("Watcher returned an unexpected batch response")
    serialize = getattr(outcome, "to_dict", None)
    if not callable(serialize):
        raise PermissionError("Watcher returned an invalid tool outcome")
    outcome = serialize()
    if outcome.get("tool_use_id") != call_id:
        raise PermissionError("Watcher returned another call's decision")
    source, failure = outcome.get("decision_source"), outcome.get("grading_error")
    if source == "grading_error":
        if (
            not isinstance(failure, dict)
            or failure.get("code")
            not in {"timeout", "at_capacity", "allowance_exhausted", "grader_failed", "no_result"}
            or not isinstance(failure.get("message"), str)
        ):
            raise PermissionError("Watcher returned invalid grading-failure provenance")
    elif failure is not None:
        raise PermissionError("Watcher returned inconsistent grading provenance")
    decision, mode = outcome.get("decision"), outcome.get("enforcement_mode")
    if decision == "deferred":
        if mode == "paused" and source == "bypass" and outcome.get("judged_decision") is None:
            return
        if (
            mode == "observe"
            and source in {"threshold", "rule", "triage", "policy_gateway", "grading_error"}
            and outcome.get("judged_decision") in {"allow", "deny", "escalate"}
        ):
            return
        raise PermissionError("Watcher returned an inconsistent deferred decision")
    if (
        mode != "enforce"
        or source not in {"threshold", "rule", "triage", "policy_gateway", "grading_error"}
        or decision not in {"allow", "deny", "escalate"}
        or outcome.get("judged_decision") != decision
    ):
        raise PermissionError("Watcher returned an inconsistent applied decision")
    if decision != "allow":
        raise PermissionError("Watcher withheld this call; no human approval interface is configured")
