"""Publish completed LangGraph histories using the public Watcher SDK.

Call ``observe`` after each completed application turn, including its final tools
and answer. Full snapshots preserve history across turns; this observer does not
gate execution. Text and function calls are supported; unsupported multimodal
blocks and streaming chunks fail explicitly instead of being silently discarded.
"""

from collections.abc import Sequence
from copy import deepcopy

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    BaseMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from watcher_sdk import AsyncWatcherClient


def messages_for_watcher(messages: Sequence[BaseMessage]):
    """Copy a complete native history, preserving tool IDs and text blocks.

    Supply finalized messages only. Raises ValueError for missing/duplicate tool
    IDs, unmatched results, invalid tool calls, or unsupported message/content
    types. Anthropic tool_use blocks must match native call IDs, names and inputs;
    their duplicate representation is recorded once. Results may finish in any order.
    """
    result = []
    calls: dict[str, str] = {}
    answered: set[str] = set()
    for message in messages:
        if isinstance(message, BaseMessageChunk):
            raise ValueError("Finish streaming before publishing a snapshot")
        if isinstance(message.content, str):
            content = message.content
        else:
            pieces = []
            content_call_ids = set()
            for block in message.content:
                if isinstance(block, str):
                    pieces.append(block)
                elif block.get("type") == "text" and isinstance(block.get("text"), str):
                    pieces.append(block["text"])
                elif isinstance(message, AIMessage) and block.get("type") == "tool_use":
                    matching = [call for call in message.tool_calls if call["id"] == block.get("id")]
                    if (
                        len(matching) != 1
                        or matching[0]["name"] != block.get("name")
                        or matching[0]["args"] != block.get("input")
                        or block["id"] in content_call_ids
                    ):
                        raise ValueError("Content tool use must match one native tool call exactly")
                    content_call_ids.add(block["id"])
                else:
                    raise ValueError("Only text content is supported")
            content = "".join(pieces)
        if isinstance(message, AIMessage):
            if message.invalid_tool_calls:
                raise ValueError("Invalid tool-call arguments")
            item: dict = {"role": "assistant", "content": content}
            tools = []
            for call in message.tool_calls:
                if not call["id"] or call["id"] in calls:
                    raise ValueError("Tool IDs must be nonempty and unique in this history")
                calls[call["id"]] = call["name"]
                tools.append({"id": call["id"], "function": call["name"], "arguments": deepcopy(call["args"])})
            if tools:
                item["tool_calls"] = tools
        elif isinstance(message, ToolMessage):
            if message.tool_call_id not in calls or message.tool_call_id in answered:
                raise ValueError("Tool result must match one unanswered call")
            answered.add(message.tool_call_id)
            item: dict = {
                "role": "tool",
                "content": content,
                "tool_call_id": message.tool_call_id,
                "function": calls[message.tool_call_id],
            }
            if message.status == "error":
                item["error"] = {"type": "unknown", "message": content}
        elif isinstance(message, HumanMessage):
            item: dict = {"role": "user", "content": content}
        elif isinstance(message, SystemMessage):
            item: dict = {"role": "system", "content": content}
        else:
            raise ValueError(f"Unsupported message type: {type(message).__name__}")
        result.append(item)
    return result


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


class IncompleteObservationError(RuntimeError):
    """Watcher returned an invalid policy outcome or an unexpected transcript response."""


def completed_outcomes(outcomes, inputs):
    """Validate advisory outcomes under the inherited observe, enforce or paused policy."""
    if not isinstance(outcomes, list) or len(outcomes) != len(inputs):
        raise IncompleteObservationError("Watcher did not return one outcome per input")
    for submitted, outcome in zip(inputs, outcomes, strict=True):
        try:
            validate_observation(outcome, submitted["tool_use_id"])
        except ValueError as error:
            raise IncompleteObservationError("Watcher returned an invalid observation outcome") from error
    return outcomes


async def observe_transcript(client: AsyncWatcherClient, conversation_id: str, transcript):
    """Observe validated Inspect messages using each call's historical prefix.

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
                    external_ids={"other": f"langgraph:{conversation_id}"},
                    timeout=420,
                )
                outcomes.extend(completed_outcomes(batch, inputs))
    finally:
        receipt = await client.pre_tool_use_hook(
            None,
            messages=transcript,
            external_ids={"other": f"langgraph:{conversation_id}"},
            timeout=10,
        )
        if receipt != []:
            raise IncompleteObservationError("Transcript-only recording returned unexpected outcomes")
    return outcomes


async def observe(client: AsyncWatcherClient, conversation_id: str, messages: Sequence[BaseMessage]):
    """Convert native history, observe historical tool prefixes and record its tail.

    This runs after tool execution and cannot prevent side effects. It waits for
    advisory outcomes under the organization's inherited policy, including paused
    bypasses. It raises on invalid outcomes and attempts final recording even when
    assessment fails. No response is treated as proof of historical execution. Reuse conversation_id and native
    tool IDs for full snapshots of the same conversation.
    """
    return await observe_transcript(client, conversation_id, messages_for_watcher(messages))
