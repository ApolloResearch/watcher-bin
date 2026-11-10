"""Validate Chat Completions exchanges and match Watcher's decisions to every delivered call.

Provider-to-transcript conversion belongs to Watcher. This module inventories
only client-visible tool proposals so a call omitted by backend selection cannot
be released without a corresponding decision for its unique native ID.
"""

import json
from dataclasses import dataclass, field
from typing import Any, cast

import structlog

from watcher_kong_ai.notices import Denial, ToolCall
from watcher_sdk import AsyncWatcherClient, WatcherAPIError

MAX_BODY = 8 * 1024 * 1024

# Every conversation ID the gateway plugin and the bridge generate starts with
# this prefix (see gateway/kong/plugins/watcher/handler.lua). Watcher labels
# sessions whose ID carries a registered gateway prefix as Gateway, so the
# bridge refuses any other ID.
CONVERSATION_PREFIX = "kong:"

# Decision sources that read the conversation, so a user's approval can change
# their next decision. Rules, thresholds and grading-failure policy do not.
_GRADED = {"policy_gateway", "triage"}
_DECIDING_SOURCES = {"threshold", "rule", "triage", "policy_gateway", "grading_error"}

# The fields that tell Watcher this gateway withholds refused calls and which
# calls a delivered reply replaced. Watcher servers that predate them forbid
# unknown fields, so they answer HTTP 422 with an ``extra_forbidden`` error
# located at the field.
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

    def invalid_constant(value: str) -> None:
        raise UnsupportedExchange("Non-finite JSON number")

    return json.loads(value, object_pairs_hook=_object, parse_constant=invalid_constant)


def string(value: Any, label: str) -> str:
    """Require a nonempty string, naming ``label`` in the error."""
    if not isinstance(value, str) or not value:
        raise UnsupportedExchange(f"Missing or invalid {label}")
    return value


def check_conversation_id(value: Any) -> str:
    """Require the gateway's documented prefix followed by a nonempty identifier."""
    identity = string(value, "gateway conversation ID")
    if not identity.startswith(CONVERSATION_PREFIX) or identity == CONVERSATION_PREFIX:
        raise UnsupportedExchange("Gateway conversation ID lacks the documented prefix")
    return identity


def validate_request(request: Any) -> None:
    """Check route coverage before provider invocation, without converting messages.

    The backend validates and converts message content. This route requires full
    supplied history, one choice and client function tools. The Kong plugin
    handles buffered JSON responses only, so streaming requests are rejected;
    continuations the bridge builds carry an explicit ``stream: false``.
    """
    if not isinstance(request, dict):
        raise UnsupportedExchange("Request must be an object")
    string(request.get("model"), "model")
    if type(request.get("stream", False)) is not bool:
        raise UnsupportedExchange("stream must be a boolean")
    if request.get("stream"):
        raise UnsupportedExchange("Streaming is unavailable on this gateway route")
    if type(request.get("n", 1)) is not int or request.get("n", 1) != 1:
        raise UnsupportedExchange("Exactly one completion choice is required")
    for key in ("functions", "function_call", "previous_response_id", "conversation", "audio"):
        if request.get(key) is not None:
            raise UnsupportedExchange(f"Unsupported request option: {key}")
    tools = request.get("tools", [])
    if not isinstance(tools, list) or any(
        not isinstance(tool, dict) or tool.get("type") != "function" for tool in tools
    ):
        raise UnsupportedExchange("Only client function tools are supported")
    if not isinstance(request.get("messages"), list) or not request["messages"]:
        raise UnsupportedExchange("A complete messages list is required")


def client_calls(response: Any) -> list[ToolCall]:
    """Inventory every client tool call in provider order, independently of hook selection.

    No transcript is built. Reject incomplete responses, unknown executable
    formats, ambiguous arguments and duplicate native IDs, so no proposal
    escapes the inventory.
    """
    choices = response.get("choices") if isinstance(response, dict) else None
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise UnsupportedExchange("Exactly one complete response choice is required")
    choice = choices[0]
    if type(choice.get("index")) is not int or choice["index"] != 0:
        raise UnsupportedExchange("Unexpected choice index")
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant" or message.get("function_call") is not None:
        raise UnsupportedExchange("Unsupported assistant response")
    calls = message.get("tool_calls") or []
    if not isinstance(calls, list):
        raise UnsupportedExchange("Invalid tool calls")
    if choice.get("finish_reason") != ("tool_calls" if calls else "stop"):
        raise UnsupportedExchange("Response is incomplete or has an unsupported finish reason")
    inventory: list[ToolCall] = []
    for call in calls:
        if not isinstance(call, dict) or call.get("type") != "function":
            raise UnsupportedExchange("Only client function tools are supported")
        identifier = string(call.get("id"), "tool call ID")
        if any(known.tool_use_id == identifier for known in inventory):
            raise UnsupportedExchange("Duplicate tool call ID")
        function = call.get("function")
        if not isinstance(function, dict):
            raise UnsupportedExchange("Invalid tool function")
        name = string(function.get("name"), "tool name")
        arguments = decode_json(function["arguments"]) if isinstance(function.get("arguments"), str) else None
        if not isinstance(arguments, dict):
            raise UnsupportedExchange("Function arguments must be an unambiguous JSON object")
        inventory.append(ToolCall(tool_use_id=identifier, tool_name=name, tool_input=arguments))
    return inventory


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


def _releasable(value: dict) -> bool:
    """Accept a consistent applied outcome for an independently matched named tool.

    A deferred acknowledgement cannot authorize a named call under enforcement.
    Valid grading-failure outcomes still follow the administrator's policy.
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


def _refused(value: dict) -> bool:
    """Recognize a consistent enforced ``deny`` or ``escalate``, including one from the failure policy."""
    decision = value.get("decision")
    return (
        _consistent_failure(value)
        and value.get("enforcement_mode") == "enforce"
        and value.get("decision_source") in _DECIDING_SOURCES
        and decision in {"deny", "escalate"}
        and value.get("judged_decision") == decision
    )


def _reason(value: dict) -> str:
    """Watcher's public explanation for a refusal; grader prompts and scores are never included."""
    verdict, failure = value.get("verdict"), value.get("grading_error")
    verdict = verdict if isinstance(verdict, dict) else {}
    failure = failure if isinstance(failure, dict) else {}
    for candidate in (verdict.get("explanation"), verdict.get("summary"), failure.get("message")):
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return "Watcher did not give a reason."


@dataclass(frozen=True)
class Evaluation:
    """Watcher's verdict on one response.

    ``verified`` is False when the decisions cannot be matched one-to-one to
    the delivered calls or carry inconsistent provenance; nothing may be
    released then. Otherwise ``denials`` lists the calls Watcher refused.
    """

    verified: bool
    denials: list[Denial] = field(default_factory=list)

    @property
    def released(self) -> bool:
        """Whether the response may reach the client unchanged."""
        return self.verified and not self.denials


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
    provider: str,
    withheld_ids: list[str] | None = None,
) -> Any:
    """Send one raw exchange to Watcher's pre-tool-use hook and return its outputs unchecked.

    Every exchange declares that this gateway withholds the calls Watcher
    refuses (``withholds_refused_calls``), so Watcher records an enforced
    refusal as blocked. ``withheld_ids`` names the calls a delivered reply
    replaced, for the recording of that reply. A Watcher server older than
    these fields rejects them; the exchange is then sent once more without
    them, so it is still evaluated and recorded, with refusals left pending.
    """
    fields: dict[str, Any] = {
        "request_body": request,
        "response_body": response,
        "url": "/v1/chat/completions",
        "provider": provider,
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


async def evaluate(
    watcher: AsyncWatcherClient,
    request: dict,
    response: dict,
    *,
    conversation_id: str,
    user_agent: str | None = None,
    provider: str = "gateway",
) -> Evaluation:
    """Submit the exchange to Watcher and match every delivered call to exactly one decision.

    Send the original provider bodies through the public raw hook (see
    ``submit``); Watcher owns conversion, tool selection and policy. A
    gateway-generated exchange ID is supplied, and one without
    ``CONVERSATION_PREFIX`` is refused before Watcher is called. For
    Chat-Completions-compatible harness traffic, the backend may additionally
    group recognized native session IDs. No settings override or
    client-supplied grouping ID is used. An empty result admits text-only
    output, never an uncovered call.
    """
    check_conversation_id(conversation_id)
    validate_request(request)
    calls = {call.tool_use_id: call for call in client_calls(response)}
    outputs = await submit(
        watcher, request, response, conversation_id=conversation_id, user_agent=user_agent, provider=provider
    )
    if not isinstance(outputs, list) or len(outputs) != len(calls):
        return Evaluation(verified=False)
    remaining = set(calls)
    denials: list[Denial] = []
    for output in outputs:
        value = output.to_dict()
        identifier = value.get("tool_use_id")
        if not isinstance(identifier, str) or identifier not in remaining or "status_code" in value:
            return Evaluation(verified=False)
        remaining.remove(identifier)
        if _refused(value):
            call = calls[identifier]
            denials.append(
                Denial(
                    tool_use_id=identifier,
                    tool_name=call.tool_name,
                    tool_input=call.tool_input,
                    reason=_reason(value),
                    is_escalation=value["decision"] == "escalate",
                    user_can_approve=value["decision"] == "escalate" and value.get("decision_source") in _GRADED,
                )
            )
        elif not _releasable(value):
            return Evaluation(verified=False)
    return Evaluation(verified=not remaining, denials=denials)
