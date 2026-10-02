"""Grade a recorded turn's tool calls retrospectively within a bounded callback."""

import asyncio
import math

from pydantic import JsonValue, ValidationError

from watcher_github_copilot_cli.transcript import NativeModel
from watcher_sdk import AsyncWatcherClient


class GradingFailure(NativeModel):
    code: str
    message: str


class PolicyOutcome(NativeModel):
    tool_use_id: str | None = None
    decision_source: str | None = None
    grading_error: GradingFailure | None = None
    decision: str | None = None
    enforcement_mode: str | None = None
    judged_decision: str | None = None


_SOURCES = {"threshold", "rule", "triage", "policy_gateway", "grading_error"}
_JUDGMENTS = {"allow", "deny", "escalate"}
_GRADING_FAILURES = {"timeout", "at_capacity", "allowance_exhausted", "grader_failed", "no_result"}


def applied_decision(outcome: object, tool_use_id: str | None) -> str:
    """Validate one server outcome for the call ``tool_use_id`` and return its applied decision.

    Inherit the server's effective policy. ``deferred`` means Watcher observed the
    call, or its paused mode did not grade it; otherwise the decision is the
    enforced judgment. Configured grading-failure outcomes are valid. Invalid
    provenance or another call's identity raises ``ValueError``.
    """
    serialize = getattr(outcome, "to_dict", None)
    if not callable(serialize):
        raise ValueError("Watcher returned an invalid tool outcome")
    try:
        result = PolicyOutcome.model_validate(serialize())
    except ValidationError:
        raise ValueError("Watcher returned an invalid tool outcome") from None
    if result.tool_use_id != tool_use_id:
        raise ValueError("Watcher returned another call's decision")
    source, failure = result.decision_source, result.grading_error
    if (source == "grading_error") != (failure is not None) or (failure and failure.code not in _GRADING_FAILURES):
        raise ValueError("Watcher returned inconsistent grading provenance")
    decision, mode, judged = result.decision, result.enforcement_mode, result.judged_decision
    if decision == "deferred" and mode == "paused" and source == "bypass" and judged is None:
        return decision
    if source not in _SOURCES or judged not in _JUDGMENTS:
        raise ValueError("Watcher returned an incomplete judgment")
    if mode == "observe" and decision == "deferred":
        return decision
    if mode == "enforce" and decision == judged:
        return judged
    raise ValueError("Watcher returned an inconsistent decision")


async def assess(
    client: AsyncWatcherClient,
    identity: str,
    messages: list[dict[str, JsonValue]],
    *,
    start: int = 0,
    budget_seconds: float = 40,
) -> None:
    """Check the calls in ``messages[start:]``, the turn just recorded, against inherited policy.

    Server policy is inherited without overrides; paused mode does no grading.
    Returned denials or escalations cannot block actions that already finished.

    Each call retains its historical prefix; only calls from the same assistant
    message share a batch, with at most 32 inputs. The public SDK evaluates a
    batch against one shared conversation, so different historical prefixes must
    not be combined. Earlier turns were assessed by their own callbacks, so
    resending them would only upload ever longer prefixes. Watcher reuses a
    completed judgment with the same native ID, name and arguments, so a retried
    callback usually does not grade a call again; requests that overlap before
    the first decision is stored can.

    The work has a 40-second budget. A timeout or failed judgment raises; a turn
    whose callback failed is not assessed by later callbacks. Timed-out server
    work can still finish and be billed; this function performs no immediate retry.
    """
    if not math.isfinite(budget_seconds) or not 0 < budget_seconds <= 40:
        raise ValueError("Observation budget must be greater than zero and at most 40 seconds")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + budget_seconds
    async with asyncio.timeout_at(deadline):
        for index in range(start, len(messages)):
            tool_calls = messages[index].get("tool_calls")
            calls = [call for call in (tool_calls if isinstance(tool_calls, list) else []) if isinstance(call, dict)]
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
                    # Watcher's own triage limit is ten seconds, so a request must be
                    # allowed longer than that to receive a timed-out grade's outcome.
                    timeout=max(deadline - loop.time(), 0.001),
                )
                if not isinstance(outcomes, list) or len(outcomes) != len(inputs):
                    raise ValueError("Watcher returned incomplete observation outcomes")
                for call, outcome in zip(selected, outcomes, strict=True):
                    applied_decision(outcome, str(call["id"]))
