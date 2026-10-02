"""Native runtime tests with deterministic provider and Watcher HTTP boundaries."""

import asyncio
import json
from copy import deepcopy

import httpx
import pytest
from ollama import Image, Message, ResponseError
from watcher_ollama.integration import Observation, complete, make_client

from watcher_sdk import AsyncWatcherClient


class Transport:
    def __init__(self, responses, provider_status=200, watcher_status=200):
        self.responses = iter(responses)
        self.provider_status = provider_status
        self.watcher_status = watcher_status
        self.provider_requests = []
        self.watcher_requests = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()

    def provider(self, request):
        self.provider_requests.append(request)
        return httpx.Response(self.provider_status, json=next(self.responses))

    async def watcher(self, request):
        self.started.set()
        await asyncio.wait_for(self.release.wait(), 2)
        payload = json.loads(request.content)
        self.watcher_requests.append(payload)
        outcomes = [
            {
                "decision": "deferred",
                "judged_decision": "deny",
                "decision_source": "rule",
                "enforcement_mode": "observe",
                "verdict": {},
                "latency_ms": 1,
                "tool_use_id": item["tool_use_id"],
            }
            for item in payload["input"]
        ]
        return httpx.Response(
            self.watcher_status,
            json=outcomes if self.watcher_status == 200 else {"detail": "unavailable"},
        )

    def clients(self):
        provider = make_client("https://provider.invalid", httpx.MockTransport(self.provider))
        watcher = AsyncWatcherClient(
            "https://watcher.invalid",
            httpx_client=httpx.AsyncClient(
                base_url="https://watcher.invalid", transport=httpx.MockTransport(self.watcher)
            ),
            max_retries=0,
        )
        return provider, watcher


def start_history():
    return [Message(role="user", content="Find weather and time.")]


def tool_reply():
    return {
        "model": "fixture-model",
        "created_at": "2026-09-14T00:00:00Z",
        "done": True,
        "done_reason": "stop",
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "weather", "arguments": {"city": "Paris"}}},
                {"function": {"name": "time", "arguments": {"city": "Tokyo"}}},
            ],
        },
    }


def text_reply():
    return {
        "model": "fixture-model",
        "created_at": "2026-09-14T00:00:00Z",
        "done": True,
        "done_reason": "stop",
        "message": {"role": "assistant", "content": "Finished."},
    }


def with_results(history, response):
    return [
        *history,
        response.message,
        Message(role="tool", tool_name="time", content="12:00"),
        Message(role="tool", tool_name="weather", content="cool"),
    ]


def unsupported_history():
    return [Message(role="user", content="image", images=[Image(value=b"image")])]


def ambiguous_history():
    return [
        *start_history(),
        Message(
            role="assistant",
            tool_calls=[
                Message.ToolCall(function=Message.ToolCall.Function(name="weather", arguments={"city": "Paris"})),
                Message.ToolCall(function=Message.ToolCall.Function(name="weather", arguments={"city": "Tokyo"})),
            ],
        ),
    ]


def mark_incomplete(response):
    response["done_reason"] = "length"


def final_text(response):
    return response.message.content


async def invoke(provider, observer, history):
    return await complete(
        provider,
        observer,
        model="fixture-model",
        messages=history,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "weather",
                    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "time",
                    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
                },
            },
        ],
    )


@pytest.mark.asyncio
async def test_native_parallel_calls_results_and_tail():
    transport = Transport([tool_reply(), text_reply()])
    provider, watcher = transport.clients()
    async with provider, watcher:
        observer = Observation(watcher, "native-conversation")
        history = start_history()
        before = deepcopy(history)
        response = await invoke(provider, observer, history)
        assert history == before
        history = with_results(history, response)
        final = await invoke(provider, observer, history)
        await observer.flush()
    assert observer.errors == []
    assert len(transport.watcher_requests) == 2
    first, last = transport.watcher_requests
    assert first["external_ids"] == last["external_ids"] == {"other": "native-conversation"}
    assert first["input"] == [
        {"tool_use_id": "ollama-1-0", "tool_name": "weather", "tool_input": {"city": "Paris"}},
        {"tool_use_id": "ollama-1-1", "tool_name": "time", "tool_input": {"city": "Tokyo"}},
    ]
    assert last["input"] == []
    assert [m["role"] for m in last["messages"]] == ["user", "assistant", "tool", "tool", "assistant"]
    assert [last["messages"][2]["tool_call_id"], last["messages"][3]["tool_call_id"]] == ["ollama-1-1", "ollama-1-0"]
    assert final_text(final) == "Finished."
    assert [r.tool_use_id for r in observer.judgments] == ["ollama-1-0", "ollama-1-1"]
    assert transport.provider_requests[0].url.path == "/api/chat"


@pytest.mark.asyncio
async def test_slow_monitoring_does_not_delay_native_response():
    transport = Transport([text_reply()])
    transport.release.clear()
    provider, watcher = transport.clients()
    async with provider, watcher:
        observer = Observation(watcher, "native-conversation")
        result = await asyncio.wait_for(invoke(provider, observer, start_history()), 1)
        assert final_text(result) == "Finished."
        await asyncio.wait_for(transport.started.wait(), 1)
        assert transport.watcher_requests == []
        transport.release.set()
        await observer.flush()
    assert len(transport.watcher_requests) == 1


@pytest.mark.asyncio
async def test_monitoring_failure_is_reported_without_changing_response():
    transport = Transport([text_reply()], watcher_status=503)
    provider, watcher = transport.clients()
    async with provider, watcher:
        observer = Observation(watcher, "native-conversation")
        result = await invoke(provider, observer, start_history())
        await observer.flush()
    assert final_text(result) == "Finished."
    assert len(observer.errors) == 1


@pytest.mark.asyncio
async def test_provider_error_has_no_fabricated_transcript():
    transport = Transport(
        [{"error": {"message": "invalid", "code": 400, "status": "INVALID_ARGUMENT"}}], provider_status=400
    )
    provider, watcher = transport.clients()
    async with provider, watcher:
        observer = Observation(watcher, "native-conversation")
        with pytest.raises(ResponseError):
            await invoke(provider, observer, start_history())
        await observer.flush()
    assert transport.watcher_requests == []


@pytest.mark.asyncio
async def test_unsupported_native_content_is_not_silently_dropped():
    transport = Transport([text_reply()])
    provider, watcher = transport.clients()
    async with provider, watcher:
        observer = Observation(watcher, "native-conversation")
        await invoke(provider, observer, unsupported_history())
        await observer.flush()
    assert observer.errors == ["ValueError"]
    assert transport.watcher_requests == []


@pytest.mark.asyncio
async def test_ambiguous_results_are_reported():
    transport = Transport([text_reply()])
    provider, watcher = transport.clients()
    async with provider, watcher:
        observer = Observation(watcher, "native-conversation")
        await invoke(provider, observer, ambiguous_history())
        await observer.flush()
    assert observer.errors == ["ValueError"]
    assert transport.watcher_requests == []


@pytest.mark.asyncio
async def test_truncated_response_is_not_reported_as_complete():
    response = text_reply()
    mark_incomplete(response)
    transport = Transport([response])
    provider, watcher = transport.clients()
    async with provider, watcher:
        observer = Observation(watcher, "native-conversation")
        await invoke(provider, observer, start_history())
        await observer.flush()
    assert observer.errors == ["ValueError"]
    assert transport.watcher_requests == []


def test_missing_conversation_identity_fails_early():
    with pytest.raises(ValueError, match="conversation ID"):
        Observation(None, "")  # ty: ignore[invalid-argument-type]  # Invalid ID fails before the unused client is accessed.


@pytest.mark.asyncio
async def test_repeated_tool_names_after_results_receive_new_stable_ids():
    transport = Transport([tool_reply(), tool_reply(), text_reply()])
    provider, watcher = transport.clients()
    async with provider, watcher:
        observer = Observation(watcher, "repeat-conversation")
        history = start_history()
        first = await invoke(provider, observer, history)
        history = with_results(history, first)
        second = await invoke(provider, observer, history)
        history = with_results(history, second)
        await invoke(provider, observer, history)
        await observer.flush()
    assert observer.errors == []
    assert transport.watcher_requests[0]["input"][0]["tool_use_id"] == "ollama-1-0"
    assert transport.watcher_requests[1]["input"][0]["tool_use_id"] == "ollama-4-0"
    assert transport.watcher_requests[2]["messages"][5]["tool_call_id"] == "ollama-4-1"
    assert transport.watcher_requests[2]["messages"][6]["tool_call_id"] == "ollama-4-0"
    assert transport.watcher_requests[2]["input"] == []
