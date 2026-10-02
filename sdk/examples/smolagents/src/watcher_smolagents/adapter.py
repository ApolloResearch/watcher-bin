"""Observe completed native framework histories using only public watcher_sdk APIs.

The caller owns execution and history retention. Conversion rejects unsupported
content instead of silently dropping it. Monitoring happens after execution and
waits for results, so this adapter never prevents a tool's side effects.
"""

from copy import deepcopy

from smolagents.agents import ActionOutput, ToolOutput
from smolagents.memory import ActionStep, FinalAnswerStep, TaskStep, ToolCall
from smolagents.models import tool_role_conversions

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


def model_context(messages):
    """Retain native text prompts using smolagents' tool-role conversion.

    Native memory renders old tool calls/results as text without execution IDs.
    Preserve that prompt context separately from the ID-bearing stream events;
    do not manufacture new tool executions from those textual reminders.
    """
    result = []
    for message in messages:
        role = tool_role_conversions.get(message.role, message.role)
        content = message.content
        if content is None:
            content = ""
        elif not isinstance(content, str):
            if any(block["type"] != "text" for block in content):
                raise ValueError("Only text model context is supported")
            content = "".join(block["text"] for block in content)
        result.append({"role": role, "content": content})
    return result


def messages_for_watcher(messages):
    """Consume the complete native run(stream=True) event list plus initial TaskStep.

    Read ToolOutput events rather than ActionStep.observations: the latter merges
    parallel results into one string and loses their individual linkage.
    Each completed ActionStep contributes its actual model prompt and response
    text before that step's buffered tool events. Repeated prompt context is
    retained. A stream ending mid-step is rejected; publish after ActionStep.
    Planning and multimedia events are rejected; this example disables planning.
    """
    result = []
    step_messages = []
    for event in messages:
        if isinstance(event, TaskStep):
            if event.task_images:
                raise ValueError("Images are unsupported")
            result.append({"role": "user", "content": event.task})
        elif isinstance(event, ToolCall):
            step_messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": event.id, "function": event.name, "arguments": event.arguments}],
                }
            )
        elif isinstance(event, ToolOutput):
            if not isinstance(event.output, str):
                raise ValueError("Only text tool output is supported")
            step_messages.append({"role": "tool", "content": event.output, "tool_call_id": event.id})
        elif isinstance(event, FinalAnswerStep):
            if not isinstance(event.output, str):
                raise ValueError("Only text final output supported")
            result.append({"role": "assistant", "content": event.output})
        elif isinstance(event, ActionStep):
            if event.error:
                raise ValueError("Failed steps require explicit recovery before publishing")
            if event.model_input_messages is None or event.model_output_message is None:
                raise ValueError("Completed steps must include native model context")
            result.extend(model_context(event.model_input_messages))
            result.extend(model_context([event.model_output_message]))
            result.extend(step_messages)
            step_messages = []
        elif isinstance(event, ActionOutput):
            continue
        else:
            raise ValueError("Unsupported native stream event")
    if step_messages:
        raise ValueError("Wait for a completed ActionStep before publishing")
    return validate(result)


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
                    external_ids={"other": f"smolagents:{conversation_id}"},
                    timeout=420,
                )
                outcomes.extend(completed_outcomes(batch, inputs))
    finally:
        receipt = await client.pre_tool_use_hook(
            None,
            messages=transcript,
            external_ids={"other": f"smolagents:{conversation_id}"},
            timeout=10,
        )
        if receipt != []:
            raise IncompleteObservationError("Transcript-only recording returned unexpected outcomes")
    return outcomes


async def observe(client: AsyncWatcherClient, conversation_id: str, messages):
    """Convert native history, observe historical tool prefixes and record its tail.

    This runs after tool execution and cannot prevent side effects. It waits for
    advisory outcomes under the organization's inherited policy, including paused
    bypasses. It raises on invalid outcomes and attempts final recording even when
    assessment fails. No response is treated as proof of historical execution. Reuse conversation_id and native
    tool IDs for full snapshots of the same conversation.
    """
    return await observe_transcript(client, conversation_id, messages_for_watcher(messages))
