"""Apply Watcher policy before the native callback permits a tool.

Completion observation remains in integration.py. This module never executes a
native tool and must be awaited at its pre-execution callback.
"""

import json
import math
import os
from copy import deepcopy

from watcher_sdk import AsyncWatcherClient


def canonical_json(value: object) -> str:
    """Compare JSON values without Python's boolean/number equality or coercions.

    Native inputs must contain only JSON objects with string keys, arrays and
    finite scalar values. Reject tuples, arbitrary objects and NaN/infinity
    rather than silently converting them to a different executable argument.
    """

    def validate(item: object) -> None:
        if item is None or type(item) in {str, bool, int}:
            return
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError("Non-finite tool arguments are not supported")
            return
        if type(item) is list:
            for child in item:
                validate(child)
            return
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("Tool argument object keys must be strings")
            for child in item.values():
                validate(child)
            return
        raise ValueError("Tool arguments must contain only supported JSON values")

    validate(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def pending_messages(messages: list[dict], call: dict) -> list[dict]:
    """Return a snapshot containing this pending call with its native identity.

    A native callback may precede transcript persistence; append its exact call
    only when absent. Existing identities must match, and a result for this call
    is forbidden: completed work must use the independent observation example.
    The input snapshot is never mutated.
    """
    if not all(isinstance(call.get(key), str) and call[key] for key in ("id", "function")):
        raise ValueError("A native tool ID and name are required")
    if not isinstance(call.get("arguments"), dict):
        raise ValueError("Native tool arguments must be an object")
    arguments = canonical_json(call["arguments"])
    result = deepcopy(messages)
    found = [c for m in result for c in m.get("tool_calls", []) if c["id"] == call["id"]]
    if any(m.get("tool_call_id") == call["id"] for m in result):
        raise ValueError("This tool has already produced a result")
    if found and (
        len(found) != 1
        or any(found[0].get(k) != call[k] for k in ("id", "function"))
        or canonical_json(found[0].get("arguments")) != arguments
    ):
        raise ValueError("Native callback and transcript tool identities disagree")
    if not found:
        result.append({"role": "assistant", "content": "", "tool_calls": [deepcopy(call)]})
    return result


async def apply_policy(
    client: AsyncWatcherClient, session_id: str, messages: list[dict], call: dict, *, cwd: str | None = None
) -> None:
    """Apply one matching server decision before native tool execution.

    Pass cwd only when supplied by the native hook/context; it is omitted otherwise.
    Inherit organization policy. Enforce allows resume native dispatch, including
    configured grading-failure allows. Observe/paused deferrals preserve the
    harness's ordinary permission checks. Denials and escalations block because
    this hook does not supply a human approval UI. Invalid or mismatched outcomes
    and transport failures never grant permission. Hook acceptance is not proof
    of durable recording; query Watcher to verify persisted messages and decisions.
    WATCHER_TIMEOUT_SECONDS defaults to 420; the native callback deadline must
    exceed this plus transcript loading. Timed-out grades may still finish and
    incur cost; no retry or cancellation of server work is attempted.
    """
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("A native session ID is required")
    timeout = float(os.environ.get("WATCHER_TIMEOUT_SECONDS", "420"))
    if not math.isfinite(timeout) or not 0 < timeout <= 420:
        raise ValueError("WATCHER_TIMEOUT_SECONDS must be greater than zero and at most 420")
    submitted = {"tool_use_id": call["id"], "tool_name": call["function"], "tool_input": call["arguments"]}
    if cwd is not None:
        if not isinstance(cwd, str) or not cwd:
            raise ValueError("Native working directory must be a nonempty string")
        submitted["cwd"] = cwd
    outcomes = await client.pre_tool_use_hook(
        input=[submitted],
        messages=pending_messages(messages, call),
        external_ids={"other": PREFIX + session_id},
        mode="full",
        timeout=timeout,
    )
    if not isinstance(outcomes, list) or len(outcomes) != 1:
        raise PermissionError("Watcher approval was incomplete")
    serialize = getattr(outcomes[0], "to_dict", None)
    if not callable(serialize):
        raise PermissionError("Watcher returned an invalid tool outcome")
    outcome = serialize()
    if outcome.get("tool_use_id") != call["id"]:
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


PREFIX = "aider:"
