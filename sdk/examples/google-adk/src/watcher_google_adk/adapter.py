"""Observe completed native framework histories using only public watcher_sdk APIs.

The caller owns execution and history retention. Conversion rejects unsupported
content instead of silently dropping it. Monitoring happens after execution and
waits for results, so this adapter never prevents a tool's side effects.
"""

import json
from copy import deepcopy

from google.adk.flows.llm_flows.functions import REQUEST_CONFIRMATION_FUNCTION_CALL_NAME
from google.adk.tools.tool_confirmation import ToolConfirmation
from google.genai import types

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


def confirmation_answers(messages):
    """Find ADK tool confirmations: which calls asked, and where and how each was answered.

    A tool that requires confirmation makes ADK emit an ``adk_request_confirmation``
    call naming the original call in ``originalFunctionCall``; the answer is that
    request's function response, read as ADK reads it
    (``ToolConfirmation.from_response_dict``). Returns ``(asked, answers)``: the
    IDs of original calls that asked, and original call ID to its answers in
    order, each ``(position, confirmed)``, where a position is ``(message index,
    part index)``. Malformed requests and answers without a request raise.
    """
    requests, asked, answers = {}, set(), {}
    for message_index, message in enumerate(messages):
        if not isinstance(message, types.Content):
            raise ValueError("Expected Google Content")
        for part_index, part in enumerate(message.parts or []):
            call, response = part.function_call, part.function_response
            if call is not None and call.name == REQUEST_CONFIRMATION_FUNCTION_CALL_NAME:
                original = (call.args or {}).get("originalFunctionCall")
                if not isinstance(original, dict) or not isinstance(original.get("id"), str):
                    raise ValueError("ADK confirmation request without its original call")
                requests[call.id] = original["id"]
                asked.add(original["id"])
            elif response is not None and response.name == REQUEST_CONFIRMATION_FUNCTION_CALL_NAME:
                if response.id not in requests:
                    raise ValueError("ADK confirmation answer without its request")
                confirmed = ToolConfirmation.from_response_dict(response.response or {}).confirmed
                answers.setdefault(requests[response.id], []).append(((message_index, part_index), confirmed))
    return asked, answers


def messages_for_watcher(messages, confirmations=None):
    """Convert session.events Content objects after ADK completes a run.

    Function responses retain their actual IDs. Dictionary results become JSON;
    ADK result envelopes are unwrapped and absent arguments become empty objects.
    Only text/function parts are
    accepted; thought, executable-code, media and grounding content need mappings.

    A response with a truthy top-level ``error`` key keeps its content and also
    gets the tool message's ``error`` (Inspect ``ToolCallError``, type
    ``unknown``): that key is how ADK reports a call that failed while running,
    such as missing arguments or a dictionary an ``on_tool_error_callback``
    returned. Watcher records a call it let through whose result has no
    ``error`` as completed, so a tool that signals failure any other way (MCP
    ``isError``, a ``status`` field) is recorded as having run unless the
    integration adds ``error`` itself.

    Tool confirmations are framework protocol, not tool results, so the
    ``adk_request_confirmation`` call and its answers are left out, and so are
    the responses ADK gives the original call before any answer (the request
    for confirmation) and after the call's result (ADK's response to a
    replayed answer). Until an answer arrives the call has no result.

    A call's result is ADK's refusal of a rejected confirmation, which keeps its
    text and gets no ``error`` (a refusal is not an execution failure; the
    callback in native.py reports the call to Watcher as blocked instead), or
    the outcome of an approved run, whose ``error`` marks a failure. Chronology
    cannot tell them apart: a replayed answer the callback refused can land
    between an approval and its run's result. ``confirmations`` is the
    callback's own record of the answer that took effect for each call
    (Monitor.confirmations: True for an admitted approval, False for an
    accepted rejection), and the result is a refusal exactly when it says
    False; a call it does not name keeps its ``error``. Without it, a result
    counts as a refusal only when every answer before it is a rejection, so an
    ambiguous history keeps its ``error``.
    """
    asked, answers = confirmation_answers(messages)
    settled = set()
    result = []
    for message_index, message in enumerate(messages):
        item: dict = {"role": "assistant" if message.role == "model" else message.role, "content": ""}
        calls = []
        # Function parts produce tool calls and results, never a message of their own.
        structured = False
        for part_index, part in enumerate(message.parts or []):
            if part.thought:
                raise ValueError("Thought parts are unsupported")
            if part.text is not None:
                item["content"] += part.text
            elif part.function_call is not None:
                call = part.function_call
                structured = True
                if call.name == REQUEST_CONFIRMATION_FUNCTION_CALL_NAME:
                    continue
                calls.append(
                    {"id": call.id, "function": call.name, "arguments": {} if call.args is None else call.args}
                )
            elif part.function_response is not None:
                response = part.function_response
                structured = True
                if response.name == REQUEST_CONFIRMATION_FUNCTION_CALL_NAME:
                    continue
                refused = False
                if response.id in asked:
                    earlier = [
                        confirmed
                        for position, confirmed in answers.get(response.id, [])
                        if position < (message_index, part_index)
                    ]
                    if not earlier or response.id in settled:
                        continue
                    settled.add(response.id)
                    if confirmations is None:
                        refused = not any(earlier)
                    else:
                        refused = confirmations.get(response.id) is False
                content = response.response
                if not isinstance(content, dict):
                    raise ValueError("Expected an ADK function response object")
                payload = content["result"] if set(content) == {"result"} else content
                text = payload if isinstance(payload, str) else json.dumps(payload)
                tool: dict = {"role": "tool", "content": text, "tool_call_id": response.id}
                # Truthiness matches ADK's own FunctionTool error check, so an
                # explicit "error": None or "" still reads as a successful run.
                failure = content.get("error")
                if failure and not refused:
                    detail = failure if isinstance(failure, str) else json.dumps(failure)
                    tool["error"] = {"type": "unknown", "message": detail}
                result.append(tool)
            else:
                raise ValueError("Unsupported Google content")
        if calls:
            item["tool_calls"] = calls
        if item["content"] or calls or not structured:
            result.append(item)
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
                    external_ids={"other": f"google-adk:{conversation_id}"},
                    timeout=420,
                )
                outcomes.extend(completed_outcomes(batch, inputs))
    finally:
        receipt = await client.pre_tool_use_hook(
            None,
            messages=transcript,
            external_ids={"other": f"google-adk:{conversation_id}"},
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

    A history with a rejected tool confirmation raises ValueError before
    anything is sent. Its result is ADK's refusal without ``error``, and this
    observer cannot report the call blocked, so Watcher would record a call it
    let through as completed. Record such a conversation through Monitor, whose
    callback reports the rejection as it happens.
    """
    _, answers = confirmation_answers(messages)
    if not all(confirmed for given in answers.values() for _, confirmed in given):
        raise ValueError("A rejected tool confirmation must be reported through Monitor, not imported here")
    return await observe_transcript(client, conversation_id, messages_for_watcher(messages))
