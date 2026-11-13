"""A LiteLLM proxy guardrail that withholds tool calls until Watcher allows them.

Load ``watcher_callback`` through LiteLLM's ``callbacks`` setting. For every
Chat Completions, Responses or Anthropic Messages call, Watcher's raw-format
pre-tool-use hook converts provider-shaped exchanges, applies the organization's
policy and records its decisions. Streaming calls are evaluated individually at
their first reliable completion boundary; ``incremental`` builds those exchanges
and preserves prior approved content as history without grading it again.

Streams forward non-tool content immediately and hold each tool plus subsequent
events until it has an allow (or observe-mode deferred) decision. All output is
re-encoded from validated events. Refused calls become ordinary text notices.
After a denial the model is asked for another approach, with at most three
proposals per client request; alternatives stream through the same gates. After
an escalation, or a third blocked proposal, one last generation asks the model
to stop and put the question to the user, and any call it proposes is withheld.
A fixed question replaces that reply when it fails or times out, and follows
it when it has no text or was cut off.
Already released calls retain their approval; internal recovery receipts state
that their real execution results are unknown. Repeated denied or released
calls cannot escape the prior decision merely by changing their IDs.
Non-streamed proposals remain atomic until an entire allowed alternative can be
returned. Every request also carries a fixed system notice explaining Watcher's
notices (``system_notice``). Every Watcher
request declares that refused calls are withheld (``withholds_refused_calls``),
so Watcher records them as blocked. The recording of the delivered response
names every call withheld from a refused proposal
(``withheld_tool_use_ids``), so Watcher can show those calls before it; released
calls are never named. Watcher skips a named call it never evaluated, such as
one from a proposal refused locally as a repeat.

Each evaluation has a 300-second default deadline. After a refusal, its remaining
budget also bounds draining that proposal, replacement generation and evaluation.
Running out of it ends the response with an error, except during the last
generation, which falls back to the fixed question.
SSE comments keep every API alive without inventing model content; final text-only
recording never holds delivery. Transport failures remain explicit stream errors.

Configure ``WATCHER_API_URL`` and ``WATCHER_API_KEY`` on the proxy process,
or use ``WATCHER_AUTH_MODE=proxy`` with a server-owned proxy token and trusted
LiteLLM account emails (see ``proxy_auth``). Proxy mode scopes conversation
IDs by account and forwards only the authenticated account's identity.
Clients can send ``x-watcher-session-id`` as the sole conversation identity,
overriding native IDs. Without it, native Claude Code, Codex and OpenCode
metadata identifies each individual conversation, including children. Shared
SDK rules validate the chosen identity before generation and when recording.
"""

import asyncio
import json
import logging
import os
from collections import deque
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import aclosing, asynccontextmanager
from typing import Any, TypeVar, cast
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import HTTPException
from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy._types import UserAPIKeyAuth
from openai._streaming import SSEDecoder
from pydantic import BaseModel, ConfigDict, Field

from watcher_litellm.copilot import current_request
from watcher_litellm.delivery import StreamDelivery, compose_nonstream
from watcher_litellm.incremental import (
    Evaluation,
    IncrementalStream,
    PendingEvent,
    is_client_item,
    is_provider_tool_search,
)
from watcher_litellm.proxy_auth import account_identity, account_session, proxy_client, require_proxy_configuration
from watcher_litellm.replan import (
    ToolCall,
    ToolDenial,
    build_replan_request,
    client_tool_details,
    complete_replan,
    denial_notice,
    redundant_namespace,
    stop_notice,
)
from watcher_litellm.streams import (
    API,
    IncompleteStream,
    UnsupportedStream,
    as_dict,
    completed_response,
    response_dict,
    response_event,
)
from watcher_litellm.system_notice import system_notice_fields
from watcher_sdk import AsyncWatcherClient, WatcherAPIError, WatcherError
from watcher_sdk._generated.models import HookCallError, PreToolUseHookResponse
from watcher_sdk.capture import CaptureSource, ConversationIdentity, validate_conversation_id
from watcher_sdk.gateway_identity import IDENTITY_HEADER_NAMES, GatewayConversation, resolve_gateway_conversation

logger = logging.getLogger(__name__)

_ROUTES: dict[str, API] = {
    "/chat/completions": "chat_completions",
    "/responses": "responses",
    "/messages": "messages",
}
_RELEASED = {"allow", "deferred"}
# Decision sources that read the conversation, so a user's approval can change
# their next decision. Rules, thresholds and grading-failure policy do not.
_GRADED = {"policy_gateway", "triage"}
_NOTICE = "Watcher withheld the proposed tool call{plural} ({names}). No tool was run.\n\n{reasons}"
_MAX_PROPOSALS = 3
_T = TypeVar("_T")


class _Recovery(BaseModel):
    """State shared by one client request and its bounded replacement generations.

    Once a call is refused, its evaluation's deadline also bounds draining that
    proposal, generating alternatives, and evaluating them. The operation map
    prevents a fresh call ID from retrying a denied or already released action.
    ``withheld`` holds the IDs of every call withheld from a refused proposal,
    which the delivered response's recording names for Watcher.
    """

    deadline: float | None = None
    forbidden: dict[str, ToolDenial] = Field(default_factory=dict)
    released: list[ToolCall] = Field(default_factory=list)
    withheld: list[str] = Field(default_factory=list)

    def withheld_ids(self) -> list[str] | None:
        """The withheld calls to name on the delivered response's recording, or None when there are none.

        A released call is never named, even if a later proposal reused its ID.
        """
        released = {call.tool_use_id for call in self.released}
        return [call_id for call_id in self.withheld if call_id not in released] or None


class _Attempt(BaseModel):
    """A provider attempt's parser and decisions, filled by the streaming driver.

    ``final`` marks the generation that was asked to stop and ask the user:
    its calls are withheld without being sent to Watcher.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    stream: IncrementalStream
    final: bool = False
    denials: list[ToolDenial] = Field(default_factory=list)
    released: list[ToolCall] = Field(default_factory=list)


def _stops(denials: list[ToolDenial], number: int) -> bool:
    """Whether refusing proposal ``number`` (from 0) ends recovery with a final, text-only generation."""
    return number == _MAX_PROPOSALS - 1 or any(denial.is_escalation for denial in denials)


def _withheld_unevaluated(calls: list[ToolCall]) -> list[ToolDenial]:
    """Refusals for calls the final generation proposed after it was asked to stop."""
    return [
        ToolDenial(**call.model_dump(), reason="Proposed after the assistant was asked to stop.", is_escalation=False)
        for call in calls
    ]


def _operation_key(call: ToolCall) -> str:
    """Compare operations independently of provider IDs, preserving JSON scalar types."""
    return json.dumps([call.tool_name, call.tool_input], ensure_ascii=False, sort_keys=True, allow_nan=False)


def _request_with_body(data: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """Give Watcher a private incremental history without changing the provider request."""
    return {**data, "proxy_server_request": {**data["proxy_server_request"], "body": body}}


def route(data: dict[str, Any]) -> API | None:
    """The client-facing API of a proxy request, or None for routes this example does not cover."""
    path = urlsplit(data.get("proxy_server_request", {}).get("url", "")).path.rstrip("/")
    return next((api for suffix, api in _ROUTES.items() if path.endswith(suffix)), None)


def client_body(api: API, body: dict[str, Any]) -> dict[str, Any]:
    """The client's request body, without the fields the proxy adds to its snapshot.

    LiteLLM adds ``litellm_call_id`` and ``litellm_metadata`` to every request.
    On Chat Completions it also uses ``metadata`` as its own slot, holding key
    and routing objects; Messages and Responses keep the client's ``metadata``,
    which carries harness identity such as Claude Code's session.
    """
    added = {"litellm_call_id", "litellm_metadata"} | ({"metadata"} if api == "chat_completions" else set())
    return {key: value for key, value in body.items() if key not in added}


def resolve_scoped_gateway_conversation(api: API, data: dict[str, Any], user: UserAPIKeyAuth) -> GatewayConversation:
    """Select conversation and parent with identical custom and account scoping.

    Native Copilot's task map already supplies account-scoped identities.
    Captures carry parent evidence without another HTTP request or waiting
    for relationship recording.
    """
    native = current_request.get()
    if native is not None:
        return GatewayConversation(
            conversation=ConversationIdentity(namespace="other", id=native.conversation.external_id),
            parent_conversation=ConversationIdentity(namespace="other", id=native.conversation.parent_external_id)
            if native.conversation.parent_external_id is not None
            else None,
        )
    original = data["proxy_server_request"]
    headers = original.get("headers") or {}
    selected = resolve_gateway_conversation(
        client_body(api, original["body"]),
        {name: value for name, value in headers.items() if name.lower() in IDENTITY_HEADER_NAMES},
        next((value for name, value in headers.items() if name.lower() == "user-agent"), None),
    )

    def scoped(identity: ConversationIdentity) -> ConversationIdentity:
        if identity.namespace == "other":
            suffix = validate_conversation_id(identity.id.removeprefix("litellm:"), max_length=1024)
            identity = ConversationIdentity(namespace="other", id="litellm:" + suffix)
        if os.environ.get("WATCHER_AUTH_MODE") == "proxy":
            session_id = identity.id if identity.namespace == "other" else f"{identity.namespace}:{identity.id}"
            identity = ConversationIdentity(namespace="other", id=account_session(user, session_id))
        return identity

    selected.conversation = scoped(selected.conversation)
    if selected.parent_conversation is not None:
        selected.parent_conversation = scoped(selected.parent_conversation)
        if selected.parent_conversation == selected.conversation:
            raise ValueError("conversation_cannot_parent_itself")
    return selected


def _unsupported_request(api: API, body: dict[str, Any]) -> str | None:
    """Request options whose effect the example cannot see or reproduce, if any."""
    if body.get("n", 1) != 1:
        return "Watcher evaluates a single response choice; remove n"
    if api == "chat_completions" and (body.get("audio") or "audio" in (body.get("modalities") or [])):
        return "Audio output is not supported through this Watcher guardrail"
    if api == "responses" and any(body.get(key) for key in ("previous_response_id", "conversation", "background")):
        return "Watcher needs the full conversation in each request; server-stored Responses history is not supported"
    return None


# Watcher statuses a repeated request can succeed on. Client SDKs retry the
# proxy's 5xx responses by regenerating the whole model response, so only these
# become 503; any other Watcher 4xx (bad key, missing permission, request too
# large, unconvertible exchange) cannot change on retry and becomes 422.
_TRANSIENT_WATCHER_STATUSES = frozenset({408, 409, 425, 429})


def _client_status(watcher_status: int) -> int:
    """The proxy's status for a Watcher error: 503 when a retry could succeed, else 422."""
    return 503 if watcher_status >= 500 or watcher_status in _TRANSIENT_WATCHER_STATUSES else 422


def client_calls(api: API, response: dict[str, Any]) -> list[tuple[list[str | int], str]]:
    """Every client-executable call in a response, as (path, call ID), in response order.

    This is the delivery-side inventory, independent of which calls Watcher
    selected: a call Watcher returned no decision for must still be withheld.
    Provider-run tools are excluded because they already executed upstream.
    """
    calls: list[tuple[list[str | int], str]] = []
    if api == "chat_completions":
        for c, choice in enumerate(response.get("choices") or []):
            message = choice.get("message") or {}
            for i, call in enumerate(message.get("tool_calls") or []):
                calls.append((["choices", c, "message", "tool_calls", i], str(call.get("id"))))
            if message.get("function_call"):
                calls.append((["choices", c, "message", "function_call"], "function_call"))
    elif api == "messages":
        for i, block in enumerate(response.get("content") or []):
            if block.get("type") == "tool_use":
                calls.append((["content", i], str(block.get("id"))))
    else:
        for i, item in enumerate(response.get("output") or []):
            if is_client_item({**item, "type": str(item.get("type", ""))}):
                calls.append((["output", i], str(item.get("call_id") or item.get("id"))))
    return calls


def watcher_view(api: API, body: dict[str, Any]) -> dict[str, Any]:
    """The copy of a request or response body Watcher evaluates and records.

    Provider-run Responses searches are left out so this copy also works with
    Watcher servers that do not accept them. A namespace that
    only repeats a tool name's prefix is left out so Watcher records the tool
    under the name Copilot uses. Other APIs are unchanged.
    """
    if api != "responses":
        return body
    view = dict(body)
    for key in ("input", "output"):
        items = body.get(key)
        if not isinstance(items, list):
            continue
        kept: list[Any] = []
        for item in items:
            if isinstance(item, dict) and is_provider_tool_search(item):
                continue
            if isinstance(item, dict) and current_request.get() is not None and redundant_namespace(item):
                item = {field: value for field, value in item.items() if field != "namespace"}
            kept.append(item)
        view[key] = kept
    return view


def _path_order(path: list[str | int]) -> list[tuple[int, int | str]]:
    """Order paths so list indices compare numerically."""
    return [(0, key) if isinstance(key, int) else (1, key) for key in path]


def without_client_calls(api: API, response: dict[str, Any]) -> dict[str, Any]:
    """A detached copy of ``response`` with every client-executable call removed and its stop reason ended.

    Text, reasoning and provider-run tools are kept. Calls are deleted by their
    location, highest index first so the remaining locations stay valid.
    """
    calls = client_calls(api, response)
    modified = as_dict(response)
    for path, _ in sorted(calls, key=lambda call: _path_order(call[0]), reverse=True):
        container: Any = modified
        for key in path[:-1]:
            container = container[key]
        del container[path[-1]]
    if api == "chat_completions":
        for index in {int(path[1]) for path, _ in calls}:
            choice = modified["choices"][index]
            if choice["message"].get("tool_calls") == []:
                del choice["message"]["tool_calls"]
            choice["finish_reason"] = "stop"
    elif api == "messages" and calls:
        modified["stop_reason"] = "end_turn"
    return modified


def _append_text(api: API, response: dict[str, Any], text: str, choice: int = 0) -> None:
    """Add ``text`` as the last assistant text of ``response``, in place; Chat joins it to ``choice``'s content."""
    if api == "chat_completions":
        message = response["choices"][choice]["message"]
        message["content"] = "\n\n".join(part for part in (message.get("content"), text) if part)
    elif api == "messages":
        response["content"].append({"type": "text", "text": text})
    else:
        response["output"].append(
            {
                "type": "message",
                "id": f"msg_{uuid4().hex}",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        )


def _mark_ended(api: API, response: dict[str, Any]) -> None:
    """Give a reply that now ends with a complete question an ordinary end, in place.

    A token-limit or content-filter stop would tell clients the reply was cut
    off, and some continue it automatically instead of showing the question.
    """
    if api == "chat_completions":
        response["choices"][0]["finish_reason"] = "stop"
    elif api == "messages":
        response.update(stop_reason="end_turn", stop_sequence=None)
        response.pop("stop_details", None)
    else:
        response.update(status="completed", incomplete_details=None)


def _asks_user(api: API, response: dict[str, Any]) -> bool:
    """Whether a final reply can stand alone as the question to the user.

    It must propose no client call, contain text of its own and have ended
    normally rather than at a token limit, a content filter or a paused
    provider-run tool.
    """
    if client_calls(api, response):
        return False
    if api == "chat_completions":
        choice = response["choices"][0]
        texts = [choice["message"].get("content")]
        ended = choice.get("finish_reason") in {"stop", "tool_calls", "function_call"}
    elif api == "messages":
        texts = [block.get("text") for block in response["content"] if block["type"] == "text"]
        ended = response.get("stop_reason") in {"end_turn", "stop_sequence", "tool_use"}
    else:
        texts = [
            part.get("text")
            for item in response["output"]
            if item["type"] == "message"
            for part in item.get("content") or []
            if part.get("type") == "output_text"
        ]
        ended = response.get("status") == "completed"
    return ended and any(isinstance(text, str) and text.strip() for text in texts)


async def _replay(chunks: list[Any]) -> AsyncGenerator[Any]:
    """Serve a buffered provider stream to the stream parser again."""
    for chunk in chunks:
        yield chunk


def withheld_response(
    api: API, response: dict[str, Any], outputs: list[PreToolUseHookResponse | HookCallError]
) -> dict[str, Any] | None:
    """The response with every client tool call removed and an explanation added, or None to release it.

    A response is released only when every client-executable call in it has an
    ``allow`` or ``deferred`` decision for its call ID. Otherwise all of its
    calls are withheld together: calls in one response often depend on each
    other, so running only some of them can be worse than running none. A call
    Watcher returned no decision for (for example one the converter treated as
    superseded context) counts as refused. ``outputs`` are the hook's raw-format
    outputs; for these three APIs each ``tool_use_id`` is the provider's call ID.
    """
    calls = client_calls(api, response)
    call_ids = [call_id for _, call_id in calls]
    output_ids = [output.tool_use_id for output in outputs]
    # IDs only identify calls when the match is one-to-one. A response can reuse
    # an ID, for example for an Anthropic call superseded by a model fallback,
    # which Watcher does not evaluate, so any ambiguity withholds everything.
    ambiguous = (
        len(set(call_ids)) != len(call_ids)
        or len(set(output_ids)) != len(output_ids)
        or not set(output_ids) <= set(call_ids)
    )
    released = {
        output.tool_use_id
        for output in outputs
        if not ambiguous and not isinstance(output, HookCallError) and output.decision in _RELEASED
    }
    refused = [output for output in outputs if output.tool_use_id not in released]
    undecided = [(path, call_id) for path, call_id in calls if call_id not in released]
    if not refused and not undecided:
        return None
    reasons = ["- Watcher's decisions could not be matched to the proposed calls."] if ambiguous else []
    for output in refused:
        if isinstance(output, HookCallError):
            reasons.append(f"- {output.tool_use_id}: Watcher could not evaluate this call.")
        else:
            explanation = output.verdict.explanation if isinstance(output.verdict.explanation, str) else None
            reasons.append(f"- {output.tool_use_id}: {explanation or 'Approval is required.'}")
    decided = {output.tool_use_id for output in outputs}
    reasons += [
        f"- {call_id}: Watcher returned no decision for this call."
        for _, call_id in undecided
        if call_id not in decided
    ]
    names = ", ".join(call_id for _, call_id in calls) or ", ".join(str(output.tool_use_id) for output in refused)
    notice = _NOTICE.format(plural="s" if len(calls) > 1 else "", names=names, reasons="\n".join(reasons))
    modified = without_client_calls(api, response)
    if api == "chat_completions":
        paths = [path for path, _ in calls]
        candidate = next((path[1] for path in paths if len(path) > 1 and path[0] == "choices"), 0)
        _append_text(api, modified, notice, int(candidate))
        modified["choices"][candidate]["finish_reason"] = "stop"
    else:
        _append_text(api, modified, notice)
    return modified


class WatcherCallback(CustomLogger):
    """Gate client tool calls in proxy responses on Watcher decisions.

    ``client_factory`` returns a fresh ``AsyncWatcherClient`` per exchange; the
    callback enters and closes it. By default the client is built from
    ``WATCHER_API_URL`` and ``WATCHER_API_KEY`` (or proxy authentication settings)
    when the first exchange is evaluated, so importing the module reads no credentials. ``timeout_seconds``
    bounds the complete Watcher exchange, including connection setup and reading
    its reply. A refused call's remaining budget also bounds its recovery chain;
    initial provider generation is excluded. ``ping_seconds`` controls idle SSE
    comments for streams; both durations must be positive.
    """

    def __init__(
        self,
        client_factory: Callable[[], AsyncWatcherClient] | None = None,
        *,
        timeout_seconds: float = 300,
        max_stream_chunks: int = 100_000,
        ping_seconds: float = 10,
    ) -> None:
        super().__init__()
        if timeout_seconds <= 0 or ping_seconds <= 0 or max_stream_chunks <= 0:
            raise ValueError("Timeout, ping interval and stream chunk limit must be positive")
        self.client_factory = client_factory
        self.timeout_seconds = timeout_seconds
        self.max_stream_chunks = max_stream_chunks
        self.ping_seconds = ping_seconds
        self._recordings: set[asyncio.Task[None]] = set()

    @asynccontextmanager
    async def _client(self, user: UserAPIKeyAuth) -> AsyncGenerator[AsyncWatcherClient]:
        client = (
            self.client_factory()
            if self.client_factory is not None
            else proxy_client(user)
            if os.environ.get("WATCHER_AUTH_MODE") == "proxy"
            else AsyncWatcherClient(os.environ["WATCHER_API_URL"], api_key=os.environ.get("WATCHER_API_KEY"))
        )
        async with client:
            yield client

    async def async_pre_call_hook(
        self, user_api_key_dict: UserAPIKeyAuth, cache: Any, data: dict[str, Any], call_type: str
    ) -> dict[str, Any]:
        """Refuse request options Watcher cannot evaluate, then add the fixed system notice.

        The notice goes into both the provider arguments and the proxy's
        request snapshot, which the callback sends to Watcher and extends for
        replacement generations, so all three see the same conversation.
        """
        api = route(data)
        if api is None:
            return data
        if os.environ.get("WATCHER_AUTH_MODE") == "proxy":
            account_identity(user_api_key_dict)
            require_proxy_configuration()
        if problem := _unsupported_request(api, data["proxy_server_request"]["body"]):
            raise HTTPException(400, problem)
        try:
            resolve_scoped_gateway_conversation(api, data, user_api_key_dict)
        except ValueError as exc:
            raise HTTPException(
                400,
                "Watcher requires a valid x-watcher-session-id or native Claude/Codex/OpenCode conversation identity: "
                + str(exc),
            ) from None
        fields = system_notice_fields(api, data)
        data.update(fields)
        snapshot = data["proxy_server_request"]
        snapshot["body"] = {**snapshot["body"], **fields}
        return data

    async def _decide(
        self,
        api: API,
        data: dict[str, Any],
        response: dict[str, Any],
        user: UserAPIKeyAuth,
        withheld_ids: list[str] | None = None,
    ) -> list[ToolDenial]:
        """Bound the entire Watcher exchange, including setup and reading, by one deadline."""
        try:
            async with asyncio.timeout(self.timeout_seconds):
                return await self._request_decision(api, data, response, user, withheld_ids)
        except TimeoutError:
            raise HTTPException(504, "Watcher evaluation timed out; the pending tool call was withheld") from None

    async def _request_decision(
        self,
        api: API,
        data: dict[str, Any],
        response: dict[str, Any],
        user: UserAPIKeyAuth,
        withheld_ids: list[str] | None,
    ) -> list[ToolDenial]:
        """Return matched policy refusals; missing, ambiguous or failed decisions are errors.

        ``withheld_ids`` names the calls withheld in favor of ``response`` and is
        sent only when there are some. Failed requests are not retried.
        """
        try:
            async with self._client(user) as client:
                outputs = await self._send_exchange(client, api, data, response, user, withheld_ids=withheld_ids)
        except WatcherAPIError as error:
            logger.warning("Watcher rejected a %s exchange with HTTP %s", api, error.status_code)
            raise HTTPException(_client_status(error.status_code), "Watcher could not evaluate this response") from None
        except WatcherError:
            logger.warning("Watcher was unavailable for a %s exchange", api)
            raise HTTPException(503, "Watcher could not evaluate this response") from None
        except HTTPException:
            raise
        except Exception as error:
            # An unparseable Watcher reply (for example from a proxy in front of
            # it) must still withhold the response rather than surface as a 500.
            logger.warning("Unexpected Watcher reply for a %s exchange: %s", api, type(error).__name__)
            raise HTTPException(503, "Watcher could not evaluate this response") from None
        replacement = withheld_response(api, response, outputs)
        logger.info(
            "Watcher evaluated a %s exchange: %d tool calls, withheld=%s",
            api,
            len(outputs),
            replacement is not None,
        )
        if replacement is None:
            return []
        calls = client_tool_details(api, response)
        call_ids = {call.tool_use_id for call in calls}
        if (
            len(outputs) != len(call_ids)
            or {output.tool_use_id for output in outputs} != call_ids
            or any(isinstance(output, HookCallError) for output in outputs)
        ):
            raise HTTPException(503, "Watcher could not evaluate every proposed tool call")
        by_id = {call.tool_use_id: call for call in calls}
        denials: list[ToolDenial] = []
        for output in outputs:
            if isinstance(output, HookCallError):
                raise HTTPException(503, "Watcher could not evaluate this tool call")
            if output.decision in _RELEASED:
                continue
            if output.decision not in {"deny", "escalate"}:
                raise HTTPException(503, "Watcher returned an unsupported decision")
            explanation = output.verdict.explanation
            denials.append(
                ToolDenial(
                    **by_id[cast(str, output.tool_use_id)].model_dump(),
                    reason=explanation if isinstance(explanation, str) and explanation else "Approval is required.",
                    is_escalation=output.decision == "escalate",
                    user_can_approve=output.decision == "escalate" and str(output.decision_source) in _GRADED,
                )
            )
        return denials

    async def _send_exchange(
        self,
        client: AsyncWatcherClient,
        api: API,
        data: dict[str, Any],
        response: dict[str, Any],
        user: UserAPIKeyAuth,
        *,
        withheld_ids: list[str] | None,
    ) -> list[PreToolUseHookResponse | HookCallError]:
        original = data["proxy_server_request"]
        headers = {key.lower(): value for key, value in (original.get("headers") or {}).items()}
        selected = resolve_scoped_gateway_conversation(api, data, user)
        is_proxy = os.environ.get("WATCHER_AUTH_MODE") == "proxy"
        native = current_request.get()
        outputs = await client.pre_tool_use_hook(
            request_body=watcher_view(api, client_body(api, original["body"])),
            response_body=watcher_view(api, response),
            url=urlsplit(original["url"]).path,
            provider=f"litellm/{data.get('model', 'unknown')}",
            user_agent=headers.get("user-agent"),
            conversation=selected.conversation,
            parent_conversation=selected.parent_conversation,
            spawning_tool_use_id=await native.conversation.spawning_tool_use_id() if native is not None else None,
            source=CaptureSource(type="gateway", name="litellm"),
            # The null key selects Copilot's tool rules without adding a matching alias.
            external_ids={"github_copilot_cli": None} if native is not None else None,
            user=None if is_proxy else user.user_email or None,
            timeout=self.timeout_seconds,
            withheld_tool_use_ids=withheld_ids,
            withholds_refused_calls=True,
        )
        if native is not None:
            await native.conversation.record_spawning_calls(client_tool_details(api, response))
        return outputs

    async def async_post_call_success_hook(
        self, data: dict[str, Any], user_api_key_dict: UserAPIKeyAuth, response: Any
    ) -> Any:
        """Release an allowed response, or resample refused proposals up to twice.

        No buffered call has reached the client, so a refused proposal's siblings
        receive cancellation results. The returned single response contains only
        an approved alternative's executable calls and ordinary denial notices,
        or, after an escalation or a third refusal, the model's text asking the
        user how to proceed.
        """
        api = route(data)
        if api is None:
            return response
        try:
            return await self._recover_nonstream(api, data, user_api_key_dict, response)
        except HTTPException:
            raise
        except (ValueError, UnsupportedStream):
            raise HTTPException(422, "Model response is not supported for gateway recovery") from None
        except Exception:
            raise HTTPException(502, "Model response could not be completed during gateway recovery") from None

    async def _recover_nonstream(self, api: API, data: dict[str, Any], user: UserAPIKeyAuth, response: Any) -> Any:
        """Evaluate complete proposals and compose only an approved alternative's calls.

        The public hook maps malformed exchanges and provider failures to safe
        HTTP errors; cancellation remains owned by the requesting proxy task.
        """
        original = response_dict(response) if api == "responses" else as_dict(response)
        started = asyncio.get_running_loop().time()
        denials = await self._decide(api, data, original, user)
        if not denials:
            return original if api == "responses" and isinstance(response, BaseModel) else response
        request = client_body(api, data["proxy_server_request"]["body"])
        candidate = original
        recovery = _Recovery(deadline=started + self.timeout_seconds)
        notices: list[str] = []
        replacement: dict[str, Any] | None = None
        for attempt in range(_MAX_PROPOSALS):
            calls = client_tool_details(api, candidate)
            refused = {denial.tool_use_id for denial in denials}
            cancelled = [call for call in calls if call.tool_use_id not in refused]
            notices.append(denial_notice(denials, cancelled=cancelled))
            self._remember_denials(recovery, denials)
            recovery.withheld.extend(call.tool_use_id for call in calls)
            stop = _stops(denials, attempt)
            request = build_replan_request(api, request, candidate, denials, released_ids=set(), stop=stop)
            if stop:
                replacement = await self._final_reply(api, request, data, denials, recovery.deadline)
                if replacement is None:
                    notices.append(stop_notice(denials))
                break
            candidate = await self._until(complete_replan(api, request, data), recovery.deadline)
            denials = await self._until(
                self._assess_replacement(api, _request_with_body(data, request), candidate, user, recovery),
                recovery.deadline,
            )
            if not denials:
                replacement = candidate
                break
        delivered = compose_nonstream(api, original, replacement, "\n\n".join(notices))
        self._start_recording(api, data, delivered, user, recovery.withheld_ids())
        if isinstance(response, BaseModel) and api != "responses":
            return type(response).model_validate(delivered)
        return delivered

    async def _final_reply(
        self, api: API, request: dict[str, Any], data: dict[str, Any], denials: list[ToolDenial], deadline: float | None
    ) -> dict[str, Any] | None:
        """Generate the reply asking the user how to proceed, or return None when it failed.

        The model was asked to put the question itself. Calls it proposes anyway
        are withheld without evaluation, and ``stop_notice`` is appended when it
        proposed any, wrote no text or stopped early. A provider failure,
        timeout, malformed reply or failed Responses result returns None, so
        the caller ends with ``stop_notice`` alone: an error status would invite
        client retries that regenerate and resubmit the refused proposals.
        """
        try:
            reply = await self._until(complete_replan(api, request, data), deadline)
            if api == "responses" and (reply.get("status") == "failed" or reply.get("error")):
                logger.warning("The final responses generation failed: the provider reported an error")
                return None
            if _asks_user(api, reply):
                return reply
            ended = without_client_calls(api, reply)
            _append_text(api, ended, stop_notice(denials))
            _mark_ended(api, ended)
            return ended
        except Exception as error:
            logger.warning("The final %s generation failed: %s", api, type(error).__name__)
            return None

    async def async_post_call_streaming_iterator_hook(
        self, user_api_key_dict: UserAPIKeyAuth, response: Any, request_data: dict[str, Any]
    ) -> AsyncGenerator[Any, None]:
        """Forward content until a tool, then release each evaluated call in provider order.

        The upstream reader and each evaluation are owned tasks: keepalives do
        not cancel either operation. Closing this iterator cancels and joins the
        local task and closes upstream; it cannot undo already persisted backend
        work. Once output starts, failures are protocol errors rather than HTTP
        status changes. Previously approved calls cannot be retracted.
        """
        api = route(request_data)
        if api is None:
            async for chunk in response:
                yield chunk
            return
        has_started = False
        delivery = StreamDelivery(api)
        stream = self._gated_stream(api, request_data, response, user_api_key_dict, delivery)
        try:
            async with aclosing(stream):
                async for event in stream:
                    has_started = True
                    yield event
        except Exception as error:
            if isinstance(error, HTTPException):
                status, detail = error.status_code, error.detail
            elif isinstance(error, (UnsupportedStream, ValueError)):
                status, detail = 422, "Model response stream is not supported"
            else:
                status, detail = 502, "Model response stream was incomplete"
            if not has_started:
                raise HTTPException(status, detail) from None
            code = "watcher_timeout" if status == 504 else "watcher_denied" if status == 403 else "stream_error"
            yield delivery.error(code, detail, status)

    async def _provider_events(self, api: API, response: Any) -> AsyncGenerator[Any]:
        """Decode complete Messages SSE frames and bound raw input for every format."""
        completed = completed_response(response) if api == "responses" else None
        async with aclosing(self._stream_chunks(api, response)) as chunks:
            if api == "messages":
                async for event in SSEDecoder().aiter_bytes(chunks):
                    # GitHub Copilot ends its Messages streams with an OpenAI-style
                    # ``[DONE]`` frame after ``message_stop``. It carries nothing to
                    # deliver. A stream that ends before ``message_stop`` fails.
                    if event.data and event.data != "[DONE]":
                        try:
                            yield json.loads(event.data)
                        except ValueError as exc:
                            raise UnsupportedStream("Malformed Messages SSE data") from exc
            else:
                async for chunk in chunks:
                    if api == "responses" and completed is None:
                        completed = completed_response(response)
                    yield response_event(chunk, completed) if api == "responses" else chunk

    async def _stream_chunks(self, api: API, response: Any) -> AsyncGenerator[Any]:
        """Bound provider input and close external LiteLLM iterators when they support it."""
        count = 0
        try:
            async for chunk in response:
                count += 1
                if count > self.max_stream_chunks:
                    raise HTTPException(413, "Model response is too long to evaluate")
                if api == "messages" and not isinstance(chunk, bytes):
                    raise UnsupportedStream("Unexpected Messages stream chunk")
                yield chunk
        finally:
            close = getattr(response, "aclose", None)
            if close is not None:
                await close()

    async def _wait(self, task: asyncio.Task[Any], api: API) -> AsyncGenerator[bytes]:
        """Send SSE comments without resetting deadlines or exposing premature protocol events.

        Comments are valid before the first event in every API. An Anthropic
        ``ping`` before ``message_start`` breaks the official streaming helper.
        """
        try:
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=self.ping_seconds)
                if not done:
                    yield b": watcher keepalive\n\n"
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _until(self, operation: Awaitable[_T], deadline: float | None) -> _T:
        """Use the remaining recovery budget without restarting it for reads or generations."""
        try:
            async with asyncio.timeout_at(deadline):
                return await operation
        except TimeoutError:
            raise HTTPException(504, "Watcher evaluation timed out; the pending tool call was withheld") from None

    @staticmethod
    def _remember_denials(recovery: _Recovery, denials: list[ToolDenial]) -> None:
        for denial in denials:
            recovery.forbidden[_operation_key(denial)] = denial

    async def _assess_replacement(
        self,
        api: API,
        data: dict[str, Any],
        response: dict[str, Any],
        user: UserAPIKeyAuth,
        recovery: _Recovery,
    ) -> list[ToolDenial]:
        """Apply existing operation decisions before grading genuinely new alternatives.

        Renaming a denied operation's call ID does not give it another chance at
        a stochastic policy decision. Repeating an already released operation
        could execute its side effects twice, even if the second verdict allows.
        Refresh released operations before each recovery evaluation: multiple
        calls can arrive within the same streamed alternative.
        """
        if recovery.deadline is not None:
            for call in recovery.released:
                recovery.forbidden[_operation_key(call)] = ToolDenial(
                    **call.model_dump(),
                    reason=(
                        "This operation was already approved and sent to the client. Its result is not yet available; "
                        "it must not be executed again during this recovery."
                    ),
                    is_escalation=False,
                )
        repeated = [
            ToolDenial(
                **call.model_dump(),
                reason=recovery.forbidden[_operation_key(call)].reason,
                is_escalation=recovery.forbidden[_operation_key(call)].is_escalation,
                user_can_approve=recovery.forbidden[_operation_key(call)].user_can_approve,
            )
            for call in client_tool_details(api, response)
            if _operation_key(call) in recovery.forbidden
        ]
        return repeated if repeated else await self._decide(api, data, response, user)

    async def _record_stream_tail(
        self,
        api: API,
        data: dict[str, Any],
        response: dict[str, Any],
        user: UserAPIKeyAuth,
        withheld_ids: list[str] | None,
    ) -> None:
        """Record text after all executable content was evaluated, without delaying delivery."""
        try:
            await self._decide(api, data, response, user, withheld_ids)
        except HTTPException:
            logger.warning("Watcher could not record a %s stream tail", api)

    def _start_recording(
        self,
        api: API,
        data: dict[str, Any],
        delivered: dict[str, Any],
        user: UserAPIKeyAuth,
        withheld_ids: list[str] | None,
    ) -> None:
        """Record the actual client-visible history without selecting approved calls again.

        ``withheld_ids`` names the calls withheld in favor of ``delivered``, so
        Watcher can show them before it.
        """
        request = client_body(api, data["proxy_server_request"]["body"])
        if api == "messages" and client_calls(api, delivered):
            # An Anthropic client sends this reply back next turn as one assistant
            # message, released calls and later text together. Watcher must store
            # it as that one message, or the next turn would branch away from it
            # and lose its withheld calls, so the whole reply goes into history
            # with an empty response after it.
            reply = as_dict(delivered)
            history = as_dict(request)
            history["messages"] = [*(history.get("messages") or []), {"role": "assistant", "content": reply["content"]}]
            tail = Evaluation(request=history, response={**reply, "content": []})
        else:
            state = IncrementalStream(api)
            state.body = delivered
            for path, _ in client_calls(api, delivered):
                if api == "chat_completions":
                    index = 0 if path[-1] == "function_call" else int(path[4])
                else:
                    index = int(path[1])
                state.allowed.add(index)
            if api == "chat_completions":
                state.chat_legacy = delivered["choices"][0]["message"].get("function_call")
            tail = state.evaluation(request, None)
        recording = asyncio.create_task(
            self._record_stream_tail(api, _request_with_body(data, tail.request), tail.response, user, withheld_ids)
        )
        self._recordings.add(recording)
        recording.add_done_callback(self._recordings.discard)

    async def _stream_attempt(
        self,
        api: API,
        original_data: dict[str, Any],
        attempt_data: dict[str, Any],
        response: Any,
        user: UserAPIKeyAuth,
        delivery: StreamDelivery,
        attempt: _Attempt,
        recovery: _Recovery,
    ) -> AsyncGenerator[bytes]:
        """Gate one provider generation, draining a refused attempt without leaking its tools.

        On refusal, close previously emitted interleaved items and approved calls
        using their remaining validated frames. Later content is withheld. The
        complete proposal remains available for a truthful provider continuation.
        """
        state = attempt.stream
        held: deque[PendingEvent] = deque()
        finished = False
        async with aclosing(self._provider_events(api, response)) as events:
            while True:
                read = asyncio.create_task(self._until(anext(events), recovery.deadline))
                async with aclosing(self._wait(read, api)) as waiting:
                    async for ping in waiting:
                        yield ping
                try:
                    value = read.result()
                except StopAsyncIteration:
                    break
                held.extend(state.add(value))
                if attempt.denials:
                    while held:
                        frame = held.popleft()
                        if delivery.retains(frame):
                            for event in delivery.emit(frame, state):
                                yield event
                    continue
                while True:
                    while held and held[0].requires <= state.allowed:
                        for event in delivery.emit(held.popleft(), state):
                            yield event
                    index = state.ready()
                    if index is None:
                        break
                    evaluation = state.evaluation(client_body(api, attempt_data["proxy_server_request"]["body"]), index)
                    if attempt.final:
                        attempt.denials = _withheld_unevaluated(client_tool_details(api, evaluation.response))
                        while held:
                            frame = held.popleft()
                            if delivery.retains(frame):
                                for event in delivery.emit(frame, state):
                                    yield event
                        break
                    request = _request_with_body(attempt_data, evaluation.request)
                    deadline = recovery.deadline or (asyncio.get_running_loop().time() + self.timeout_seconds)
                    decision = asyncio.create_task(
                        self._until(
                            self._assess_replacement(api, request, evaluation.response, user, recovery), deadline
                        )
                    )
                    async with aclosing(self._wait(decision, api)) as waiting:
                        async for ping in waiting:
                            yield ping
                    attempt.denials = decision.result()
                    if attempt.denials:
                        recovery.deadline = deadline
                        while held:
                            frame = held.popleft()
                            if delivery.retains(frame):
                                for event in delivery.emit(frame, state):
                                    yield event
                        break
                    calls = client_tool_details(api, evaluation.response)
                    attempt.released.extend(calls)
                    recovery.released.extend(calls)
                    state.allowed.add(index)
                if state.terminal and not attempt.denials and not attempt.final and not finished:
                    delivery.checkpoint(state)
                    final = delivery.finish(state)
                    if api != "chat_completions":
                        self._start_recording(api, original_data, delivery.response, user, recovery.withheld_ids())
                    for event in final:
                        yield event
                    finished = True
            if attempt.denials:
                if not state.terminal or set(state.calls) != state.complete:
                    raise IncompleteStream("Refused provider proposal was truncated")
            else:
                state.finish()
            delivery.checkpoint(state)
            if finished and api == "chat_completions":
                self._start_recording(api, original_data, delivery.response, user, recovery.withheld_ids())

    async def _gated_stream(
        self, api: API, data: dict[str, Any], response: Any, user: UserAPIKeyAuth, delivery: StreamDelivery
    ) -> AsyncGenerator[bytes]:
        """Stream an original proposal, at most two evaluated replacements and a final reply as one response.

        After an escalation or the third refused proposal, one more generation
        is asked to stop and put the question to the user. It is read in full
        before any of it is delivered (``_final_chunks``), then delivered like
        any other text. ``stop_notice`` ends the response instead of an error
        when that generation fails or times out, and follows the reply's text
        when the reply proposed calls (withheld), had no text or stopped early.
        """
        recovery = _Recovery()
        request = client_body(api, data["proxy_server_request"]["body"])
        refused: list[ToolDenial] = []
        final = False
        for number in range(_MAX_PROPOSALS + 1):
            delivery.begin_attempt()
            attempt = _Attempt(stream=IncrementalStream(api), final=final)
            iterator = self._stream_attempt(
                api, data, _request_with_body(data, request), response, user, delivery, attempt, recovery
            )
            async with aclosing(iterator):
                async for event in iterator:
                    yield event
            if attempt.final:
                asks = not attempt.denials and _asks_user(api, attempt.stream.body)
                for event in self._end_delivery(
                    api, data, user, delivery, attempt.stream, None if asks else refused, recovery
                ):
                    yield event
                return
            if not attempt.denials:
                return
            released_ids = {call.tool_use_id for call in attempt.released}
            refused_ids = {denial.tool_use_id for denial in attempt.denials}
            withheld = [
                call for call in client_tool_details(api, attempt.stream.body) if call.tool_use_id not in released_ids
            ]
            cancelled = [call for call in withheld if call.tool_use_id not in refused_ids]
            recovery.withheld.extend(call.tool_use_id for call in withheld)
            self._remember_denials(recovery, attempt.denials)
            for event in delivery.notice(denial_notice(attempt.denials, cancelled=cancelled)):
                yield event
            refused = attempt.denials
            final = _stops(attempt.denials, number)
            request = build_replan_request(
                api, request, attempt.stream.body, attempt.denials, released_ids=released_ids, stop=final
            )
            operation = (
                self._final_chunks(api, request, data) if final else complete_replan(api, request, data, stream=True)
            )
            generation = asyncio.create_task(self._until(operation, recovery.deadline))
            async with aclosing(self._wait(generation, api)) as waiting:
                async for ping in waiting:
                    yield ping
            try:
                response = generation.result()
            except Exception as error:
                if not final:
                    raise
                logger.warning("The final %s generation failed: %s", api, type(error).__name__)
                for event in self._end_delivery(api, data, user, delivery, attempt.stream, refused, recovery):
                    yield event
                return
            if final:
                response = _replay(response)

    async def _final_chunks(self, api: API, request: dict[str, Any], data: dict[str, Any]) -> list[Any]:
        """Generate the final reply and read and validate all of it before any is delivered.

        The reply is short text. Holding it until the provider finishes means a
        failure, timeout or malformed stream can still be replaced by the fixed
        question, rather than cutting off a half-delivered reply with an error.
        """
        response = await complete_replan(api, request, data, stream=True)
        source = self._provider_events(api, response) if api == "responses" else self._stream_chunks(api, response)
        async with aclosing(source):
            chunks = [chunk async for chunk in source]
        state = IncrementalStream(api)
        async with aclosing(self._provider_events(api, _replay(chunks))) as events:
            async for value in events:
                state.add(value)
        if not state.terminal or set(state.calls) != state.complete:
            raise IncompleteStream("The final reply ended before completing")
        # Replay withholds proposed calls by reading their details, which
        # rejects malformed arguments; reject them here, while the fallback
        # can still discard the reply.
        client_tool_details(api, state.body)
        return chunks

    def _end_delivery(
        self,
        api: API,
        data: dict[str, Any],
        user: UserAPIKeyAuth,
        delivery: StreamDelivery,
        state: IncrementalStream,
        refused: list[ToolDenial] | None,
        recovery: _Recovery,
    ) -> list[bytes]:
        """Finish a stream after its final reply, first adding ``stop_notice`` for ``refused`` when given.

        ``state`` is the last attempt read in full: the final reply, or the
        refused attempt before it when the final generation failed. The
        recording names ``recovery``'s withheld calls.
        """
        events: list[bytes] = []
        if refused is not None:
            events += delivery.notice(stop_notice(refused))
            _mark_ended(api, state.body)
        events += delivery.finish(state)
        self._start_recording(api, data, delivery.response, user, recovery.withheld_ids())
        return events


watcher_callback = WatcherCallback()
