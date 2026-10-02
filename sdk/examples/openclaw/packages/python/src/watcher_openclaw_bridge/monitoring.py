"""Record the final conversation, then grade new calls within a bounded callback."""

import asyncio
import math
from pathlib import Path

from watcher_openclaw_bridge.checkpoint import call_fingerprint, open_checkpoint
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


async def observe(
    client: AsyncWatcherClient,
    identity: str,
    messages: list[dict],
    *,
    checkpoint_path: Path | None = None,
    budget_seconds: float = 40,
) -> None:
    """Record the snapshot first, then check calls not successfully observed before.

    Server policy is inherited without overrides; paused mode does no grading.
    Returned denials or escalations cannot block actions that already finished.
    Paused and grading-failure outcomes are not checkpointed, so a later callback
    can assess them under resumed policy.

    Each call retains its historical prefix; only calls from the same assistant
    message share a batch, with at most 32 inputs. The public SDK evaluates a
    batch against one shared conversation, so different historical prefixes must
    not be combined. Native IDs, names and arguments form the checkpoint key.

    The work has a 40-second budget, plus up to two seconds to stop its checkpoint
    worker. The work budget includes the initial
    transcript-only request. A timeout or failed judgment raises after keeping
    completed checkpoints; a later callback resumes unfinished checks. A final
    turn can therefore be recorded before all tool judgments are complete.
    A failed initial recording does not attempt grading. Timed-out server work
    can still finish and be billed; this function performs no immediate retry.
    """
    if not math.isfinite(budget_seconds) or not 0 < budget_seconds <= 40:
        raise ValueError("Observation budget must be greater than zero and at most 40 seconds")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + budget_seconds
    async with asyncio.timeout_at(deadline):
        await client.pre_tool_use_hook(
            input=[],
            messages=messages,
            external_ids={"other": identity},
            timeout=min(10, budget_seconds),
        )
        async with open_checkpoint(checkpoint_path) as checkpoint:
            for index, message in enumerate(messages):
                calls = [
                    call for call in message.get("tool_calls", []) if call_fingerprint(call) not in checkpoint.completed
                ]
                for offset in range(0, len(calls), 32):
                    selected = calls[offset : offset + 32]
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        raise TimeoutError("Observation deadline reached")
                    inputs = [
                        {"tool_use_id": call["id"], "tool_name": call["function"], "tool_input": call["arguments"]}
                        for call in selected
                    ]
                    outcomes = await client.pre_tool_use_hook(
                        input=inputs,
                        messages=messages[: index + 1],
                        external_ids={"other": identity},
                        mode="triage_only",
                        timeout=min(10, remaining),
                    )
                    if not isinstance(outcomes, list) or len(outcomes) != len(inputs):
                        raise ValueError("Watcher returned incomplete observation outcomes")
                    completed = set()
                    has_invalid_outcome = False
                    for call, outcome in zip(selected, outcomes, strict=True):
                        try:
                            if validate_observation(outcome, call["id"]):
                                completed.add(call_fingerprint(call))
                        except ValueError:
                            has_invalid_outcome = True
                    await checkpoint.save(completed)
                    if has_invalid_outcome:
                        raise ValueError("Watcher returned an invalid tool observation")
