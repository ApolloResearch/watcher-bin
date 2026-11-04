"""Validate gateway delivery, send provider exchanges to Watcher and recover from refusals.

The Bifrost plugin (``gateway/main.go``) calls this private service twice per
client request:

- ``/validate`` before the provider call: checks the request is supported and
  returns it with Watcher's fixed system notice (``system_notice``) for the
  plugin to install, or verifies an alternative marker and tells the plugin to
  pass the bridge's own nested request through ungraded.
- ``/evaluate`` with the complete response: sends the exchange to Watcher and
  either releases it unchanged or returns a replacement completion holding
  Watcher's notices and an approved alternative or the model's final question
  to the user (``alternatives``). Nothing from a refused proposal is released.

Every exchange tells Watcher that refused calls are withheld
(``withholds_refused_calls``), so Watcher records an enforced deny or
escalation as blocked when it decides it. After a replacement has been sent,
the bridge records it in the client's session as the client received it and
names the calls it withheld (``withheld_tool_use_ids``), so Watcher can show
them before it (``record_delivery``). A Watcher server older than these fields
rejects them; the bridge then sends the exchange once more without them.
"""

import asyncio
import base64
import hmac
import json
import os
import re
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast
from urllib.parse import urlsplit

import httpx
import structlog
import typer

from watcher_bifrost.alternatives import Assessment, Gateway, MarkerLedger, marker_key, recover
from watcher_bifrost.replan import ToolDenial, tool_calls
from watcher_bifrost.system_notice import with_system_notice
from watcher_sdk import AsyncWatcherClient, WatcherAPIError

MAX_BODY = 8 * 1024 * 1024
# One deadline for the original decision, every alternative and the final
# generation. It stays below the plugin's 425-second bridge timeout, which is
# the gateway's bound on a transport hook.
DEADLINE_SECONDS = 420.0
# Headers Bifrost authenticates a client and selects its provider key by
# (virtual keys, bearer/API keys, a stored key by name or ID, direct-key mode)
# and the session identity its session affinity binds keys and routes to
# (x-bf-session-id with its TTL and switch, and the coding-harness session
# headers Bifrost falls back to). The plugin forwards them so an alternative is
# generated as the same client with the same key, session binding, routing,
# budgets and isolation; they are held in memory for one request and never
# logged. WATCHER_ALTERNATIVE_HEADERS adds operator-defined headers Bifrost
# governance is configured to require.
FORWARDED_HEADERS = frozenset(
    {
        "authorization",
        "api-key",
        "x-api-key",
        "x-goog-api-key",
        "x-bf-vk",
        "x-bf-api-key",
        "x-bf-api-key-id",
        "x-bf-direct-key",
        "x-bf-session-id",
        "x-bf-session-ttl",
        "x-bf-session-affinity",
        "x-claude-code-session-id",
        "x-session-affinity",
        "x-session-id",
        "session-id",
        "session_id",
        "thread-id",
        "conversation_id",
    }
)
# Headers that describe the transport or the marker; never forwarded.
_RESERVED_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "content-type",
        "content-encoding",
        "transfer-encoding",
        "connection",
        "accept-encoding",
        "x-watcher-alternative",
    }
)
_HEADER_NAME = re.compile(r"[A-Za-z0-9-]+")
# Decision sources that read the conversation, so a user's approval can change
# their next decision. Rules, thresholds and grading-failure policy do not.
_GRADED = {"policy_gateway", "triage"}
_DECIDING_SOURCES = {"threshold", "rule", "triage", "policy_gateway", "grading_error"}

# Every conversation ID the gateway plugin generates starts with this prefix
# (see gateway/main.go). Watcher labels sessions whose ID carries a
# registered gateway prefix as Gateway, so the bridge refuses any other ID.
CONVERSATION_PREFIX = "bifrost:"
# Raw-format request fields newer than some Watcher servers this example may run
# against. Those servers forbid unknown fields, so they answer HTTP 422 with an
# ``extra_forbidden`` validation error located at the field.
_GATEWAY_FIELDS = frozenset({"withheld_tool_use_ids", "withholds_refused_calls"})

logger = structlog.get_logger(__name__)


class UnsupportedExchange(ValueError):
    """The gateway cannot safely deliver this request or response."""


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


def encode_json(value: Any) -> bytes:
    """Serialise a bridge reply compactly as UTF-8, the way ``Gateway.generate`` encodes alternatives.

    The plugin forwards a reply's ``request`` upstream and its ``response`` to
    the client as these exact bytes, and checks each against the same limit as
    the client's own body. A space after every separator would grow a compact
    client request by a byte per separator and push one near the limit over it.
    """
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise UnsupportedExchange(f"Missing or invalid {label}")
    return value


def _conversation_id(value: Any) -> str:
    """Require the gateway's documented prefix followed by a nonempty identifier."""
    identity = _string(value, "gateway conversation ID")
    if not identity.startswith(CONVERSATION_PREFIX) or identity == CONVERSATION_PREFIX:
        raise UnsupportedExchange("Gateway conversation ID lacks the documented prefix")
    return identity


def validate_request(request: Any, *, allow_stream: bool = False) -> None:
    """Check this deployment's native delivery limits before provider invocation.

    Watcher performs transcript conversion. This guard limits the example to one
    Chat Completions choice, complete client-provided history and function tools.
    Stream=true needs the native plugin's complete-response buffering path.
    """
    if not isinstance(request, dict):
        raise UnsupportedExchange("Request must be an object")
    _string(request.get("model"), "model")
    if type(request.get("stream", False)) is not bool:
        raise UnsupportedExchange("stream must be a boolean")
    if request.get("stream") and not allow_stream:
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
        identifier = _string(call.get("id"), "native call ID")
        if identifier in seen:
            raise UnsupportedExchange("Duplicate native call ID")
        seen.add(identifier)
        function = call.get("function")
        if not isinstance(function, dict) or not isinstance(function.get("arguments"), str):
            raise UnsupportedExchange("Invalid function proposal")
        _string(function.get("name"), "function name")
        if not isinstance(decode_json(function["arguments"]), dict):
            raise UnsupportedExchange("Function arguments must be a JSON object")
        paths[("choices", 0, "message", "tool_calls", index)] = identifier
    return paths


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
    """Accept consistent applied allow/deferred; malformed provenance never grants release."""
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


def _reason(value: dict) -> str:
    """Watcher's public explanation for a refusal; grader prompts and scores are never included."""
    verdict, failure = value.get("verdict"), value.get("grading_error")
    verdict = verdict if isinstance(verdict, dict) else {}
    failure = failure if isinstance(failure, dict) else {}
    for candidate in (verdict.get("explanation"), verdict.get("summary"), failure.get("message")):
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return "Approval is required."


def _predates_gateway_fields(error: WatcherAPIError) -> bool:
    """Whether Watcher rejected an exchange as an older server that does not know ``_GATEWAY_FIELDS``."""
    detail = error.body.get("detail") if error.status_code == 422 and isinstance(error.body, dict) else None
    if not isinstance(detail, list):
        return False
    for item in detail:
        entry = cast(dict[str, Any], item) if isinstance(item, dict) else {}
        location = entry.get("loc")
        if entry.get("type") == "extra_forbidden" and isinstance(location, list) and location:
            if location[-1] in _GATEWAY_FIELDS:
                return True
    return False


async def _send(
    watcher: AsyncWatcherClient,
    request: dict,
    response: dict,
    *,
    conversation_id: str,
    url: str,
    provider: str,
    user_agent: str | None,
    withheld: list[str] | None = None,
) -> object:
    """Send one raw exchange in ``conversation_id``, declaring that refused calls are withheld.

    ``withheld`` names the calls withheld in favour of ``response``. A server
    that predates those fields rejects them with HTTP 422; the exchange is then
    sent once more without them, so it is still evaluated and recorded, and
    its refusals stay pending rather than blocked.
    """

    async def send(withheld_ids: list[str] | None, withholds: bool | None) -> object:
        return await watcher.pre_tool_use_hook(
            request_body=request,
            response_body=response,
            url=url,
            provider=provider,
            user_agent=user_agent,
            external_ids={"other": conversation_id},
            withheld_tool_use_ids=withheld_ids,
            withholds_refused_calls=withholds,
        )

    try:
        return await send(withheld, True)
    except WatcherAPIError as error:
        if not _predates_gateway_fields(error):
            raise
        logger.warning("watcher_predates_gateway_fields", conversation_id=conversation_id)
        return await send(None, None)


async def evaluate(
    watcher: AsyncWatcherClient,
    request: dict,
    response: dict,
    *,
    conversation_id: str,
    allow_stream: bool = False,
    url: str = "/v1/chat/completions",
    provider: str = "openai",
    user_agent: str | None = None,
) -> Assessment:
    """Send the original exchange to Watcher and match every delivered call to exactly one decision.

    No settings override is sent. Backend conversion and call selection are
    authoritative for grading; the independent delivery inventory prevents a
    skipped proposal reaching the client without permission. The result is
    verified only when every delivered call has one consistent allow/deferred
    or enforced deny/escalate outcome; ``denials`` lists the refused calls, and
    a verified result without denials releases the response. Empty outcomes
    admit text-only output, never an uncovered client tool. Ingestion remains
    asynchronous. A conversation ID without ``CONVERSATION_PREFIX`` is refused
    before Watcher is called. The exchange declares that refused calls are
    withheld (``_send``).
    """
    _conversation_id(conversation_id)
    validate_request(request, allow_stream=allow_stream)
    expected = set(client_calls(response).values())
    if user_agent is not None and not isinstance(user_agent, str):
        raise UnsupportedExchange("Invalid client User-Agent")
    outcomes = await _send(
        watcher,
        request,
        response,
        conversation_id=conversation_id,
        url=_string(url, "client-facing URL"),
        provider=_string(provider, "provider"),
        user_agent=user_agent,
    )
    if not isinstance(outcomes, list):
        return Assessment(verified=False)
    calls = {call.tool_use_id: call for call in tool_calls(response)}
    decided: set[str] = set()
    denials: list[ToolDenial] = []
    for outcome in outcomes:
        serialize = getattr(outcome, "to_dict", None)
        if not callable(serialize):
            return Assessment(verified=False)
        value = serialize()
        identifier = value.get("tool_use_id")
        if not isinstance(identifier, str) or identifier not in expected or identifier in decided:
            return Assessment(verified=False)
        decided.add(identifier)
        if refused(value):
            call = calls[identifier]
            denials.append(
                ToolDenial(
                    tool_use_id=identifier,
                    tool_name=call.tool_name,
                    tool_input=call.tool_input,
                    reason=_reason(value),
                    is_escalation=value["decision"] == "escalate",
                    user_can_approve=value["decision"] == "escalate" and value.get("decision_source") in _GRADED,
                )
            )
        elif not releasable(value):
            return Assessment(verified=False)
    return Assessment(verified=decided == expected, denials=denials)


@dataclass(frozen=True)
class Delivery:
    """A replacement completion to record in the client's session after it was sent.

    ``request`` is the client's request (with the system notice) and
    ``response`` the completion the client received; ``withheld`` names the
    calls withheld in its favour, as ``recover`` returned them.
    """

    request: dict
    response: dict
    withheld: list[str]
    conversation_id: str
    url: str
    provider: str
    user_agent: str | None


async def record_delivery(watcher: AsyncWatcherClient, delivery: Delivery) -> None:
    """Record what the client received after a refusal; failures are logged, never raised.

    Watcher's transcript then matches the client's next request, and the
    delivered message carries the withheld call IDs. Calls the replacement
    released were already graded as the approved alternative, so they are
    moved into the request's history and the recorded response is an empty
    assistant message: nothing is graded again. A text-only replacement is
    recorded as the response itself.
    """
    request, response = delivery.request, delivery.response
    choice = response["choices"][0]
    if choice["message"].get("tool_calls"):
        request = {**request, "messages": [*request["messages"], choice["message"]]}
        empty = {**choice, "message": {"role": "assistant", "content": None}, "finish_reason": "stop"}
        response = {**response, "choices": [empty]}
    try:
        await _send(
            watcher,
            request,
            response,
            conversation_id=delivery.conversation_id,
            url=delivery.url,
            provider=delivery.provider,
            user_agent=delivery.user_agent,
            withheld=delivery.withheld or None,
        )
    except Exception as error:
        logger.warning(
            "delivery_not_recorded", conversation_id=delivery.conversation_id, error_type=type(error).__name__
        )
        return
    logger.info("delivery_recorded", conversation_id=delivery.conversation_id, withheld=len(delivery.withheld))


def validate(envelope: dict, ledger: MarkerLedger, *, allow_stream: bool) -> tuple[int, dict]:
    """Answer the plugin's pre-provider check: (HTTP status, reply).

    ``envelope["body"]`` is the exact client body, base64-encoded so that a
    marker is checked against the bytes Bifrost received. With a marker, a
    valid, unexpired, unused one for exactly that body returns ``passthrough``
    (the bridge only signs buffered requests); anything else is 403
    ``reject``. Without one, a supported request returns ``grade``, plus the
    request carrying the system notice when it lacked it. Unsupported requests,
    and requests the notice would push past ``MAX_BODY`` once encoded with
    ``encode_json``, raise ``UnsupportedExchange``.
    """
    raw = base64.b64decode(_string(envelope.get("body"), "request body"), validate=True)
    if len(raw) > MAX_BODY:
        raise UnsupportedExchange("Request exceeds the gateway limit")
    marker = envelope.get("marker", "")
    if not isinstance(marker, str):
        raise UnsupportedExchange("Invalid alternative marker")
    if marker:
        if not ledger.accept(marker, raw):
            logger.warning("alternative_marker_rejected")
            return 403, {"action": "reject"}
        validate_request(decode_json(raw))
        return 200, {"action": "passthrough"}
    request = decode_json(raw)
    validate_request(request, allow_stream=allow_stream)
    noticed = with_system_notice(request)
    if noticed is None:
        return 200, {"action": "grade"}
    if len(encode_json(noticed)) > MAX_BODY:
        raise UnsupportedExchange("Request with Watcher's system notice exceeds the gateway limit")
    return 200, {"action": "grade", "request": noticed}


def alternative_headers(extra: str) -> frozenset[str]:
    """``FORWARDED_HEADERS`` plus the comma-separated header names in ``extra``, lowercased.

    Mirrors the plugin's WATCHER_ALTERNATIVE_HEADERS parsing: names must be
    header tokens and may not be transport headers or the marker.
    """
    names = set(FORWARDED_HEADERS)
    for name in (part.strip() for part in extra.split(",")):
        if not name:
            continue
        if not _HEADER_NAME.fullmatch(name) or name.lower() in _RESERVED_HEADERS:
            raise ValueError("Invalid WATCHER_ALTERNATIVE_HEADERS")
        names.add(name.lower())
    return frozenset(names)


def _credentials(value: Any, allowed: frozenset[str]) -> dict[str, str]:
    """The client's authentication and key-selection headers, limited to ``allowed``."""
    if not isinstance(value, dict):
        raise UnsupportedExchange("Invalid client credentials")
    credentials = {}
    for name, header in value.items():
        if not isinstance(name, str) or name.lower() not in allowed or not isinstance(header, str):
            raise UnsupportedExchange("Invalid client credentials")
        credentials[name.lower()] = header
    return credentials


async def respond(
    watcher: AsyncWatcherClient,
    gateway: Gateway,
    envelope: dict,
    *,
    allow_stream: bool,
    deadline: float,
    forwarded: frozenset[str] = FORWARDED_HEADERS,
) -> tuple[dict, Delivery | None]:
    """Answer the plugin's response check: ``release``, ``replace``, ``structured_refusal`` or ``withhold``.

    ``structured_refusal`` answers a refusal in a request asking for JSON output
    (``response_format`` ``json_object`` or ``json_schema``), where a notice
    cannot be delivered; the plugin returns an explicit 403 error.

    The original decision and the whole recovery share ``deadline`` (event
    loop clock). An unverifiable original decision withholds the response; a
    timeout or Watcher error there propagates, and the plugin withholds too.
    A replacement larger than ``MAX_BODY`` is withheld rather than truncated.
    ``forwarded`` lists the client headers alternatives may carry.

    Alternatives are graded in the client's own conversation. A ``replace``
    answer comes with the ``Delivery`` to record once it has been sent
    (``record_delivery``); every other answer comes with None.
    """
    request, response = envelope.get("request"), envelope.get("response")
    if not isinstance(request, dict) or not isinstance(response, dict):
        raise UnsupportedExchange("Exchange request and response must be objects")
    metadata = envelope.get("metadata", {})
    if not isinstance(metadata, dict):
        raise UnsupportedExchange("Invalid exchange metadata")
    conversation_id = _conversation_id(metadata.get("watcher_conversation_id"))
    credentials = _credentials(envelope.get("credentials") or {}, forwarded)
    url, provider = metadata.get("watcher_url"), metadata.get("watcher_provider")
    user_agent = metadata.get("watcher_user_agent")
    async with asyncio.timeout_at(deadline):
        assessment = await evaluate(
            watcher,
            request,
            response,
            conversation_id=conversation_id,
            allow_stream=allow_stream,
            url=url,
            provider=provider,
            user_agent=user_agent,
        )
    if not assessment.verified:
        logger.warning("decisions_unmatched", conversation_id=conversation_id)
        return {"action": "withhold"}, None
    if not assessment.denials:
        return {"action": "release"}, None
    logger.info(
        "proposal_refused",
        conversation_id=conversation_id,
        denied=len(assessment.denials),
        escalated=any(denial.is_escalation for denial in assessment.denials),
    )
    response_format = request.get("response_format")
    if isinstance(response_format, dict) and response_format.get("type") in ("json_object", "json_schema"):
        # A text notice would make the requested JSON content unparseable, so the
        # plugin returns an explicit error and no alternative is generated.
        logger.info("structured_output_refusal", conversation_id=conversation_id)
        return {"action": "structured_refusal"}, None

    async def grade(history: dict, candidate: dict) -> Assessment:
        return await evaluate(
            watcher,
            history,
            candidate,
            conversation_id=conversation_id,
            url=url,
            provider=provider,
            user_agent=user_agent,
        )

    delivered, withheld = await recover(
        gateway,
        grade,
        client_calls,
        request,
        response,
        assessment.denials,
        credentials=credentials,
        conversation_id=conversation_id,
        deadline=deadline,
    )
    if len(encode_json(delivered)) > MAX_BODY:
        logger.warning("replacement_too_large", conversation_id=conversation_id)
        return {"action": "withhold"}, None
    delivery = Delivery(request, delivered, withheld, conversation_id, url, provider, user_agent)
    return {"action": "replace", "response": delivered}, delivery


def gateway_origin(value: Any) -> str:
    """Require an http(s) origin for Bifrost's client listener, without credentials, path or query."""
    url = _string(value, "gateway URL")
    parts = urlsplit(url)
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username is not None
        or parts.path.strip("/")
        or parts.query
        or parts.fragment
    ):
        raise ValueError("WATCHER_GATEWAY_URL must be the gateway's http(s) origin")
    return url.rstrip("/")


def serve(host: str, port: int, *, allow_stream: bool = False) -> None:
    """Start an authenticated, gateway-private bridge using the public Watcher SDK.

    Reads ``WATCHER_BRIDGE_TOKEN``, ``WATCHER_BASE_URL``, ``WATCHER_API_KEY``,
    ``WATCHER_GATEWAY_URL`` (the origin alternatives are requested from) and the
    optional ``WATCHER_ALTERNATIVE_HEADERS``, and refuses to start without
    ingestion permission.
    """
    token = _string(os.environ.get("WATCHER_BRIDGE_TOKEN"), "bridge token")
    api_url = _string(os.environ.get("WATCHER_BASE_URL"), "Watcher URL")
    api_key = _string(os.environ.get("WATCHER_API_KEY"), "Watcher API key")

    async def check_ingestion() -> None:
        async with AsyncWatcherClient(api_url, api_key=api_key) as watcher:
            permission = await watcher.check_permissions(["sessions:ingest"])
            if permission.granted is not True or permission.missing:
                raise PermissionError("Watcher credential requires sessions:ingest")

    asyncio.run(check_ingestion())
    # Alternative settings are read after the permission check, so a credential
    # without ingestion permission is reported first.
    gateway_url = gateway_origin(os.environ.get("WATCHER_GATEWAY_URL"))
    forwarded = alternative_headers(os.environ.get("WATCHER_ALTERNATIVE_HEADERS", ""))
    ledger = MarkerLedger(marker_key(api_key))

    async def evaluate_exchange(envelope: dict) -> tuple[dict, Delivery | None]:
        deadline = asyncio.get_running_loop().time() + DEADLINE_SECONDS
        async with (
            AsyncWatcherClient(api_url, api_key=api_key) as watcher,
            httpx.AsyncClient(base_url=gateway_url, timeout=DEADLINE_SECONDS, follow_redirects=False) as client,
        ):
            gateway = Gateway(client=client, ledger=ledger, max_body=MAX_BODY)
            return await respond(
                watcher, gateway, envelope, allow_stream=allow_stream, deadline=deadline, forwarded=forwarded
            )

    async def record(delivery: Delivery) -> None:
        async with AsyncWatcherClient(api_url, api_key=api_key) as watcher:
            await record_delivery(watcher, delivery)

    class Handler(BaseHTTPRequestHandler):
        """Validate bridge credentials without logging native transcript content."""

        def log_message(self, format: str, *_args: Any) -> None:
            pass

        def do_POST(self) -> None:
            refusal = {"action": "withhold" if self.path == "/evaluate" else "reject"}
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self._reply(401, refusal)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                # A base64-encoded request, or a request plus its complete
                # response, each fit within three body limits.
                if not 0 < length <= 3 * MAX_BODY or self.headers.get("Transfer-Encoding"):
                    raise UnsupportedExchange("Invalid body length")
                envelope = decode_json(self.rfile.read(length))
                if self.path not in ("/validate", "/evaluate") or not isinstance(envelope, dict):
                    raise UnsupportedExchange("Unknown bridge endpoint")
                delivery = None
                if self.path == "/validate":
                    status, reply = validate(envelope, ledger, allow_stream=allow_stream)
                else:
                    status, (reply, delivery) = 200, asyncio.run(evaluate_exchange(envelope))
                self._reply(status, reply)
                if delivery is not None:
                    # Recorded after the reply was sent, on its own thread, so
                    # recording never delays or fails what the client receives.
                    threading.Thread(target=asyncio.run, args=(record(delivery),), daemon=True).start()
            except (ValueError, TypeError, KeyError):
                self._reply(200, refusal)
            except Exception as error:
                logger.warning("bridge_request_failed", endpoint=self.path, error_type=type(error).__name__)
                self._reply(503, refusal)

        def _reply(self, status: int, payload: dict) -> None:
            data = encode_json(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    ThreadingHTTPServer((host, port), Handler).serve_forever()


app = typer.Typer(invoke_without_command=True, no_args_is_help=True, pretty_exceptions_enable=False)


@app.command("serve")
def serve_command(host: str = "127.0.0.1", port: int = 8765, allow_buffered_stream: bool = False) -> None:
    """Run the gateway-private bridge on the configured listener."""
    serve(host, port, allow_stream=allow_buffered_stream)


@app.command("help", hidden=True)
def help_command(context: typer.Context) -> None:
    typer.echo(context.parent.get_help() if context.parent else context.get_help())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
