"""A LiteLLM proxy guardrail that withholds tool calls until Watcher allows them.

Load ``watcher_callback`` through LiteLLM's ``callbacks`` setting. For every
Chat Completions, Responses or Anthropic Messages call, Watcher's raw-format
pre-tool-use hook converts provider-shaped exchanges, applies the organization's
policy and records its decisions. Streaming calls are evaluated individually at
their first reliable completion boundary; ``incremental`` builds those exchanges
and preserves prior approved content as history without grading it again.

Streams forward non-tool content immediately and hold each tool plus subsequent
events until it has an allow (or observe-mode deferred) decision. All output is
re-encoded from validated events. Denials and escalations become ordinary text
notices plus gateway-generated alternatives, with at most three proposals per
client request. Alternatives stream through the same gates. Already released
calls retain their approval; internal recovery receipts state that their real
execution results are unknown. Repeated denied or released calls cannot escape
the prior decision merely by changing their IDs. Non-streamed proposals remain
atomic until an entire allowed alternative can be returned.

Each evaluation has a 300-second default deadline. After a refusal, its remaining
budget also bounds draining that proposal, replacement generation and evaluation.
SSE comments keep every API alive without inventing model content; final text-only
recording never holds delivery. Transport failures remain explicit stream errors.

Configure ``WATCHER_API_URL`` and ``WATCHER_API_KEY`` on the proxy process.
Clients can send ``x-watcher-session-id`` to group their requests into one
Watcher session, recorded under ``SESSION_PREFIX``; requests that carry a native
session ID, as Claude Code's and Codex's normally do, group by it. Requests without
either are refused before generation because partial replies cannot reliably
identify a conversation by shared history.
"""

import asyncio
import json
import logging
import os
import re
from collections import deque
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import aclosing, asynccontextmanager
from typing import Any, TypeVar, cast
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import HTTPException
from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy._types import UserAPIKeyAuth
from openai._streaming import SSEDecoder
from pydantic import BaseModel, ConfigDict, Field

from watcher_litellm.delivery import StreamDelivery, compose_nonstream
from watcher_litellm.incremental import PROVIDER_ITEMS, IncrementalStream, PendingEvent
from watcher_litellm.replan import (
    ToolCall,
    ToolDenial,
    build_replan_request,
    client_tool_details,
    complete_replan,
    denial_notice,
)
from watcher_litellm.streams import (
    API,
    IncompleteStream,
    UnsupportedStream,
    as_dict,
)
from watcher_sdk import AsyncWatcherClient, WatcherAPIError, WatcherError
from watcher_sdk._generated.models import HookCallError, PreToolUseHookResponse

logger = logging.getLogger(__name__)

_ROUTES: dict[str, API] = {
    "/chat/completions": "chat_completions",
    "/responses": "responses",
    "/messages": "messages",
}
_RELEASED = {"allow", "deferred"}
# Watcher stores each client's x-watcher-session-id under this prefix. Watcher
# labels sessions whose ID carries a registered gateway prefix as Gateway, and
# the prefix keeps client-chosen IDs apart from IDs other integrations send. A
# header that already starts with the prefix is sent unchanged, so a client can
# send back the stored ID it looked up without it gaining a second prefix.
SESSION_PREFIX = "litellm:"
_NOTICE = "Watcher withheld the proposed tool call{plural} ({names}). No tool was run.\n\n{reasons}"
_MAX_PROPOSALS = 3
_T = TypeVar("_T")


class _Recovery(BaseModel):
    """State shared by one client request and its bounded replacement generations.

    Once a call is refused, its evaluation's deadline also bounds draining that
    proposal, generating alternatives, and evaluating them. The operation map
    prevents a fresh call ID from retrying a denied or already released action.
    """

    deadline: float | None = None
    forbidden: dict[str, ToolDenial] = Field(default_factory=dict)
    released: list[ToolCall] = Field(default_factory=list)


class _Attempt(BaseModel):
    """A provider attempt's parser and decisions, filled by the streaming driver."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    stream: IncrementalStream
    denials: list[ToolDenial] = Field(default_factory=list)
    released: list[ToolCall] = Field(default_factory=list)


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


def session_identity(data: dict[str, Any]) -> str | None:
    """Use a client-supplied conversation identity, never infer it from a partial reply.

    A native Claude/Codex UUID becomes a stable gateway alias as well as retaining
    the backend's native identity. Generic clients supply ``x-watcher-session-id``.
    Content-derived IDs would merge independent conversations sharing an opening.
    """
    original = data["proxy_server_request"]
    headers = {key.lower(): value for key, value in (original.get("headers") or {}).items()}
    explicit = headers.get("x-watcher-session-id")
    if explicit:
        return explicit if explicit.startswith(SESSION_PREFIX) else SESSION_PREFIX + explicit
    body = original["body"]
    client_metadata = body.get("client_metadata")
    candidate = client_metadata.get("thread_id") if isinstance(client_metadata, dict) else None
    harness = "codex"
    if candidate is None:
        metadata = body.get("metadata")
        user_id = metadata.get("user_id") if isinstance(metadata, dict) else None
        if isinstance(user_id, str):
            harness = "claude"
            try:
                identity = json.loads(user_id)
            except ValueError:
                match = re.search(r"_session_([0-9a-fA-F-]{36})$", user_id)
                candidate = match[1] if match is not None else None
            else:
                candidate = identity.get("session_id") if isinstance(identity, dict) else None
    if not isinstance(candidate, str):
        return None
    try:
        native_id = UUID(candidate)
    except ValueError:
        return None
    return f"{SESSION_PREFIX}{harness}:{native_id}"


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


# Responses output items the provider runs itself. Every other ``*_call`` item
# is executed by the client and must have a released Watcher decision.
_PROVIDER_ITEMS = PROVIDER_ITEMS


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
            kind = str(item.get("type", ""))
            if kind.endswith("_call") and kind not in _PROVIDER_ITEMS:
                calls.append((["output", i], str(item.get("call_id") or item.get("id"))))
    return calls


def _path_order(path: list[str | int]) -> list[tuple[int, int | str]]:
    """Order paths so list indices compare numerically."""
    return [(0, key) if isinstance(key, int) else (1, key) for key in path]


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
    Calls are deleted by their location in ``response``, highest index first so
    the remaining locations stay valid.
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
    modified = as_dict(response)
    paths = [path for path, _ in calls]
    for path in sorted(paths, key=_path_order, reverse=True):
        container: Any = modified
        for key in path[:-1]:
            container = container[key]
        del container[path[-1]]
    if api == "chat_completions":
        for choice in modified["choices"]:
            if choice["message"].get("tool_calls") == []:
                del choice["message"]["tool_calls"]
        candidate = next((path[1] for path in paths if len(path) > 1 and path[0] == "choices"), 0)
        choice = modified["choices"][candidate]
        message = choice["message"]
        message["content"] = "\n\n".join(part for part in (message.get("content"), notice) if part)
        choice["finish_reason"] = "stop"
    elif api == "messages":
        modified["content"].append({"type": "text", "text": notice})
        modified["stop_reason"] = "end_turn"
    else:
        modified["output"].append(
            {
                "type": "message",
                "id": f"msg_watcher_{modified.get('id', '')}",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": notice, "annotations": []}],
            }
        )
    return modified


class WatcherCallback(CustomLogger):
    """Gate client tool calls in proxy responses on Watcher decisions.

    ``client_factory`` returns a fresh ``AsyncWatcherClient`` per exchange; the
    callback enters and closes it. By default the client is built from
    ``WATCHER_API_URL`` and ``WATCHER_API_KEY`` when the first exchange is
    evaluated, so importing the module reads no credentials. ``timeout_seconds``
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
    async def _client(self) -> AsyncGenerator[AsyncWatcherClient]:
        client = (
            self.client_factory()
            if self.client_factory is not None
            else AsyncWatcherClient(os.environ["WATCHER_API_URL"], api_key=os.environ.get("WATCHER_API_KEY"))
        )
        async with client:
            yield client

    async def async_pre_call_hook(
        self, user_api_key_dict: UserAPIKeyAuth, cache: Any, data: dict[str, Any], call_type: str
    ) -> dict[str, Any]:
        """Refuse request options Watcher cannot evaluate before the provider runs anything."""
        api = route(data)
        if api is not None and (problem := _unsupported_request(api, data["proxy_server_request"]["body"])):
            raise HTTPException(400, problem)
        if api is not None and session_identity(data) is None:
            raise HTTPException(
                400,
                "Watcher requires x-watcher-session-id or native Claude/Codex session metadata "
                "to keep incremental decisions in one conversation",
            )
        return data

    async def _decide(
        self, api: API, data: dict[str, Any], response: dict[str, Any], user: UserAPIKeyAuth
    ) -> list[ToolDenial]:
        """Bound the entire Watcher exchange, including setup and reading, by one deadline."""
        try:
            async with asyncio.timeout(self.timeout_seconds):
                return await self._request_decision(api, data, response, user)
        except TimeoutError:
            raise HTTPException(504, "Watcher evaluation timed out; the pending tool call was withheld") from None

    async def _request_decision(
        self, api: API, data: dict[str, Any], response: dict[str, Any], user: UserAPIKeyAuth
    ) -> list[ToolDenial]:
        """Return matched policy refusals; missing, ambiguous or failed decisions are errors."""
        original = data["proxy_server_request"]
        headers = {key.lower(): value for key, value in (original.get("headers") or {}).items()}
        session_id = session_identity(data)
        try:
            async with self._client() as client:
                outputs = await client.pre_tool_use_hook(
                    request_body=client_body(api, original["body"]),
                    response_body=response,
                    url=urlsplit(original["url"]).path,
                    provider=f"litellm/{data.get('model', 'unknown')}",
                    user_agent=headers.get("user-agent"),
                    external_ids={"other": session_id} if session_id else None,
                    user=user.user_email or None,
                    timeout=self.timeout_seconds,
                )
        except WatcherAPIError as error:
            logger.warning("Watcher rejected a %s exchange with HTTP %s", api, error.status_code)
            raise HTTPException(_client_status(error.status_code), "Watcher could not evaluate this response") from None
        except WatcherError:
            logger.warning("Watcher was unavailable for a %s exchange", api)
            raise HTTPException(503, "Watcher could not evaluate this response") from None
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
                )
            )
        return denials

    async def async_post_call_success_hook(
        self, data: dict[str, Any], user_api_key_dict: UserAPIKeyAuth, response: Any
    ) -> Any:
        """Release an allowed response, or resample refused proposals up to twice.

        No buffered call has reached the client, so a refused proposal's siblings
        receive cancellation results. The returned single response contains only
        an approved alternative's executable calls and ordinary denial notices.
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
        original = as_dict(response)
        started = asyncio.get_running_loop().time()
        denials = await self._decide(api, data, original, user)
        if not denials:
            return response
        request = client_body(api, data["proxy_server_request"]["body"])
        candidate = original
        recovery = _Recovery(deadline=started + self.timeout_seconds)
        notices: list[str] = []
        replacement: dict[str, Any] | None = None
        for attempt in range(_MAX_PROPOSALS):
            refused = {denial.tool_use_id for denial in denials}
            cancelled = [call for call in client_tool_details(api, candidate) if call.tool_use_id not in refused]
            notices.append(denial_notice(denials, cancelled=cancelled))
            self._remember_denials(recovery, denials)
            if attempt == _MAX_PROPOSALS - 1:
                notices.append("Watcher stopped after three blocked proposals.")
                break
            request = build_replan_request(api, request, candidate, denials, released_ids=set())
            candidate = await self._until(complete_replan(api, request, data), recovery.deadline)
            denials = await self._until(
                self._assess_replacement(api, _request_with_body(data, request), candidate, user, recovery),
                recovery.deadline,
            )
            if not denials:
                replacement = candidate
                break
        delivered = compose_nonstream(api, original, replacement, "\n\n".join(notices))
        self._start_recording(api, data, delivered, user)
        if isinstance(response, BaseModel):
            return type(response).model_validate(delivered)
        return delivered

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
        async with aclosing(self._stream_chunks(api, response)) as chunks:
            if api == "messages":
                async for event in SSEDecoder().aiter_bytes(chunks):
                    if event.data:
                        try:
                            yield json.loads(event.data)
                        except ValueError as exc:
                            raise UnsupportedStream("Malformed Messages SSE data") from exc
            else:
                async for chunk in chunks:
                    yield chunk

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
            )
            for call in client_tool_details(api, response)
            if _operation_key(call) in recovery.forbidden
        ]
        return repeated if repeated else await self._decide(api, data, response, user)

    async def _record_stream_tail(
        self, api: API, data: dict[str, Any], response: dict[str, Any], user: UserAPIKeyAuth
    ) -> None:
        """Record text after all executable content was evaluated, without delaying delivery."""
        try:
            await self._decide(api, data, response, user)
        except HTTPException:
            logger.warning("Watcher could not record a %s stream tail", api)

    def _start_recording(self, api: API, data: dict[str, Any], delivered: dict[str, Any], user: UserAPIKeyAuth) -> None:
        """Record the actual client-visible history without selecting approved calls again."""
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
        tail = state.evaluation(client_body(api, data["proxy_server_request"]["body"]), None)
        recording = asyncio.create_task(
            self._record_stream_tail(api, _request_with_body(data, tail.request), tail.response, user)
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
                if state.terminal and not attempt.denials and not finished:
                    delivery.checkpoint(state)
                    final = delivery.finish(state)
                    if api != "chat_completions":
                        self._start_recording(api, original_data, delivery.response, user)
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
                self._start_recording(api, original_data, delivery.response, user)

    async def _gated_stream(
        self, api: API, data: dict[str, Any], response: Any, user: UserAPIKeyAuth, delivery: StreamDelivery
    ) -> AsyncGenerator[bytes]:
        """Stream an original proposal and at most two evaluated replacements as one response."""
        recovery = _Recovery()
        request = client_body(api, data["proxy_server_request"]["body"])
        for number in range(_MAX_PROPOSALS):
            delivery.begin_attempt()
            attempt = _Attempt(stream=IncrementalStream(api))
            iterator = self._stream_attempt(
                api, data, _request_with_body(data, request), response, user, delivery, attempt, recovery
            )
            async with aclosing(iterator):
                async for event in iterator:
                    yield event
            if not attempt.denials:
                return
            released_ids = {call.tool_use_id for call in attempt.released}
            refused_ids = {denial.tool_use_id for denial in attempt.denials}
            cancelled = [
                call
                for call in client_tool_details(api, attempt.stream.body)
                if call.tool_use_id not in released_ids | refused_ids
            ]
            self._remember_denials(recovery, attempt.denials)
            for event in delivery.notice(denial_notice(attempt.denials, cancelled=cancelled)):
                yield event
            if number == _MAX_PROPOSALS - 1:
                for event in delivery.notice("Watcher stopped after three blocked proposals."):
                    yield event
                final = delivery.finish(attempt.stream)
                self._start_recording(api, data, delivery.response, user)
                for event in final:
                    yield event
                return
            request = build_replan_request(
                api, request, attempt.stream.body, attempt.denials, released_ids=released_ids
            )
            generation = asyncio.create_task(
                self._until(complete_replan(api, request, data, stream=True), recovery.deadline)
            )
            async with aclosing(self._wait(generation, api)) as waiting:
                async for ping in waiting:
                    yield ping
            response = generation.result()


watcher_callback = WatcherCallback()
