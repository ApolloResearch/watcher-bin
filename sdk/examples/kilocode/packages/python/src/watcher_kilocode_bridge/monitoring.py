"""Public SDK observation of captured native tools, followed by a final-tail flush."""

from watcher_sdk import AsyncWatcherClient


def validate_observation(outcome: object, expected_id: str) -> bool:
    """Validate an advisory server outcome and report whether to checkpoint its judgment.

    Inherit the server's effective policy. Historical observations never execute
    or block a native action. Paused bypasses and configured grading-failure
    outcomes are valid but stay eligible for assessment on a later callback.
    Invalid provenance or a mismatched identity raises before it can be cached.
    """
    serialize = getattr(outcome, "to_dict", None)
    if not callable(serialize):
        raise ValueError("Watcher returned an invalid observation outcome")
    result = serialize()
    if not isinstance(result, dict) or result.get("tool_use_id") != expected_id:
        raise ValueError("Watcher returned another call's observation")
    source, failure = result.get("decision_source"), result.get("grading_error")
    if source == "grading_error":
        if (
            not isinstance(failure, dict)
            or failure.get("code")
            not in {"timeout", "at_capacity", "allowance_exhausted", "grader_failed", "no_result"}
            or not isinstance(failure.get("message"), str)
        ):
            raise ValueError("Watcher returned invalid grading-failure provenance")
    elif failure is not None:
        raise ValueError("Watcher returned inconsistent grading provenance")
    decision, mode, judged = result.get("decision"), result.get("enforcement_mode"), result.get("judged_decision")
    if mode == "paused" and decision == "deferred" and source == "bypass" and judged is None:
        return False
    if source not in {"threshold", "rule", "triage", "policy_gateway", "grading_error"} or judged not in {
        "allow",
        "deny",
        "escalate",
    }:
        raise ValueError("Watcher returned an incomplete observation judgment")
    if (mode == "observe" and decision == "deferred") or (mode == "enforce" and decision == judged):
        return source != "grading_error"
    raise ValueError("Watcher returned an inconsistent observation decision")


async def observe(client: AsyncWatcherClient, identity: str, messages: list[dict]) -> None:
    """Evaluate captured tools after execution without changing native permissions.

    Each call is judged using its historical prefix, before any result or future
    assistant reply. Send at most 32 inputs per batch. Native delivery retries may
    replay IDs; do not force regrading. Final text/results are flushed even if a
    judgment fails. Failures propagate to the native observation-only boundary.
    Organization policy is inherited without overrides, including locked and
    paused modes. In active modes, rules and triage run within each request budget;
    the slow gateway grade is skipped. A returned denial or escalation is advisory
    to an action that already finished. Paused mode only records history. Timed-out
    server work can still finish and be billed; no automatic retry is attempted.
    """
    try:
        for index, message in enumerate(messages):
            calls = message.get("tool_calls", [])
            for offset in range(0, len(calls), 32):
                selected = calls[offset : offset + 32]
                inputs = [
                    {"tool_use_id": call["id"], "tool_name": call["function"], "tool_input": call["arguments"]}
                    for call in selected
                ]
                outcomes = await client.pre_tool_use_hook(
                    input=inputs,
                    messages=messages[: index + 1],
                    external_ids={"other": identity},
                    mode="triage_only",
                    timeout=10,
                )
                if not isinstance(outcomes, list) or len(outcomes) != len(inputs):
                    raise ValueError("Watcher returned incomplete observation outcomes")
                for submitted, outcome in zip(inputs, outcomes, strict=True):
                    validate_observation(outcome, submitted["tool_use_id"])
    finally:
        await client.pre_tool_use_hook(
            input=[],
            messages=messages,
            external_ids={"other": identity},
            timeout=10,
        )
