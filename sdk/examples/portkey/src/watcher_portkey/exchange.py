"""Validate gateway exchanges and turn Watcher's outcomes into release or refusal decisions.

The bridge's webhooks receive Portkey's parsed Chat Completions request and
response. These helpers check that the exchange is within this deployment's
delivery limits, submit it unchanged to Watcher's raw-format pre-tool-use hook
and match every outcome to a client-visible call by its native ID. The result
is one of three answers: release (every call allowed or deferred), refuse
(every call has a verified outcome and at least one is an enforced deny or
escalate), or an error when the outcomes cannot be verified, which always
withholds the response.
"""

import json
from typing import Any

import structlog

from watcher_portkey.replan import ToolDenial, tool_calls
from watcher_sdk import AsyncWatcherClient, WatcherAPIError

# Every conversation ID the gateway plugin generates starts with this prefix
# (see gateway/server.mjs). Watcher labels sessions whose ID carries a
# registered gateway prefix as Gateway, so the bridge refuses any other ID.
CONVERSATION_PREFIX = "portkey:"
_SOURCES = {"threshold", "rule", "triage", "policy_gateway", "grading_error"}
# Decision sources that read the conversation, so a user's approval can change
# their next decision. Rules, thresholds and grading-failure policy do not.
_GRADED = {"policy_gateway", "triage"}
_FAILURE_CODES = {"timeout", "at_capacity", "allowance_exhausted", "grader_failed", "no_result"}
# Raw-format request fields newer than some Watcher servers this example may
# run against. Those servers forbid unknown fields, so they answer HTTP 422 with
# an ``extra_forbidden`` validation error located at the field.
_GATEWAY_FIELDS = frozenset({"withheld_tool_use_ids", "withholds_refused_calls"})

logger = structlog.get_logger(__name__)


class UnsupportedExchange(ValueError):
    """The gateway cannot safely deliver this request or response."""


class UnverifiedDecision(ValueError):
    """Watcher's outcomes do not prove a release or a refusal for every delivered call."""


def _object(pairs: list[tuple[str, Any]]) -> dict:
    """Reject duplicate JSON keys rather than interpreting an ambiguous envelope."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise UnsupportedExchange("Duplicate JSON key")
        result[key] = value
    return result


def decode_json(value: str | bytes) -> Any:
    """Decode gateway envelopes and argument syntax without rewriting their bodies."""

    def invalid_constant(value: str) -> None:
        raise UnsupportedExchange("Non-finite JSON number")

    return json.loads(value, object_pairs_hook=_object, parse_constant=invalid_constant)


def string(value: Any, label: str) -> str:
    """Return a nonempty string, or raise ``UnsupportedExchange`` naming ``label``."""
    if not isinstance(value, str) or not value:
        raise UnsupportedExchange(f"Missing or invalid {label}")
    return value


def require_conversation_id(value: Any) -> str:
    """Require the gateway's documented prefix followed by a nonempty identifier."""
    identity = string(value, "gateway conversation ID")
    if not identity.startswith(CONVERSATION_PREFIX) or identity == CONVERSATION_PREFIX:
        raise UnsupportedExchange("Gateway conversation ID lacks the documented prefix")
    return identity


def validate_request(request: Any) -> None:
    """Check this deployment's native delivery limits before provider invocation.

    Watcher performs transcript conversion. This guard limits the example to one
    buffered Chat Completions choice, complete client-provided history and
    function tools. Streams are rejected: Portkey delivers a stream before its
    response hook's verdict, so the hook could not withhold a streamed call.
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
    if "audio" in (request.get("modalities") or []):
        raise UnsupportedExchange("Audio output is unsupported")
    tools = request.get("tools", [])
    if not isinstance(tools, list) or any(
        not isinstance(tool, dict) or tool.get("type") != "function" for tool in tools
    ):
        raise UnsupportedExchange("Only client function tools are supported")
    messages = request.get("messages")
    if not isinstance(messages, list) or not messages or any(not isinstance(message, dict) for message in messages):
        raise UnsupportedExchange("A complete messages list is required")


def client_calls(response: Any) -> dict[tuple[str | int, ...], str]:
    """Inventory every executable proposal in the body the client would receive.

    This does not select calls for grading or convert the transcript. A call the
    backend skips as superseded context still needs a decision before a gateway
    releases it. Unique native IDs bind decisions to the calls being delivered.
    """
    choices = response.get("choices") if isinstance(response, dict) else None
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise UnsupportedExchange("One complete response choice is required")
    choice = choices[0]
    if type(choice.get("index")) is not int or choice["index"] != 0:
        raise UnsupportedExchange("Unexpected choice index")
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise UnsupportedExchange("Response must contain an assistant message")
    if message.get("function_call") is not None or message.get("audio") is not None:
        raise UnsupportedExchange("Unsupported executable or audio output")
    calls = message.get("tool_calls", [])
    if calls is None:
        calls = []
    if not isinstance(calls, list):
        raise UnsupportedExchange("Invalid tool proposals")
    reason = choice.get("finish_reason")
    if reason not in ("stop", "tool_calls", "length", "content_filter"):
        raise UnsupportedExchange("Unsupported completion finish reason")
    if calls and reason not in ("stop", "tool_calls"):
        raise UnsupportedExchange("Incomplete executable response")
    paths: dict[tuple[str | int, ...], str] = {}
    seen = set()
    for index, call in enumerate(calls):
        if not isinstance(call, dict) or call.get("type") != "function":
            raise UnsupportedExchange("Unsupported client tool type")
        identifier = string(call.get("id"), "native call ID")
        if identifier in seen:
            raise UnsupportedExchange("Duplicate native call ID")
        seen.add(identifier)
        function = call.get("function")
        if not isinstance(function, dict) or not isinstance(function.get("arguments"), str):
            raise UnsupportedExchange("Invalid function proposal")
        string(function.get("name"), "function name")
        if not isinstance(decode_json(function["arguments"]), dict):
            raise UnsupportedExchange("Function arguments must be a JSON object")
        paths[("choices", 0, "message", "tool_calls", index)] = identifier
    return paths


def _consistent_failure(value: dict) -> bool:
    """A grading-failure decision must carry a known failure; no other decision may carry one."""
    failure = value.get("grading_error")
    if value.get("decision_source") == "grading_error":
        return (
            isinstance(failure, dict)
            and failure.get("code") in _FAILURE_CODES
            and isinstance(failure.get("message"), str)
        )
    return failure is None


def releasable(value: dict) -> bool:
    """Accept consistent applied allow/deferred; malformed provenance never grants release."""
    decision, mode, source = value.get("decision"), value.get("enforcement_mode"), value.get("decision_source")
    if not _consistent_failure(value):
        return False
    if mode == "paused":
        return decision == "deferred" and source == "bypass" and value.get("judged_decision") is None
    if source not in _SOURCES:
        return False
    if mode == "observe":
        return decision == "deferred" and value.get("judged_decision") in {"allow", "deny", "escalate"}
    return mode == "enforce" and decision == "allow" and value.get("judged_decision") == "allow"


def refused(value: dict) -> bool:
    """Accept a consistent enforced deny or escalate as a refusal.

    The judged decision may differ from the applied one only where Watcher
    promotes a graded deny to an escalation; it is never allow or missing.
    """
    return (
        _consistent_failure(value)
        and value.get("enforcement_mode") == "enforce"
        and value.get("decision") in {"deny", "escalate"}
        and value.get("judged_decision") in {"deny", "escalate"}
        and value.get("decision_source") in _SOURCES
    )


def _predates_gateway_fields(error: WatcherAPIError) -> bool:
    """Whether Watcher rejected the exchange as an older server that does not know the gateway fields."""
    body: Any = error.body
    if error.status_code != 422 or not isinstance(body, dict):
        return False
    detail: Any = body.get("detail")
    if not isinstance(detail, list):
        return False
    for item in detail:
        entry: Any = item
        if not isinstance(entry, dict) or entry.get("type") != "extra_forbidden":
            continue
        location: Any = entry.get("loc")
        if isinstance(location, list) and location and location[-1] in _GATEWAY_FIELDS:
            return True
    return False


async def decide(
    watcher: AsyncWatcherClient,
    request: dict,
    response: dict,
    *,
    conversation_id: str,
    url: str = "/v1/chat/completions",
    provider: str = "openai",
    user_agent: str | None = None,
    timeout: float | None = None,
    withheld_ids: list[str] | None = None,
) -> list[ToolDenial]:
    """Send the exchange to Watcher and return its refusals; an empty list releases the response.

    No settings override is sent. Backend conversion and call selection are
    authoritative for grading; the independent delivery inventory prevents a
    skipped proposal reaching the client without permission. Empty results admit
    text-only output, never an uncovered client tool. Ingestion remains asynchronous.

    Every exchange declares that refused calls are withheld
    (``withholds_refused_calls``), so Watcher records an enforced refusal as
    blocked. ``withheld_ids`` names the calls withheld in favour of
    ``response``, when it is the reply delivered after a refusal, so Watcher
    can show them before it. A Watcher server older than this example rejects
    both fields; the exchange is then sent once more without them, so it is
    still evaluated and recorded.

    Raises ``UnsupportedExchange`` for an exchange outside the delivery limits,
    before Watcher is called, including a conversation ID without
    ``CONVERSATION_PREFIX``. Raises ``UnverifiedDecision`` unless every
    delivered call has exactly one outcome that is either releasable or a
    refusal. ``timeout`` bounds each Watcher request in seconds.
    """
    require_conversation_id(conversation_id)
    validate_request(request)
    expected = set(client_calls(response).values())
    calls = {call.tool_use_id: call for call in tool_calls(response)}
    if user_agent is not None and not isinstance(user_agent, str):
        raise UnsupportedExchange("Invalid client User-Agent")
    exchange: dict[str, Any] = {
        "request_body": request,
        "response_body": response,
        "url": string(url, "client-facing URL"),
        "provider": string(provider, "provider"),
        "user_agent": user_agent,
        "external_ids": {"other": conversation_id},
        "timeout": timeout,
    }
    try:
        outcomes = await watcher.pre_tool_use_hook(
            **exchange, withheld_tool_use_ids=withheld_ids, withholds_refused_calls=True
        )
    except WatcherAPIError as error:
        if not _predates_gateway_fields(error):
            raise
        logger.warning("watcher_predates_gateway_fields", conversation_id=conversation_id)
        outcomes = await watcher.pre_tool_use_hook(**exchange)
    if not isinstance(outcomes, list):
        raise UnverifiedDecision("Watcher returned no outcome list")
    decided: set[str] = set()
    denials: list[ToolDenial] = []
    for outcome in outcomes:
        serialize = getattr(outcome, "to_dict", None)
        if not callable(serialize):
            raise UnverifiedDecision("Watcher returned an unreadable outcome")
        value = serialize()
        identifier = value.get("tool_use_id")
        if not isinstance(identifier, str) or identifier not in expected or identifier in decided:
            raise UnverifiedDecision("Watcher's outcome does not match one delivered call")
        decided.add(identifier)
        if releasable(value):
            continue
        if not refused(value):
            raise UnverifiedDecision("Watcher's outcome is neither a release nor a refusal")
        verdict = value.get("verdict")
        explanation = verdict.get("explanation") if isinstance(verdict, dict) else None
        call = calls[identifier]
        denials.append(
            ToolDenial(
                tool_use_id=call.tool_use_id,
                tool_name=call.tool_name,
                tool_input=call.tool_input,
                reason=explanation if isinstance(explanation, str) and explanation.strip() else "Approval is required.",
                is_escalation=value["decision"] == "escalate",
                user_can_approve=value["decision"] == "escalate" and value["decision_source"] in _GRADED,
            )
        )
    if decided != expected:
        raise UnverifiedDecision("A delivered call has no Watcher outcome")
    return denials
