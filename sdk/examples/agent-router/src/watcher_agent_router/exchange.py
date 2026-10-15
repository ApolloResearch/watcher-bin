"""Validate Chat Completions exchanges and decide whether Watcher allows their delivery.

Watcher converts the provider exchange and selects the tool calls it grades.
This module independently inventories every tool call the client would
receive, so a call that Watcher skipped cannot be released without a matching
decision for its unique native ID.
"""

import json
from copy import deepcopy
from typing import Any

from pydantic import BaseModel

from watcher_sdk import AsyncWatcherClient

# Every conversation ID the processor generates starts with this prefix.
# Watcher labels sessions whose ID carries a registered gateway prefix as
# Gateway, so ``evaluate`` refuses any other ID.
CONVERSATION_PREFIX = "agent-router:"

CHAT_COMPLETIONS_PATH = "/v1/chat/completions"


class UnsupportedExchange(ValueError):
    """The route cannot safely deliver the supplied request or response."""


def _object(pairs: list[tuple[str, Any]]) -> dict:
    """Reject duplicate JSON keys rather than reinterpret an ambiguous object."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise UnsupportedExchange("Duplicate JSON key")
        result[key] = value
    return result


def decode_json(value: str | bytes) -> Any:
    """Decode strict JSON without changing integers, floats, booleans or nulls."""

    def invalid_constant(_constant: str) -> None:
        raise UnsupportedExchange("Non-finite JSON number")

    try:
        return json.loads(value, object_pairs_hook=_object, parse_constant=invalid_constant)
    except UnsupportedExchange:
        raise
    # Besides malformed JSON, untrusted bytes can trip CPython's integer-digit
    # limit (ValueError) or nest deeply enough to exhaust the recursion limit.
    except (ValueError, RecursionError) as error:
        raise UnsupportedExchange("Body is not valid JSON") from error


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise UnsupportedExchange(f"Missing or invalid {label}")
    return value


def _conversation_id(value: Any) -> str:
    """Require the documented prefix followed by a nonempty identifier."""
    identity = _string(value, "gateway conversation ID")
    if not identity.startswith(CONVERSATION_PREFIX) or identity == CONVERSATION_PREFIX:
        raise UnsupportedExchange("Gateway conversation ID lacks the documented prefix")
    return identity


def validate_request(request: Any) -> None:
    """Check route coverage before the provider is called, without converting messages.

    Watcher validates and converts message content. This route requires one
    choice, the complete client-supplied history and client function tools.
    Streaming requests are accepted; the processor gates their event stream.
    """
    if not isinstance(request, dict):
        raise UnsupportedExchange("Request must be an object")
    _string(request.get("model"), "model")
    if type(request.get("stream", False)) is not bool:
        raise UnsupportedExchange("stream must be a boolean")
    if type(request.get("n", 1)) is not int or request.get("n", 1) != 1:
        raise UnsupportedExchange("Exactly one completion choice is required")
    for key in ("functions", "function_call", "previous_response_id", "conversation", "audio"):
        if request.get(key) is not None:
            raise UnsupportedExchange(f"Unsupported request option: {key}")
    modalities = request.get("modalities")
    if modalities is None:
        modalities = []
    if not isinstance(modalities, list) or "audio" in modalities:
        raise UnsupportedExchange("modalities must be a list without audio output")
    tools = request.get("tools", [])
    if not isinstance(tools, list) or any(
        not isinstance(tool, dict) or tool.get("type") != "function" for tool in tools
    ):
        raise UnsupportedExchange("Only client function tools are supported")
    messages = request.get("messages")
    if not isinstance(messages, list) or not messages or any(not isinstance(message, dict) for message in messages):
        raise UnsupportedExchange("A complete messages list is required")


def client_calls(response: Any) -> set[str]:
    """Return the native IDs of every tool call in the body the client would receive.

    This does not select calls for grading or build a transcript. Incomplete
    responses, unknown executable formats, non-object arguments and duplicate
    native IDs are rejected so no proposal escapes the inventory.
    """
    choices = response.get("choices") if isinstance(response, dict) else None
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise UnsupportedExchange("Exactly one complete response choice is required")
    choice = choices[0]
    if type(choice.get("index")) is not int or choice["index"] != 0:
        raise UnsupportedExchange("Unexpected choice index")
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise UnsupportedExchange("Response must contain an assistant message")
    if message.get("function_call") is not None or message.get("audio") is not None:
        raise UnsupportedExchange("Unsupported executable or audio output")
    calls = message.get("tool_calls")
    if calls is None:
        calls = []
    if not isinstance(calls, list):
        raise UnsupportedExchange("Invalid tool calls")
    reason = choice.get("finish_reason")
    if reason not in ("stop", "tool_calls", "length", "content_filter"):
        raise UnsupportedExchange("Unsupported completion finish reason")
    if calls and reason not in ("stop", "tool_calls"):
        raise UnsupportedExchange("Incomplete executable response")
    identifiers: set[str] = set()
    for call in calls:
        if not isinstance(call, dict) or call.get("type") != "function":
            raise UnsupportedExchange("Only client function tools are supported")
        identifier = _string(call.get("id"), "tool call ID")
        if identifier in identifiers:
            raise UnsupportedExchange("Duplicate tool call ID")
        identifiers.add(identifier)
        function = call.get("function")
        if not isinstance(function, dict) or not isinstance(function.get("arguments"), str):
            raise UnsupportedExchange("Invalid tool function")
        _string(function.get("name"), "tool name")
        if not isinstance(decode_json(function["arguments"]), dict):
            raise UnsupportedExchange("Function arguments must be a JSON object")
    return identifiers


class Denial(BaseModel):
    """A withheld call and Watcher's public explanation, as shown to the client and the model."""

    tool_use_id: str
    tool_name: str
    tool_input: object
    reason: str
    is_escalation: bool


class Evaluation(BaseModel):
    """Watcher's verdict on one response.

    ``verified`` is False when the decisions cannot be matched one-to-one to
    the delivered calls or carry inconsistent provenance; nothing may be
    released then. Otherwise ``denials`` lists the calls Watcher refused, and
    an empty list means every call may be delivered.
    """

    verified: bool
    denials: list[Denial] = []


def _consistent_failure(value: dict) -> bool:
    """A grading-failure outcome must name a known failure; any other outcome must carry none."""
    failure = value.get("grading_error")
    if value.get("decision_source") == "grading_error":
        return (
            isinstance(failure, dict)
            and failure.get("code") in {"timeout", "at_capacity", "allowance_exhausted", "grader_failed", "no_result"}
            and isinstance(failure.get("message"), str)
        )
    return failure is None


def releasable(value: dict) -> bool:
    """Accept only a consistent applied outcome; malformed provenance never grants release.

    Under enforcement only ``allow`` releases a call. Observe and paused modes
    return ``deferred``, which keeps ordinary client behavior. A valid
    grading-failure outcome follows the administrator's failure policy.
    """
    decision, mode, source = value.get("decision"), value.get("enforcement_mode"), value.get("decision_source")
    if not _consistent_failure(value):
        return False
    if mode == "paused":
        return decision == "deferred" and source == "bypass" and value.get("judged_decision") is None
    if source not in _DECIDING_SOURCES:
        return False
    if mode == "observe":
        return decision == "deferred" and value.get("judged_decision") in {"allow", "deny", "escalate"}
    return mode == "enforce" and decision == "allow" and value.get("judged_decision") == "allow"


def refused(value: dict) -> bool:
    """Recognize a consistent enforced ``deny`` or ``escalate``, including one from the failure policy."""
    decision = value.get("decision")
    return (
        _consistent_failure(value)
        and value.get("enforcement_mode") == "enforce"
        and value.get("decision_source") in _DECIDING_SOURCES
        and decision in {"deny", "escalate"}
        and value.get("judged_decision") == decision
    )


_DECIDING_SOURCES = {"threshold", "rule", "triage", "policy_gateway", "grading_error"}


def _reason(value: dict) -> str:
    """Watcher's public explanation for a refusal; grader prompts and scores are never included."""
    verdict = value.get("verdict") if isinstance(value.get("verdict"), dict) else {}
    failure = value.get("grading_error") if isinstance(value.get("grading_error"), dict) else {}
    for candidate in (verdict.get("explanation"), verdict.get("summary"), failure.get("message")):
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return "Watcher did not give a reason."


def _delivered_calls(response: dict) -> dict[str, dict]:
    """The response's tool calls by native ID, with arguments parsed (already validated)."""
    calls = response["choices"][0]["message"].get("tool_calls") or []
    return {
        call["id"]: {"name": call["function"]["name"], "input": decode_json(call["function"]["arguments"])}
        for call in calls
    }


async def evaluate(
    watcher: AsyncWatcherClient,
    request: dict,
    response: dict,
    *,
    conversation_id: str,
    user_agent: str | None = None,
) -> Evaluation:
    """Submit the exchange to Watcher and match every delivered call to exactly one decision.

    The original request and response bodies go through the public raw hook,
    so Watcher owns conversion, call selection and policy. No settings override
    is sent. An empty result admits text-only output, never an uncovered call.
    A successful hook acknowledges submission; recording happens afterward.
    """
    _conversation_id(conversation_id)
    validate_request(request)
    expected = client_calls(response)
    outcomes = await watcher.pre_tool_use_hook(
        request_body=request,
        response_body=response,
        url=CHAT_COMPLETIONS_PATH,
        provider="openai",
        user_agent=user_agent,
        external_ids={"other": conversation_id},
    )
    if not isinstance(outcomes, list):
        return Evaluation(verified=False)
    calls = _delivered_calls(response) if expected else {}
    decided: set[str] = set()
    denials: list[Denial] = []
    for outcome in outcomes:
        value = outcome.to_dict()
        identifier = value.get("tool_use_id")
        if (
            "status_code" in value
            or not isinstance(identifier, str)
            or identifier not in expected
            or identifier in decided
        ):
            return Evaluation(verified=False)
        decided.add(identifier)
        if refused(value):
            call = calls[identifier]
            denials.append(
                Denial(
                    tool_use_id=identifier,
                    tool_name=call["name"],
                    tool_input=call["input"],
                    reason=_reason(value),
                    is_escalation=value["decision"] == "escalate",
                )
            )
        elif not releasable(value):
            return Evaluation(verified=False)
    return Evaluation(verified=decided == expected, denials=denials)


# The notice echoes each refused call so the model can see what was withheld,
# but it must stay small: the rewritten response replaces the provider's within
# the same size budget (MAX_BODY in processor.py).
_ECHO_LIMIT = 4096
_ID_LIMIT = 256
_NOTICE_LIMIT = 64 * 1024


def _echo(denial: Denial) -> dict:
    """One refused call as shown in the notice, with long arguments and reasons shortened."""
    shown = denial.model_dump(mode="json")
    arguments = json.dumps(shown["tool_input"], ensure_ascii=False, sort_keys=True)
    if len(arguments) > _ECHO_LIMIT:
        shown["tool_input"] = {"truncated_arguments": arguments[:_ECHO_LIMIT]}
    shown["reason"] = shown["reason"][:_ECHO_LIMIT]
    shown["tool_use_id"] = shown["tool_use_id"][:_ID_LIMIT]
    shown["tool_name"] = shown["tool_name"][:_ID_LIMIT]
    return shown


def denial_notice(denials: list[Denial], cancelled: list[str]) -> str:
    """Describe withheld calls as ordinary assistant text with their IDs, arguments and public reasons.

    ``cancelled`` names the calls Watcher allowed that were withheld because
    another call in the same response was refused; none of them were run.
    Long arguments and reasons are shortened, and once the notice reaches
    its size limit the remaining calls are only counted.
    """
    shown: list[dict] = []
    size = 0
    for denial in denials:
        echo = _echo(denial)
        size += len(json.dumps(echo, ensure_ascii=False))
        if shown and size > _NOTICE_LIMIT:
            break
        shown.append(echo)
    notice = "Watcher did not approve these tool calls, so the gateway withheld them:\n\n" + json.dumps(
        shown, ensure_ascii=False, sort_keys=True
    )
    if len(shown) < len(denials):
        notice += f"\n\n{len(denials) - len(shown)} more refused tool calls were withheld."
    if cancelled:
        listed = json.dumps([identifier[:_ID_LIMIT] for identifier in cancelled[:100]], ensure_ascii=False)
        notice += (
            "\n\nThese other tool calls were withheld because a call in the same response was refused; "
            f"they were not run: {listed}"
        )
        if len(cancelled) > 100:
            notice += f" and {len(cancelled) - 100} more."
    return notice


def withheld_notice(response: dict, evaluation: Evaluation, compact: bool = False) -> str:
    """The explanation for a response's refused calls and the siblings withheld with them.

    ``compact`` gives a short count-only notice, for when the full one would
    push the rewritten response past its size budget.
    """
    denied = {denial.tool_use_id for denial in evaluation.denials}
    calls = response["choices"][0]["message"].get("tool_calls") or []
    cancelled = [call["id"] for call in calls if call["id"] not in denied]
    if compact:
        return (
            f"Watcher did not approve {len(evaluation.denials)} tool calls, so the gateway withheld them"
            f" and {len(cancelled)} other calls from the same response. None of them were run."
        )
    return denial_notice(evaluation.denials, cancelled)


# Message fields an alternative may carry. Any other populated field could not
# be merged into the delivered message without losing or misplacing it.
_ALTERNATIVE_FIELDS = {"role", "content", "tool_calls", "refusal", "reasoning_content"}
# Fields providers routinely send empty, which carry nothing to merge.
_EMPTY_DEFAULTS: dict[str, list] = {"annotations": [[]]}
RETRY_INSTRUCTION = "Choose an alternative consistent with this result, or explain why you cannot continue."
_CANCELLED_RESULT = "This tool call was not run because another call in the same response was refused. "


def alternative_message(response: dict) -> dict:
    """Return an alternative's assistant message once its fields are known to merge cleanly.

    Call after ``client_calls`` has accepted the response. Text fields must be
    strings; unknown populated fields (audio, multimodal parts, provider
    extensions) are refused rather than dropped.
    """
    message = response["choices"][0]["message"]
    for key, value in message.items():
        if key not in _ALTERNATIVE_FIELDS and value is not None and value not in _EMPTY_DEFAULTS.get(key, []):
            raise UnsupportedExchange("The alternative carries message fields the gateway cannot merge")
    if any(
        message.get(key) is not None and not isinstance(message[key], str)
        for key in ("content", "refusal", "reasoning_content")
    ):
        raise UnsupportedExchange("The alternative's text must be a string")
    return message


def compose(response: dict, notice: str, alternative: dict | None) -> dict:
    """Replace every call in ``response`` with ``notice`` and, if given, an approved alternative.

    No original call has reached the client, so all are removed together. The
    content becomes the original text, the notice, then the alternative's
    text; the alternative supplies the calls and finish reason. The original
    identity and usage are kept: usage describes the first provider attempt
    only. Token log probabilities are dropped, since they describe the
    refused answer. ``alternative`` must have passed ``alternative_message``.

    The original is only known to be an assistant message with valid calls:
    content given as a list of parts keeps its parts and gains the added
    text as further text parts, and original text fields that are not
    strings are left as they are rather than merged.
    """
    message = dict(response["choices"][0]["message"])
    message.pop("tool_calls", None)
    other = alternative["choices"][0]["message"] if alternative is not None else {}
    added = [part for part in (notice, other.get("content")) if part]
    original = message.get("content")
    if isinstance(original, list):
        message["content"] = [*original, *({"type": "text", "text": text} for text in added)]
    else:
        message["content"] = "\n\n".join([original, *added] if isinstance(original, str) and original else added)
    for key in ("refusal", "reasoning_content"):
        if other.get(key) and isinstance(message.get(key) or "", str):
            message[key] = (message.get(key) or "") + other[key]
    if other.get("tool_calls"):
        message["tool_calls"] = other["tool_calls"]
        reason = "tool_calls"
    else:
        reason = alternative["choices"][0]["finish_reason"] if alternative is not None else "stop"
    choice = {**response["choices"][0], "message": message, "finish_reason": reason}
    choice.pop("logprobs", None)
    return {**response, "choices": [choice]}


def operation_key(tool_name: str, tool_input: object) -> str:
    """Identify an operation independently of its call ID, keeping JSON's distinction between true and 1."""
    return json.dumps([tool_name, tool_input], ensure_ascii=False, sort_keys=True)


def continuation(request: dict, response: dict, evaluation: Evaluation) -> dict:
    """The request that asks the model for an alternative to a refused proposal.

    Appends the proposal and one tool result per call to a copy of the
    request: refused calls get Watcher's explanation, their siblings say they
    were not run. Nothing in the proposal reached the client, so no result
    describes an execution. Tools, tool choice and other options are kept, so
    an alternative cannot use a tool the client excluded. The request is
    buffered (``stream`` false) whatever the client asked for.
    """
    result = deepcopy(request)
    result.pop("stream_options", None)
    result["stream"] = False
    message = deepcopy(response["choices"][0]["message"])
    result["messages"].append(message)
    denials = {denial.tool_use_id: denial for denial in evaluation.denials}
    for call in message.get("tool_calls") or []:
        denial = denials.get(call["id"])
        content = (
            denial_notice([denial], []) + "\n\n" + RETRY_INSTRUCTION
            if denial is not None
            else _CANCELLED_RESULT + RETRY_INSTRUCTION
        )
        result["messages"].append({"role": "tool", "tool_call_id": call["id"], "content": content})
    return result
