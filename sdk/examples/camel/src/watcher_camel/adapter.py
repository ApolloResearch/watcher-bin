"""Observe completed native framework histories using only public watcher_sdk APIs.

The caller owns execution and history retention. Conversion rejects unsupported
content instead of silently dropping it. Monitoring happens after execution and
waits for results, so this adapter never prevents a tool's side effects.
"""

import json
from copy import deepcopy

from watcher_sdk import AsyncWatcherClient


def validate(messages):
    """Copy Inspect-compatible messages and reject broken tool/result identities."""
    messages = deepcopy(messages)
    calls = {}
    answered = set()
    for message in messages:
        if message["role"] not in ("system", "user", "assistant", "tool"):
            raise ValueError("Unsupported role")
        if not isinstance(message["content"], str):
            raise ValueError("Only finalized text content is supported")
        for call in message.get("tool_calls", []):
            if not isinstance(call["id"], str) or not call["id"] or call["id"] in calls:
                raise ValueError("Tool IDs must be nonempty and unique")
            if not isinstance(call["arguments"], dict) or not call["function"]:
                raise ValueError("Tool arguments must be objects and names nonempty")
            calls[call["id"]] = call["function"]
        if message["role"] == "tool":
            call_id = message["tool_call_id"]
            if call_id not in calls or call_id in answered:
                raise ValueError("Tool result must match one unanswered call")
            message["function"] = calls[call_id]
            answered.add(call_id)
    return messages


def messages_for_watcher(messages):
    """Convert native ChatAgent.memory.get_context() messages.

    The native export uses Chat Completions dictionaries. Tool pruning must be
    disabled and the retained context must contain original calls for all results.
    """
    result = []
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("Expected native memory messages")
        content = message.get("content") or ""
        if not isinstance(content, str):
            raise ValueError("Only text messages supported")
        item = {"role": message["role"], "content": content}
        if message.get("tool_calls"):
            item["tool_calls"] = [
                {
                    "id": call["id"],
                    "function": call["function"]["name"],
                    "arguments": json.loads(call["function"]["arguments"]),
                }
                for call in message["tool_calls"]
            ]
        if message["role"] == "tool":
            item["tool_call_id"] = message["tool_call_id"]
        result.append(item)
    return validate(result)


class IncompleteObservationError(RuntimeError):
    """Watcher returned an incomplete or inconsistent historical observation."""


def validate_observation(outcome: object, expected_id: str) -> bool:
    """Validate an advisory server outcome and report whether to checkpoint its judgment.

    Inherit the server's effective policy. Historical observations never execute
    or block a native action. Paused bypasses and configured grading-failure
    outcomes are valid but stay eligible for assessment on a later callback.
    Invalid provenance or a mismatched identity raises before it can be cached.
    """
    serialize = getattr(outcome, "to_dict", None)
    if not callable(serialize):
        raise IncompleteObservationError("Watcher returned an invalid observation outcome")
    result = serialize()
    if not isinstance(result, dict) or result.get("tool_use_id") != expected_id:
        raise IncompleteObservationError("Watcher returned another call's observation")
    source, failure = result.get("decision_source"), result.get("grading_error")
    if source == "grading_error":
        if (
            not isinstance(failure, dict)
            or failure.get("code")
            not in {"timeout", "at_capacity", "allowance_exhausted", "grader_failed", "no_result"}
            or not isinstance(failure.get("message"), str)
        ):
            raise IncompleteObservationError("Watcher returned invalid grading-failure provenance")
    elif failure is not None:
        raise IncompleteObservationError("Watcher returned inconsistent grading provenance")
    decision, mode, judged = result.get("decision"), result.get("enforcement_mode"), result.get("judged_decision")
    if mode == "paused" and decision == "deferred" and source == "bypass" and judged is None:
        return False
    if source not in {"threshold", "rule", "triage", "policy_gateway", "grading_error"} or judged not in {
        "allow",
        "deny",
        "escalate",
    }:
        raise IncompleteObservationError("Watcher returned an incomplete observation judgment")
    if (mode == "observe" and decision == "deferred") or (mode == "enforce" and decision == judged):
        return source != "grading_error"
    raise IncompleteObservationError("Watcher returned an inconsistent observation decision")


def completed_outcomes(outcomes, inputs):
    """Retain completed advisory judgments, validating paused and fallback outcomes too."""
    if not isinstance(outcomes, list) or len(outcomes) != len(inputs):
        raise IncompleteObservationError("Watcher did not return one outcome per input")
    return [
        outcome
        for submitted, outcome in zip(inputs, outcomes, strict=True)
        if validate_observation(outcome, submitted["tool_use_id"])
    ]


async def observe_transcript(client: AsyncWatcherClient, conversation_id: str, transcript):
    """Assess validated history prefixes under the server's configured policy.

    Calls from one assistant message share a prefix and are batched by 32.
    Later results and answers are never included when judging an earlier call.
    Always attempt final-tail recording, even after a judgment or validation
    failure. If both fail, the recording error propagates and the judgment error
    remains in its __context__. No native tool is executed or retried here.
    """
    if not conversation_id:
        raise ValueError("conversation_id must be nonempty")
    outcomes = []
    try:
        for index, message in enumerate(transcript):
            calls = message.get("tool_calls", []) if message["role"] == "assistant" else []
            for start in range(0, len(calls), 32):
                inputs = [
                    {"tool_name": call["function"], "tool_input": call["arguments"], "tool_use_id": call["id"]}
                    for call in calls[start : start + 32]
                ]
                batch = await client.pre_tool_use_hook(
                    inputs,
                    messages=transcript[: index + 1],
                    external_ids={"other": f"camel:{conversation_id}"},
                    timeout=420,
                )
                outcomes.extend(completed_outcomes(batch, inputs))
    finally:
        receipt = await client.pre_tool_use_hook(
            None,
            messages=transcript,
            external_ids={"other": f"camel:{conversation_id}"},
            timeout=10,
        )
        if receipt != []:
            raise IncompleteObservationError("Transcript-only recording returned unexpected outcomes")
    return outcomes


async def observe(client: AsyncWatcherClient, conversation_id: str, messages):
    """Convert native history, observe historical tool prefixes and record its tail.

    This runs after tool execution and cannot prevent side effects. It waits for
    completed advisory outcomes, raises on incomplete judgments, and attempts
    final recording even when monitoring fails. Reuse conversation_id and native
    tool IDs for full snapshots of the same conversation.
    """
    return await observe_transcript(client, conversation_id, messages_for_watcher(messages))
