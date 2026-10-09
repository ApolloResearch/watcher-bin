"""Disconnect during denial recovery and observe cleanup at external boundaries.

The real callback and SDK first receive a Watcher denial. An external Router
then blocks either generation or a read after emitting an incomplete new call.
Client cancellation must finish those operations' asynchronous cleanup before
returning, without exposing either call or starting another evaluation.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Literal

import litellm
import pytest
from litellm.proxy import proxy_server
from recovery_servers import tool_feedback
from test_delivery import response
from test_incremental_proxy import Frame
from test_incremental_safety import USER, WatcherPeer, decoded, request_data
from watcher_litellm.callback import WatcherCallback
from watcher_litellm.streams import API, encode


def proposal(api: API, prefix: str, call_id: str, *, incomplete: bool = False) -> list[Any]:
    """Return native Router chunks, optionally stopping just before a call completes."""
    result: list[Any] = []
    for wire in encode(api, response(api, prefix, [call_id])):
        event = decoded([wire])[0]
        complete = (
            (event.get("type") == "content_block_stop" and event["index"] == 1)
            or (event.get("type") == "response.output_item.done" and event["output_index"] == 1)
            or any(choice.get("finish_reason") for choice in event.get("choices", []))
        )
        if incomplete and complete:
            break
        result.append(
            wire if api == "messages" else litellm.ModelResponseStream(**event) if api == "chat_completions" else event
        )
    return result


class PendingRouter:
    """An external provider whose cleanup requires an event-loop turn to complete."""

    def __init__(self, stage: Literal["generation", "read"]) -> None:
        self.stage = stage
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.cleaned = asyncio.Event()
        self.resumed = asyncio.Event()
        self.requests: list[tuple[API, dict[str, Any]]] = []

    async def generate(self, api: API, kwargs: dict[str, Any]) -> AsyncIterator[Any]:
        """Block the request itself or return a stream that blocks after its pending tool."""
        self.requests.append((api, kwargs))
        if self.stage == "generation":
            try:
                self.entered.set()
                await self.release.wait()
                self.resumed.set()
            finally:
                await asyncio.sleep(0)
                self.cleaned.set()
        return self.events(api)

    async def events(self, api: API) -> AsyncIterator[Any]:
        """Emit a partial executable item, then wait indefinitely for provider output."""
        try:
            for chunk in proposal(api, "replacement", "unevaluated", incomplete=True):
                yield chunk
            self.entered.set()
            await self.release.wait()
            self.resumed.set()
        finally:
            await asyncio.sleep(0)
            self.cleaned.set()

    async def aanthropic_messages(self, **kwargs: Any) -> AsyncIterator[Any]:
        return await self.generate("messages", kwargs)

    async def aresponses(self, **kwargs: Any) -> AsyncIterator[Any]:
        return await self.generate("responses", kwargs)

    async def acompletion(self, **kwargs: Any) -> AsyncIterator[Any]:
        return await self.generate("chat_completions", kwargs)


@pytest.mark.parametrize("api", ["messages", "chat_completions", "responses"])
@pytest.mark.parametrize("stage", ["generation", "read"])
@pytest.mark.parametrize("close_iterator", [False, True], ids=["cancel-task", "close-iterator"])
async def test_disconnect_during_recovery_joins_provider_cleanup_and_stops_evaluation(
    monkeypatch: pytest.MonkeyPatch, api: API, stage: Literal["generation", "read"], close_iterator: bool
) -> None:
    peer = WatcherPeer()
    peer.decide("denied", "deny")
    router = PendingRouter(stage)
    monkeypatch.setattr(proxy_server, "llm_router", router)
    original_closed = asyncio.Event()

    async def original() -> AsyncIterator[Any]:
        try:
            for chunk in proposal(api, "original", "denied"):
                yield chunk
        finally:
            original_closed.set()

    callback = WatcherCallback(peer.client, ping_seconds=0.01)
    iterator = callback.async_post_call_streaming_iterator_hook(USER, original(), request_data(api))
    output: list[Frame] = []

    async def consume() -> None:
        async for chunk in iterator:
            frame = Frame(wire=chunk.decode())
            output.append(frame)
            if close_iterator and router.entered.is_set() and frame.is_keepalive:
                return

    client = asyncio.create_task(consume())
    try:
        async with asyncio.timeout(3):
            await router.entered.wait()
            assert original_closed.is_set()
            if close_iterator:
                await client
                await iterator.aclose()
            else:
                client.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await client
            assert router.cleaned.is_set(), "disconnect returned before provider cleanup finished"
            router.release.set()
            await asyncio.sleep(0)
            assert not router.resumed.is_set()
            assert len(peer.requests) == 1
            assert peer.clients and all(transport.is_closed for transport in peer.clients)
            assert len(router.requests) == 1
            called_api, kwargs = router.requests[0]
            assert called_api == api and kwargs["stream"] is True
            assert "in this proposal; the gateway withheld them" in tool_feedback(api, kwargs)["denied"]
            assert not any(frame.has_tool for frame in output)
            assert any("Watcher did not approve" in frame.wire for frame in output)
            if stage == "read":
                assert any("replacement text" in frame.wire for frame in output)
    finally:
        router.release.set()
        client.cancel()
        await asyncio.gather(client, return_exceptions=True)
        await iterator.aclose()
