"""The final stop-and-ask reply always ends with a question to the user.

After an escalation (or a third refusal) one last generation is asked to put
the question to the user. When that generation fails, times out, returns no
text or is cut off, the callback adds a fixed question instead of returning an
error that a client might retry by regenerating the refused proposals.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, Literal

import litellm
import pytest
from test_delivery import official_response, response
from test_incremental_safety import USER, WatcherPeer, collect, decoded, is_error, request_data
from test_recovery_cancellation import proposal
from watcher_litellm.callback import WatcherCallback
from watcher_litellm.streams import API, encode

APIS: list[API] = ["messages", "chat_completions", "responses"]
# stop_notice's question for an escalation by a command rule, the fixture's decision source.
QUESTION = "Reply A to skip it, B to do something else, or C to ask an administrator to change the policy."
Case = Literal["empty", "truncated", "failure", "timeout", "calls"]


def final_body(api: API, case: Case) -> dict[str, Any]:
    """A final reply that cannot stand alone as the question to the user."""
    body = response(api, "final", ["proposed"] if case == "calls" else [])
    if case == "empty":
        if api == "messages":
            body["content"] = []
        elif api == "chat_completions":
            body["choices"][0]["message"]["content"] = ""
        else:
            body["output"] = []
    elif case == "truncated":
        if api == "messages":
            body["stop_reason"] = "max_tokens"
        elif api == "chat_completions":
            body["choices"][0]["finish_reason"] = "length"
        else:
            body.update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
    return body


def stream_of(api: API, body: dict[str, Any]) -> list[Any]:
    """Native Router chunks for a complete provider response."""
    events = list(encode(api, body))
    if api == "messages":
        return events
    return [
        litellm.ModelResponseStream(**event) if api == "chat_completions" else event
        for event in (decoded([wire])[0] for wire in events)
    ]


def install_final(monkeypatch: pytest.MonkeyPatch, case: Case) -> list[dict[str, Any]]:
    """Make the final generation fall short in the way ``case`` names; return the requests it received."""
    requests: list[dict[str, Any]] = []

    async def generate(api: API, request: dict[str, Any], data: dict[str, Any], *, stream: bool = False) -> Any:
        requests.append(request)
        if case == "failure":
            raise RuntimeError("private provider diagnostics")
        if case == "timeout":
            await asyncio.sleep(10)
        body = final_body(api, case)
        if not stream:
            return body

        async def chunks() -> AsyncIterator[Any]:
            for chunk in stream_of(api, body):
                yield chunk

        return chunks()

    monkeypatch.setattr("watcher_litellm.callback.complete_replan", generate)
    return requests


def text_and_end(api: API, delivered: dict[str, Any]) -> tuple[str, str, list[Any]]:
    """The reply's visible text, its stop reason or status, and any client calls it contains."""
    if api == "messages":
        text = "\n".join(block["text"] for block in delivered["content"] if block["type"] == "text")
        calls = [block for block in delivered["content"] if block["type"] == "tool_use"]
        return text, delivered["stop_reason"], calls
    if api == "chat_completions":
        choice = delivered["choices"][0]
        return choice["message"]["content"] or "", choice["finish_reason"], choice["message"].get("tool_calls") or []
    text = "\n".join(
        part["text"] for item in delivered["output"] if item["type"] == "message" for part in item["content"]
    )
    calls = [item for item in delivered["output"] if item["type"] == "function_call"]
    return text, delivered["status"], calls


ENDED = {"messages": "end_turn", "chat_completions": "stop", "responses": "completed"}


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("case", ["empty", "truncated", "failure", "timeout", "calls"])
async def test_nonstream_final_reply_falls_back_to_a_fixed_question(
    api: API, case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    peer = WatcherPeer()
    peer.decide("denied", "escalate")
    requests = install_final(monkeypatch, case)

    async with asyncio.timeout(3):
        delivered = await WatcherCallback(peer.client, timeout_seconds=0.3).async_post_call_success_hook(
            request_data(api), USER, response(api, "original", ["denied"])
        )

    text, end, calls = text_and_end(api, delivered)
    assert calls == []
    assert text.endswith(QUESTION)
    assert "WATCHER ESCALATION (added by Watcher" in text
    assert end == ENDED[api]
    assert ("final text" in text) is (case in {"truncated", "calls"})
    assert "proposed" not in json.dumps(delivered)
    assert len(requests) == 1
    assert len(peer.requests) == 1


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("case", ["empty", "truncated", "failure", "timeout", "calls"])
async def test_streamed_final_reply_falls_back_to_a_fixed_question(
    api: API, case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    peer = WatcherPeer()
    peer.decide("denied", "escalate")
    requests = install_final(monkeypatch, case)

    output = await collect(WatcherCallback(peer.client, timeout_seconds=0.3), api, proposal(api, "original", "denied"))

    assert not any(is_error(event) for event in decoded(output))
    text, end, calls = text_and_end(api, official_response(api, output))
    assert calls == []
    assert text.endswith(QUESTION)
    assert "WATCHER ESCALATION (added by Watcher" in text
    assert end == ENDED[api]
    assert ("final text" in text) is (case in {"truncated", "calls"})
    assert len(requests) == 1
    assert len(peer.requests) == 1


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("raises", [True, False], ids=["error", "eof"])
async def test_streamed_final_reply_failing_midway_delivers_none_of_it(
    api: API, raises: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    peer = WatcherPeer()
    peer.decide("denied", "escalate")

    async def generate(api: API, request: dict[str, Any], data: dict[str, Any], *, stream: bool = False) -> Any:
        chunks = stream_of(api, response(api, "final", []))

        async def broken() -> AsyncIterator[Any]:
            for chunk in chunks[: len(chunks) // 2]:
                yield chunk
            if raises:
                raise RuntimeError("private provider diagnostics")

        return broken()

    monkeypatch.setattr("watcher_litellm.callback.complete_replan", generate)

    output = await collect(WatcherCallback(peer.client), api, proposal(api, "original", "denied"))

    assert not any(is_error(event) for event in decoded(output))
    text, end, calls = text_and_end(api, official_response(api, output))
    assert calls == []
    assert text.endswith(QUESTION)
    assert "final" not in text
    assert end == ENDED[api]


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("stream", [False, True], ids=["json", "stream"])
async def test_a_complete_final_question_is_delivered_unchanged(
    api: API, stream: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    peer = WatcherPeer()
    peer.decide("denied", "escalate")

    async def generate(api: API, request: dict[str, Any], data: dict[str, Any], *, stream: bool = False) -> Any:
        body = response(api, "final", [])
        if not stream:
            return body

        async def chunks() -> AsyncIterator[Any]:
            for chunk in stream_of(api, body):
                yield chunk

        return chunks()

    monkeypatch.setattr("watcher_litellm.callback.complete_replan", generate)
    callback = WatcherCallback(peer.client)
    if stream:
        delivered = official_response(api, await collect(callback, api, proposal(api, "original", "denied")))
    else:
        delivered = await callback.async_post_call_success_hook(
            request_data(api), USER, response(api, "original", ["denied"])
        )

    text, end, _ = text_and_end(api, delivered)
    assert text.endswith("final text")
    assert QUESTION not in text
    assert end == ENDED[api]


@pytest.mark.parametrize("api", APIS)
async def test_a_failed_alternative_before_the_final_generation_is_still_a_stream_error(
    api: API, monkeypatch: pytest.MonkeyPatch
) -> None:
    peer = WatcherPeer()
    peer.decide("denied", "deny")

    async def fail(api: API, request: dict[str, Any], data: dict[str, Any], *, stream: bool = False) -> Any:
        raise RuntimeError("private provider diagnostics")

    monkeypatch.setattr("watcher_litellm.callback.complete_replan", fail)

    events = decoded(await collect(WatcherCallback(peer.client), api, proposal(api, "original", "denied")))

    assert is_error(events[-1])
    assert "private" not in json.dumps(events)
    assert QUESTION not in json.dumps(events)


@pytest.mark.parametrize("api", APIS)
async def test_streamed_final_call_with_malformed_arguments_delivers_none_of_the_reply(
    api: API, monkeypatch: pytest.MonkeyPatch
) -> None:
    peer = WatcherPeer()
    peer.decide("denied", "escalate")
    body = response(api, "final", ["proposed"])
    if api == "messages":
        body["content"][1]["input"] = []
    elif api == "chat_completions":
        body["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = "[]"
    else:
        body["output"][1]["arguments"] = "[]"

    async def generate(api: API, request: dict[str, Any], data: dict[str, Any], *, stream: bool = False) -> Any:
        async def chunks() -> AsyncIterator[Any]:
            for chunk in stream_of(api, body):
                yield chunk

        return chunks()

    monkeypatch.setattr("watcher_litellm.callback.complete_replan", generate)

    output = await collect(WatcherCallback(peer.client), api, proposal(api, "original", "denied"))

    assert not any(is_error(event) for event in decoded(output))
    text, end, calls = text_and_end(api, official_response(api, output))
    assert calls == []
    assert text.endswith(QUESTION)
    assert "final text" not in text
    assert end == ENDED[api]
    assert len(peer.requests) == 1


async def test_nonstream_failed_responses_result_is_replaced_by_the_fixed_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    peer = WatcherPeer()
    peer.decide("denied", "escalate")

    async def generate(api: API, request: dict[str, Any], data: dict[str, Any], *, stream: bool = False) -> Any:
        body = response(api, "final", [])
        body.update(status="failed", error={"code": "server_error", "message": "private provider diagnostics"})
        return body

    monkeypatch.setattr("watcher_litellm.callback.complete_replan", generate)

    delivered = await WatcherCallback(peer.client).async_post_call_success_hook(
        request_data("responses"), USER, response("responses", "original", ["denied"])
    )

    text, end, calls = text_and_end("responses", delivered)
    assert calls == []
    assert text.endswith(QUESTION)
    assert "final text" not in text
    assert end == "completed"
    assert delivered.get("error") is None
    assert "private" not in json.dumps(delivered)
