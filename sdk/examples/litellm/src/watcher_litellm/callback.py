"""A LiteLLM proxy guardrail that holds each response until Watcher has judged its tool calls.

Load ``watcher_callback`` through LiteLLM's ``callbacks`` setting. For every
Chat Completions, Responses or Anthropic Messages call, the callback sends the
client's raw request body and the complete provider response to Watcher's
pre-tool-use hook in its raw format. Watcher converts the pair, applies the
organization's policy to each new client tool call, records the conversation,
and returns one decision per call with that call's location in the response.

A response is released only when every client tool call in it has an allow
(or observe-mode deferred) decision. Otherwise the callback removes every
client tool call and appends an explanation, so the client receives a normal
text reply. Chat Completions and Responses streams are buffered until the
decision and then re-encoded from the evaluated body. Messages streams are
forwarded as their events arrive, re-encoded from the parsed events, but every
tool call and the end of the message are held until the decision. Nothing is
replayed, so the client can only execute what Watcher saw. A Watcher failure
withholds the response with an HTTP error, or with a stream error event once a
Messages stream has started.

Configure ``WATCHER_API_URL`` and ``WATCHER_API_KEY`` on the proxy process.
Clients can send ``x-watcher-session-id`` to group their requests into one
Watcher session, recorded under ``SESSION_PREFIX``; requests that carry a native
session ID, as Claude Code's and Codex's normally do, group by it. Without
either, Watcher groups requests by their shared conversation history.
"""

import asyncio
import logging
import os
import time
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException
from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy._types import UserAPIKeyAuth
from openai._streaming import SSEDecoder
from pydantic import BaseModel

from watcher_litellm.streams import (
    API,
    MESSAGES_EVENT_TYPES,
    IncompleteStream,
    MessageAssembler,
    UnsupportedStream,
    as_dict,
    assemble,
    encode,
    encode_messages_event,
    encode_messages_from,
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
_PING = encode_messages_event({"type": "ping"})


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
_PROVIDER_ITEMS = {
    "web_search_call",
    "file_search_call",
    "code_interpreter_call",
    "image_generation_call",
    "mcp_call",
    "mcp_list_tools",
    "mcp_approval_request",
}


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
    bounds each Watcher request, including any LLM grading it runs.
    """

    def __init__(
        self,
        client_factory: Callable[[], AsyncWatcherClient] | None = None,
        *,
        timeout_seconds: float = 240,
        max_stream_chunks: int = 100_000,
        ping_seconds: float = 10,
    ) -> None:
        super().__init__()
        self.client_factory = client_factory
        self.timeout_seconds = timeout_seconds
        self.max_stream_chunks = max_stream_chunks
        self.ping_seconds = ping_seconds

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
        return data

    async def _decide(
        self, api: API, data: dict[str, Any], response: dict[str, Any], user: UserAPIKeyAuth
    ) -> dict[str, Any] | None:
        """Ask Watcher about one exchange; return a replacement response, or None to release it."""
        original = data["proxy_server_request"]
        headers = {key.lower(): value for key, value in (original.get("headers") or {}).items()}
        # Without the header there is no conversation ID to send, so Watcher
        # matches the exchange to the session it continues by shared history.
        # That session reports the Hooks API source rather than Gateway.
        session_id = headers.get("x-watcher-session-id")
        if session_id and not session_id.startswith(SESSION_PREFIX):
            session_id = SESSION_PREFIX + session_id
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
        return replacement

    async def async_post_call_success_hook(
        self, data: dict[str, Any], user_api_key_dict: UserAPIKeyAuth, response: Any
    ) -> Any:
        """Release the response unchanged, or return it with its tool calls withheld."""
        api = route(data)
        if api is None:
            return response
        replacement = await self._decide(api, data, as_dict(response), user_api_key_dict)
        if replacement is None:
            return response
        if isinstance(response, BaseModel):
            return type(response).model_validate(replacement)
        return replacement

    async def async_post_call_streaming_iterator_hook(
        self, user_api_key_dict: UserAPIKeyAuth, response: Any, request_data: dict[str, Any]
    ) -> AsyncGenerator[Any, None]:
        """Gate the stream on Watcher's decision, forwarding Messages events as they arrive."""
        api = route(request_data)
        if api is None:
            async for chunk in response:
                yield chunk
            return
        if api == "messages":
            async for event in self._messages_stream(request_data, response, user_api_key_dict):
                yield event
            return
        chunks: list[Any] = []
        async for chunk in response:
            chunks.append(chunk)
            if len(chunks) > self.max_stream_chunks:
                raise HTTPException(413, "Model response is too long to evaluate")
        try:
            assembled = assemble(api, chunks)
        except IncompleteStream:
            # A truncated stream or a provider error event: a client retry
            # regenerates the response and may succeed.
            raise HTTPException(502, "Model response stream was incomplete") from None
        except UnsupportedStream:
            # A shape this example cannot interpret comes back the same way on
            # retry, so the client is told not to retry.
            raise HTTPException(422, "Model response stream is not supported") from None
        replacement = await self._decide(api, request_data, assembled, user_api_key_dict)
        # The original chunks are never replayed: a client's stream parser can
        # read calls from them that this assembly did not see (for example a
        # Responses event absent from the completed body), so only the
        # evaluated body is streamed.
        for event in encode(api, replacement if replacement is not None else assembled):
            yield event

    async def _messages_stream(
        self, data: dict[str, Any], response: Any, user: UserAPIKeyAuth
    ) -> AsyncGenerator[bytes]:
        has_started = False
        try:
            async for event in self._gated_messages_stream(data, response, user):
                has_started = True
                yield event
        except HTTPException as error:
            if not has_started:
                raise
            error_type = "overloaded_error" if error.status_code >= 500 else "invalid_request_error"
            yield encode_messages_event({"type": "error", "error": {"type": error_type, "message": error.detail}})

    async def _stream_chunks(self, response: Any) -> AsyncGenerator[bytes]:
        count = 0
        async for chunk in response:
            count += 1
            if count > self.max_stream_chunks:
                raise HTTPException(413, "Model response is too long to evaluate")
            if not isinstance(chunk, bytes):
                raise UnsupportedStream("Unexpected Messages stream chunk")
            yield chunk

    async def _gated_messages_stream(
        self, data: dict[str, Any], response: Any, user: UserAPIKeyAuth
    ) -> AsyncGenerator[bytes]:
        assembler = MessageAssembler()
        held: list[bytes] = []
        is_holding = False
        forwarded_blocks = 0
        last_sent = time.monotonic()
        try:
            async for sse in SSEDecoder().aiter_bytes(self._stream_chunks(response)):
                event = assembler.add(sse.data)
                kind = event["type"]
                if kind not in MESSAGES_EVENT_TYPES or (kind == "ping" and assembler.message is None):
                    continue

                is_call = kind == "content_block_start" and event["content_block"]["type"] == "tool_use"
                if is_call or kind in ("message_delta", "message_stop"):
                    is_holding = True
                if kind == "ping" or not is_holding:
                    if kind == "content_block_start":
                        forwarded_blocks += 1
                    last_sent = time.monotonic()
                    yield encode_messages_event(event)
                    continue

                held.append(encode_messages_event(event))
                if time.monotonic() - last_sent >= self.ping_seconds:
                    last_sent = time.monotonic()
                    yield _PING

            message = assembler.result()
        except IncompleteStream:
            # A truncated stream or a provider error event: a client retry
            # regenerates the response and may succeed.
            raise HTTPException(502, "Model response stream was incomplete") from None
        except UnsupportedStream:
            # A shape this example cannot interpret comes back the same way on
            # retry, so the client is told not to retry.
            raise HTTPException(422, "Model response stream is not supported") from None

        decision = asyncio.create_task(self._decide("messages", data, message, user))
        try:
            while True:
                done, _ = await asyncio.wait({decision}, timeout=self.ping_seconds)
                if done:
                    break
                yield _PING
        finally:
            decision.cancel()

        replacement = decision.result()
        released = held if replacement is None else list(encode_messages_from(replacement, forwarded_blocks))
        for event in released:
            yield event


watcher_callback = WatcherCallback()
