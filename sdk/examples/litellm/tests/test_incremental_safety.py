"""Exercise malformed and interleaved streams through the public callback.

The Watcher boundary uses the real SDK over an HTTP transport stub. Explicit
gates let tests deny one call after another was allowed without relying on
timing sleeps or replacing the callback's implementation.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import litellm
import pytest
from fastapi import HTTPException
from litellm.proxy._types import UserAPIKeyAuth
from litellm.types.utils import Delta, StreamingChoices
from openai._streaming import SSEDecoder
from pydantic import BaseModel, ConfigDict, Field
from watcher_litellm.callback import WatcherCallback, client_calls
from watcher_litellm.streams import API, assemble

from watcher_sdk import AsyncWatcherClient

USER = UserAPIKeyAuth(user_email="stream-test@example.com")


class WatcherPeer(BaseModel):
    """Control each real SDK request independently and observe cancellation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    requests: list[dict[str, Any]] = Field(default_factory=list)
    entered: asyncio.Queue[dict[str, Any]] = Field(default_factory=asyncio.Queue)
    replies: asyncio.Queue[httpx.Response] = Field(default_factory=asyncio.Queue)
    closed: asyncio.Event = Field(default_factory=asyncio.Event)
    clients: list[httpx.AsyncClient] = Field(default_factory=list)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        """Acknowledge text recording immediately; wait for an explicit decision on tool evaluations."""
        body = json.loads(request.content)
        api: API = "responses" if body["url"].endswith("/responses") else "messages"
        if body["url"].endswith("/chat/completions"):
            api = "chat_completions"
        if not client_calls(api, body["response_body"]):
            return httpx.Response(200, json=[])
        self.requests.append(body)
        self.entered.put_nowait(body)
        try:
            return await self.replies.get()
        finally:
            self.closed.set()

    def client(self) -> AsyncWatcherClient:
        transport = httpx.AsyncClient(base_url="http://watcher.test", transport=httpx.MockTransport(self.handle))
        self.clients.append(transport)
        return AsyncWatcherClient("http://watcher.test", api_key="fixture", httpx_client=transport)

    def decide(self, call_id: str, decision: str) -> None:
        self.replies.put_nowait(
            httpx.Response(
                200,
                json=[
                    {
                        "decision": decision,
                        "judged_decision": decision,
                        "decision_source": "rule",
                        "enforcement_mode": "enforce",
                        "tool_use_id": call_id,
                        "verdict": {"explanation": "Fixture decision."},
                        "latency_ms": 1.0,
                    }
                ],
            )
        )


def request_data(api: API) -> dict[str, Any]:
    path = "chat/completions" if api == "chat_completions" else api
    body: dict[str, Any] = {"model": "fixture", "stream": True}
    if api == "responses":
        body["input"] = "Read the files."
    else:
        body["messages"] = [{"role": "user", "content": "Read the files."}]
    return {"model": "fixture", "proxy_server_request": {"url": f"http://proxy/v1/{path}", "body": body}}


async def source(chunks: list[Any]) -> AsyncIterator[Any]:
    for chunk in chunks:
        yield chunk


def sse(event: dict[str, Any]) -> bytes:
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode()


def decoded(chunks: list[bytes]) -> list[dict[str, Any]]:
    return [json.loads(event.data) for event in SSEDecoder().iter_bytes(iter(chunks)) if event.data]


def is_error(event: dict[str, Any]) -> bool:
    return "error" in event or event.get("type") in {"error", "response.failed"}


async def collect(callback: WatcherCallback, api: API, chunks: list[Any]) -> list[bytes]:
    async with asyncio.timeout(3):
        return [
            chunk
            async for chunk in callback.async_post_call_streaming_iterator_hook(USER, source(chunks), request_data(api))
        ]


async def rejected(callback: WatcherCallback, api: API, chunks: list[Any]) -> list[dict[str, Any]]:
    """Accept an HTTP failure before output or an explicit error after output."""
    output: list[bytes] = []
    async with asyncio.timeout(3):
        try:
            async for chunk in callback.async_post_call_streaming_iterator_hook(
                USER, source(chunks), request_data(api)
            ):
                output.append(chunk)
        except HTTPException as exc:
            assert 400 <= exc.status_code < 600
            return decoded(output)
    events = decoded(output)
    assert events and is_error(events[-1]), "a rejected stream must visibly fail"
    return events


def message_start(content: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "message_start",
        "message": {
            "id": "msg_fixture",
            "type": "message",
            "role": "assistant",
            "model": "fixture",
            "content": content,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 0},
        },
    }


def message_tool(index: int, call_id: str, path: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "content_block_start",
            "index": index,
            "content_block": {"type": "tool_use", "id": call_id, "name": "read_file", "input": {}},
        },
        {
            "type": "content_block_delta",
            "index": index,
            "delta": {"type": "input_json_delta", "partial_json": json.dumps({"path": path}, ensure_ascii=False)},
        },
        {"type": "content_block_stop", "index": index},
    ]


def message_end() -> list[dict[str, Any]]:
    return [
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use", "stop_sequence": None},
            "usage": {"output_tokens": 10},
        },
        {"type": "message_stop"},
    ]


def response_item(call_id: str, arguments: str, name: str = "read_file") -> dict[str, Any]:
    return {
        "type": "function_call",
        "id": f"fc_{call_id}",
        "call_id": call_id,
        "name": name,
        "arguments": arguments,
        "status": "completed",
    }


def response_start() -> dict[str, Any]:
    return {
        "type": "response.created",
        "response": {"id": "resp_fixture", "status": "in_progress", "output": [], "model": "fixture"},
    }


def response_added(index: int, item: dict[str, Any]) -> dict[str, Any]:
    return {"type": "response.output_item.added", "output_index": index, "item": item}


def response_delta(index: int, call_id: str, arguments: str) -> dict[str, Any]:
    return {
        "type": "response.function_call_arguments.delta",
        "output_index": index,
        "item_id": f"fc_{call_id}",
        "delta": arguments,
    }


def response_done(index: int, item: dict[str, Any]) -> dict[str, Any]:
    return {"type": "response.output_item.done", "output_index": index, "item": item}


def response_end(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "response.completed",
        "response": {"id": "resp_fixture", "status": "completed", "output": items, "model": "fixture"},
    }


def chat(delta: dict[str, Any], finish_reason: str | None = None) -> Any:
    return litellm.ModelResponseStream(
        id="chatcmpl_fixture",
        model="fixture",
        created=1,
        choices=[StreamingChoices(index=0, delta=Delta(**delta), finish_reason=finish_reason)],
    )


def chat_tool(index: int, arguments: str, call_id: str | None = None) -> dict[str, Any]:
    function: dict[str, Any] = {"arguments": arguments}
    if call_id is not None:
        function["name"] = "read_file"
    return {
        "index": index,
        "function": function,
        **({"id": call_id, "type": "function"} if call_id is not None else {}),
    }


@pytest.mark.parametrize("fragment_bytes", [1, 7, 64])
async def test_fragmented_messages_preserve_unicode_and_each_approved_call(fragment_bytes: int) -> None:
    peer = WatcherPeer()
    peer.decide("call_0", "allow")
    peer.decide("call_1", "allow")
    events = [
        message_start([]),
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Précis."}},
        {"type": "content_block_stop", "index": 0},
        *message_tool(1, "call_0", "café.txt"),
        *message_tool(2, "call_1", "second.txt"),
        *message_end(),
    ]
    wire = b"".join(sse(event) for event in events)
    chunks = [wire[index : index + fragment_bytes] for index in range(0, len(wire), fragment_bytes)]

    output = await collect(WatcherCallback(peer.client), "messages", chunks)

    assert len(peer.requests) == 2
    assert decoded(output) == events
    assert assemble("messages", output)["content"] == [
        {"type": "text", "text": "Précis."},
        {"type": "tool_use", "id": "call_0", "name": "read_file", "input": {"path": "café.txt"}},
        {"type": "tool_use", "id": "call_1", "name": "read_file", "input": {"path": "second.txt"}},
    ]


async def test_interleaved_chat_denial_never_releases_second_call(text_only_replan: None) -> None:
    peer = WatcherPeer()
    peer.decide("call_0", "allow")
    peer.decide("call_1", "deny")
    chunks = [
        chat({"role": "assistant", "content": "before"}),
        chat({"tool_calls": [chat_tool(0, '{"path":', "call_0")]}),
        chat({"content": "between"}),
        chat({"tool_calls": [chat_tool(1, '{"path":', "call_1")]}),
        chat({"tool_calls": [chat_tool(0, '"first.txt"}')]}),
        chat({"tool_calls": [chat_tool(1, '"second.txt"}')]}),
        chat({"content": "after"}),
        chat({}, "tool_calls"),
    ]

    output = decoded(await collect(WatcherCallback(peer.client), "chat_completions", chunks))

    assert len(peer.requests) == 2
    wire = json.dumps(output)
    assert '"call_0"' in wire
    assert "between" in wire
    calls = [
        call
        for event in output
        for choice in event.get("choices", [])
        for call in choice["delta"].get("tool_calls") or []
    ]
    assert [call["id"] for call in calls if call.get("id")] == ["call_0"]
    assert json.loads("".join(call["function"]["arguments"] for call in calls)) == {"path": "first.txt"}
    assert '"finish_reason": "tool_calls"' in wire
    assert "Watcher did not approve" in wire
    assert "after" not in wire


async def test_interleaved_responses_allow_preserves_original_event_order() -> None:
    peer = WatcherPeer()
    peer.decide("call_0", "allow")
    peer.decide("call_1", "allow")
    first = response_item("call_0", '{"path":"first.txt"}')
    second = response_item("call_1", '{"path":"second.txt"}')
    events = [
        response_start(),
        response_added(0, {**first, "arguments": "", "status": "in_progress"}),
        response_delta(0, "call_0", '{"path":'),
        response_added(1, {**second, "arguments": "", "status": "in_progress"}),
        response_delta(1, "call_1", second["arguments"]),
        response_done(1, second),
        response_delta(0, "call_0", '"first.txt"}'),
        response_done(0, first),
        response_end([first, second]),
    ]

    output = await collect(WatcherCallback(peer.client), "responses", events)

    assert len(peer.requests) == 2
    delivered = decoded(output)
    assert [event["sequence_number"] for event in delivered] == list(range(len(events)))
    assert [{key: value for key, value in event.items() if key != "sequence_number"} for event in delivered] == events


@pytest.mark.parametrize("changed_field", ["arguments", "name", "call_id"])
async def test_responses_done_cannot_replace_streamed_call(changed_field: str) -> None:
    peer = WatcherPeer()
    peer.decide("call_0", "allow")
    first = response_item("call_0", '{"path":"safe.txt"}')
    changed = {**first, changed_field: "unevaluated_replacement"}
    events = [
        response_start(),
        response_added(0, {**first, "arguments": "", "status": "in_progress"}),
        response_delta(0, "call_0", first["arguments"]),
        response_done(0, changed),
        response_end([changed]),
    ]

    output = await rejected(WatcherCallback(peer.client), "responses", events)

    assert "function_call" not in json.dumps(output)
    assert "unevaluated_replacement" not in json.dumps(output)


@pytest.mark.parametrize("snapshot", ["created", "completed"])
async def test_responses_snapshot_cannot_introduce_an_unstreamed_call(snapshot: str) -> None:
    peer = WatcherPeer()
    hidden = response_item("hidden_call", '{"path":"hidden.txt"}')
    if snapshot == "created":
        events = [response_start()]
        events[0]["response"]["output"] = [hidden]
    else:
        events = [response_start(), response_end([hidden])]

    output = await rejected(WatcherCallback(peer.client), "responses", events)

    assert "hidden_call" not in json.dumps(output)
    assert peer.requests == []


async def test_responses_terminal_snapshot_cannot_change_an_approved_call() -> None:
    peer = WatcherPeer()
    peer.decide("call_0", "allow")
    first = response_item("call_0", '{"path":"safe.txt"}')
    changed = {**first, "arguments": '{"path":"unevaluated.txt"}'}
    events = [
        response_start(),
        response_added(0, {**first, "arguments": "", "status": "in_progress"}),
        response_delta(0, "call_0", first["arguments"]),
        response_done(0, first),
        response_end([changed]),
    ]

    output = await rejected(WatcherCallback(peer.client), "responses", events)

    assert any(event.get("type") == "response.output_item.done" for event in output)
    assert "unevaluated.txt" not in json.dumps(output)
    assert not any(event.get("type") == "response.completed" for event in output)


@pytest.mark.parametrize("api", ["messages", "chat_completions", "responses"])
async def test_reused_call_id_cannot_reuse_the_first_allow(api: API) -> None:
    peer = WatcherPeer()
    peer.decide("same_id", "allow")
    if api == "messages":
        events = [
            message_start([]),
            *message_tool(0, "same_id", "safe.txt"),
            *message_tool(1, "same_id", "unevaluated.txt"),
            *message_end(),
        ]
        chunks = [sse(event) for event in events]
    elif api == "responses":
        first = response_item("same_id", '{"path":"safe.txt"}')
        second = {**response_item("same_id", '{"path":"unevaluated.txt"}'), "id": "fc_second"}
        chunks = [
            response_start(),
            response_added(0, {**first, "arguments": "", "status": "in_progress"}),
            response_delta(0, "same_id", first["arguments"]),
            response_done(0, first),
            response_added(1, second),
            response_done(1, second),
            response_end([first, second]),
        ]
    else:
        chunks = [
            chat({"role": "assistant", "content": "before"}),
            chat({"tool_calls": [chat_tool(0, '{"path":"safe.txt"}', "same_id")]}),
            chat({"tool_calls": [chat_tool(1, '{"path":"unevaluated.txt"}', "same_id")]}),
            chat({}, "tool_calls"),
        ]

    output = await rejected(WatcherCallback(peer.client), api, chunks)

    if api == "chat_completions":
        assert "before" in json.dumps(output)
        assert peer.requests == []
    else:
        assert "safe.txt" in json.dumps(output)
        assert len(peer.requests) == 1
    assert "unevaluated.txt" not in json.dumps(output)


async def test_messages_start_cannot_smuggle_a_tool() -> None:
    peer = WatcherPeer()
    hidden = {"type": "tool_use", "id": "hidden_call", "name": "delete_files", "input": {}}
    events = [message_start([hidden]), *message_end()]

    output = await rejected(WatcherCallback(peer.client), "messages", [sse(event) for event in events])

    assert "hidden_call" not in json.dumps(output)
    assert peer.requests == []


@pytest.mark.parametrize("delta_type", ["input_json_delta", "thinking_delta"])
async def test_messages_text_block_rejects_a_delta_for_another_block_type(delta_type: str) -> None:
    peer = WatcherPeer()
    delta = (
        {"type": "input_json_delta", "partial_json": '{"command":"hidden"}'}
        if delta_type == "input_json_delta"
        else {"type": "thinking_delta", "thinking": "hidden"}
    )
    events = [
        message_start([]),
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": delta},
        {"type": "content_block_stop", "index": 0},
        *message_end(),
    ]

    output = await rejected(WatcherCallback(peer.client), "messages", [sse(event) for event in events])

    assert any(event.get("type") == "content_block_start" for event in output)
    assert "hidden" not in json.dumps(output)
    assert peer.requests == []


@pytest.mark.parametrize("api", ["messages", "chat_completions", "responses"])
async def test_call_after_terminal_event_is_never_forwarded(api: API) -> None:
    peer = WatcherPeer()
    if api == "messages":
        events = [message_start([]), *message_end(), *message_tool(0, "hidden_call", "hidden.txt")]
        chunks = [sse(event) for event in events]
    elif api == "responses":
        chunks = [response_start(), response_end([]), response_added(0, response_item("hidden_call", "{}"))]
    else:
        chunks = [chat({"role": "assistant", "content": "before"}), chat({}, "stop")]
        chunks.append(chat({"tool_calls": [chat_tool(0, "{}", "hidden_call")]}))

    output = await rejected(WatcherCallback(peer.client), api, chunks)

    assert "hidden_call" not in json.dumps(output)
    assert peer.requests == []


@pytest.mark.parametrize("api", ["messages", "chat_completions", "responses"])
@pytest.mark.parametrize("close_iterator", [False, True], ids=["cancel-task", "close-iterator"])
async def test_cancelled_client_closes_grading_request_and_provider(api: API, close_iterator: bool) -> None:
    peer = WatcherPeer()
    provider_closed = asyncio.Event()
    provider_wait = asyncio.Event()
    if api == "messages":
        chunks = [sse(event) for event in [message_start([]), *message_tool(0, "call_0", "secret.txt")]]
    elif api == "responses":
        item = response_item("call_0", '{"path":"secret.txt"}')
        chunks = [response_start(), response_added(0, {**item, "arguments": ""})]
        chunks += [response_delta(0, "call_0", item["arguments"]), response_done(0, item)]
    else:
        chunks = [chat({"role": "assistant", "content": "before"})]
        chunks += [chat({"tool_calls": [chat_tool(0, '{"path":"secret.txt"}', "call_0")]}), chat({}, "tool_calls")]

    async def pending_provider() -> AsyncIterator[Any]:
        try:
            async for chunk in source(chunks):
                yield chunk
            await provider_wait.wait()
        finally:
            provider_closed.set()

    output: list[bytes] = []
    callback = WatcherCallback(peer.client, ping_seconds=0.01)
    iterator = callback.async_post_call_streaming_iterator_hook(USER, pending_provider(), request_data(api))
    waiting = asyncio.Event()

    async def consume() -> None:
        async for chunk in iterator:
            output.append(chunk)
            if close_iterator and (
                chunk.startswith(b":") or any(event.get("type") == "ping" for event in decoded([chunk]))
            ):
                waiting.set()
                return

    task = asyncio.create_task(consume())
    try:
        await asyncio.wait_for(peer.entered.get(), timeout=3)
        if close_iterator:
            await asyncio.wait_for(waiting.wait(), timeout=1)
            await task
            await asyncio.wait_for(iterator.aclose(), timeout=1)
        else:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        await asyncio.wait_for(peer.closed.wait(), timeout=1)
        await asyncio.wait_for(provider_closed.wait(), timeout=1)
        assert peer.clients and all(client.is_closed for client in peer.clients)
        assert b"secret.txt" not in b"".join(output)
    finally:
        provider_wait.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
