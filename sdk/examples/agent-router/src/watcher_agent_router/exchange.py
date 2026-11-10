"""Validate Chat Completions exchanges and decide whether Watcher allows their delivery.

Watcher converts the provider exchange and selects the tool calls it grades.
This module independently inventories every tool call the client would
receive, so a call that Watcher skipped cannot be released without a matching
decision for its unique native ID.
"""

import json
from typing import Any, cast

import structlog
from pydantic import BaseModel

from watcher_sdk import AsyncWatcherClient, WatcherAPIError

# Every conversation ID the processor generates starts with this prefix.
# Watcher labels sessions whose ID carries a registered gateway prefix as
# Gateway, so ``evaluate`` refuses any other ID.
CONVERSATION_PREFIX = "agent-router:"

CHAT_COMPLETIONS_PATH = "/v1/chat/completions"

# Raw-hook fields newer than some Watcher servers, which reject them as unknown.
_GATEWAY_FIELDS = frozenset({"withheld_tool_use_ids", "withholds_refused_calls"})

logger = structlog.get_logger(__name__)


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
    # Whether the user's answer can lead to approval of an escalation. Only
    # Watcher's graders read the conversation; a rule, a threshold or the
    # grading-failure policy decides again without it, so offering "allow"
    # there would escalate the same call in a loop.
    user_can_approve: bool = False


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
# Decision sources that read the conversation, so a user's approval can change their next decision.
_GRADED_SOURCES = {"triage", "policy_gateway"}


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


def _predates_gateway_fields(error: WatcherAPIError) -> bool:
    """Whether Watcher rejected the exchange as an older server that does not know ``_GATEWAY_FIELDS``."""
    detail = error.body.get("detail") if error.status_code == 422 and isinstance(error.body, dict) else None
    if not isinstance(detail, list):
        return False
    for item in cast(list[Any], detail):
        if not isinstance(item, dict) or item.get("type") != "extra_forbidden":
            continue
        location = item.get("loc")
        if isinstance(location, list) and location and location[-1] in _GATEWAY_FIELDS:
            return True
    return False


async def submit(
    watcher: AsyncWatcherClient,
    request: dict,
    response: dict,
    *,
    conversation_id: str,
    user_agent: str | None,
    withheld_ids: list[str] | None = None,
) -> Any:
    """Send one raw exchange to Watcher's pre-tool-use hook and return its outputs unchecked.

    Every exchange declares that this processor withholds the calls Watcher
    refuses (``withholds_refused_calls``), so Watcher records an enforced
    refusal as blocked rather than pending. ``withheld_ids`` names the calls
    a delivered reply replaced, for the recording of that reply. A Watcher
    server older than these fields rejects them; the exchange is then sent
    once more without them, so it is still evaluated and recorded, with
    refusals left pending.
    """
    fields: dict[str, Any] = {
        "request_body": request,
        "response_body": response,
        "url": CHAT_COMPLETIONS_PATH,
        "provider": "openai",
        "user_agent": user_agent,
        "external_ids": {"other": conversation_id},
    }
    try:
        return await watcher.pre_tool_use_hook(
            **fields, withholds_refused_calls=True, withheld_tool_use_ids=withheld_ids or None
        )
    except WatcherAPIError as error:
        if not _predates_gateway_fields(error):
            raise
        logger.warning("watcher_predates_gateway_fields", conversation_id=conversation_id)
        return await watcher.pre_tool_use_hook(**fields)


def recorded_exchange(request: dict, delivered: dict) -> tuple[dict, dict]:
    """The exchange that records ``delivered`` as the reply to ``request`` without grading anything again.

    Watcher evaluates the calls in a response. Calls an approved alternative
    carries were graded when it was proposed, so they move into the request
    as the assistant's last message (they have no results yet), and the
    response is an empty assistant message. A reply without calls is recorded
    as it is. Watcher attaches withheld call IDs to the delivered message,
    which is the last stored message or the one before an empty reply.
    """
    choice = delivered["choices"][0]
    if not choice["message"].get("tool_calls"):
        return request, delivered
    history = {**request, "messages": [*request["messages"], choice["message"]]}
    empty = {"role": "assistant", "content": None}
    return history, {**delivered, "choices": [{**choice, "message": empty, "finish_reason": "stop"}]}


async def evaluate(
    watcher: AsyncWatcherClient,
    request: dict,
    response: dict,
    *,
    conversation_id: str,
    user_agent: str | None = None,
) -> Evaluation:
    """Submit the exchange to Watcher and match every delivered call to exactly one decision.

    The original request and response bodies go through the public raw hook
    (see ``submit``), so Watcher owns conversion, call selection and policy.
    No settings override is sent. An empty result admits text-only output,
    never an uncovered call. A successful hook acknowledges submission;
    recording happens afterward.
    """
    _conversation_id(conversation_id)
    validate_request(request)
    expected = client_calls(response)
    outcomes = await submit(watcher, request, response, conversation_id=conversation_id, user_agent=user_agent)
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
                    user_can_approve=value["decision"] == "escalate" and value["decision_source"] in _GRADED_SOURCES,
                )
            )
        elif not releasable(value):
            return Evaluation(verified=False)
    return Evaluation(verified=decided == expected, denials=denials)


# Message fields an alternative may carry. Any other populated field could not
# be merged into the delivered message without losing or misplacing it.
_ALTERNATIVE_FIELDS = {"role", "content", "tool_calls", "refusal", "reasoning_content"}
# Fields providers routinely send empty, which carry nothing to merge.
_EMPTY_DEFAULTS: dict[str, list] = {"annotations": [[]]}


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
