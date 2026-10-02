"""Native provider transport and public Watcher serialization contract tests."""

import asyncio
import json
from copy import deepcopy
from typing import Any

import httpx
import pytest
from watcher_cohere.integration import Observation, complete, make_client

from watcher_sdk import AsyncWatcherClient

CALLS = [
    {"id": "call_a", "type": "function", "function": {"name": "weather", "arguments": '{"city":"Paris"}'}},
    {"id": "call_b", "type": "function", "function": {"name": "weather", "arguments": '{"city":"Tokyo"}'}},
]
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "weather",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
        },
    }
]


def reply(message, reason="stop"):
    message = deepcopy(message)
    if isinstance(message["content"], str):
        message["content"] = [{"type": "text", "text": message["content"]}]
    return {"id": "chat-1", "message": message, "finish_reason": "TOOL_CALL" if reason == "tool_calls" else "COMPLETE"}


class Transport:
    """Deterministic external boundaries; neither endpoint is a live service."""

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
        self.watcher_requests.append(json.loads(request.content))
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
            for item in self.watcher_requests[-1]["input"]
        ]
        return httpx.Response(
            self.watcher_status,
            headers={"X-Watcher-Recording": "complete"},
            json=outcomes if self.watcher_status == 200 else {"detail": "unavailable"},
        )


def clients(transport):
    provider = make_client(
        "fixture-key",
        "https://provider.invalid/v1",
        httpx.AsyncClient(transport=httpx.MockTransport(transport.provider)),
    )
    watcher = AsyncWatcherClient(
        "https://watcher.invalid",
        max_retries=0,
        httpx_client=httpx.AsyncClient(
            base_url="https://watcher.invalid", transport=httpx.MockTransport(transport.watcher)
        ),
    )
    return provider, watcher


@pytest.mark.asyncio
async def test_parallel_tools_results_and_final_tail_keep_identity():
    transport = Transport(
        [
            reply({"role": "assistant", "content": None, "tool_calls": CALLS}, "tool_calls"),
            reply({"role": "assistant", "content": "Paris is cool; Tokyo is warm."}),
        ]
    )
    provider, watcher = clients(transport)
    async with provider, watcher:
        observer = Observation(watcher, "conversation-42")
        history: list[dict] = [
            {"role": "system", "content": "Report weather."},
            {"role": "user", "content": "Paris and Tokyo?"},
        ]
        original = deepcopy(history)
        result = await complete(provider, observer, model="fixture-model", messages=history, tools=TOOLS)
        assert history == original
        assert [call.id for call in result.message.tool_calls] == ["call_a", "call_b"]
        history += [
            {"role": "assistant", "content": None, "tool_calls": deepcopy(CALLS)},
            {"role": "tool", "tool_call_id": "call_b", "content": "warm"},
            {"role": "tool", "tool_call_id": "call_a", "content": "cool"},
        ]
        await complete(provider, observer, model="fixture-model", messages=history)
        await observer.flush()
    assert observer.errors == []
    assert len(transport.watcher_requests) == 2
    first, final = transport.watcher_requests
    assert first["external_ids"] == final["external_ids"] == {"other": "conversation-42"}
    assert first["input"] == [
        {"tool_use_id": "call_a", "tool_name": "weather", "tool_input": {"city": "Paris"}},
        {"tool_use_id": "call_b", "tool_name": "weather", "tool_input": {"city": "Tokyo"}},
    ]
    assert final["input"] == []
    assert "settings_overrides" not in first
    assert [result.tool_use_id for result in observer.judgments] == ["call_a", "call_b"]
    assert [result.judged_decision.value for result in observer.judgments] == ["deny", "deny"]
    assert final["format"] == "watcher"
    assert first["messages"][-1]["tool_calls"] == [
        {"id": "call_a", "function": "weather", "arguments": {"city": "Paris"}, "type": "function"},
        {"id": "call_b", "function": "weather", "arguments": {"city": "Tokyo"}, "type": "function"},
    ]
    assert [message["role"] for message in final["messages"]] == [
        "system",
        "user",
        "assistant",
        "tool",
        "tool",
        "assistant",
    ]
    assert final["messages"][3]["tool_call_id"] == "call_b"
    assert final["messages"][4]["tool_call_id"] == "call_a"
    assert final["messages"][-1]["content"][0]["text"] == "Paris is cool; Tokyo is warm."
    sent = json.loads(transport.provider_requests[0].content)
    assert sent["tools"] == TOOLS
    assert sent["messages"] == original
    assert "tools" not in json.loads(transport.provider_requests[1].content)


@pytest.mark.asyncio
async def test_slow_watcher_does_not_delay_provider_response():
    transport = Transport([reply({"role": "assistant", "content": "ready"})])
    transport.release.clear()
    provider, watcher = clients(transport)
    async with provider, watcher:
        observer = Observation(watcher, "conversation-42")
        response = await asyncio.wait_for(
            complete(provider, observer, model="fixture-model", messages=[{"role": "user", "content": "hello"}]), 1
        )
        assert response.message.content[0].text == "ready"
        await asyncio.wait_for(transport.started.wait(), 1)
        assert transport.watcher_requests == []
        transport.release.set()
        await observer.flush()
    assert len(transport.watcher_requests) == 1


@pytest.mark.asyncio
async def test_watcher_failure_is_visible_without_changing_provider_result():
    transport = Transport([reply({"role": "assistant", "content": "ready"})], watcher_status=503)
    provider, watcher = clients(transport)
    async with provider, watcher:
        observer = Observation(watcher, "conversation-42")
        response = await complete(
            provider, observer, model="fixture-model", messages=[{"role": "user", "content": "hello"}]
        )
        await observer.flush()
    assert response.message.content[0].text == "ready"
    assert len(observer.errors) == 1


@pytest.mark.asyncio
async def test_provider_failure_does_not_create_a_successful_transcript():
    transport = Transport(
        [{"error": {"message": "invalid request", "type": "invalid_request_error"}}], provider_status=400
    )
    provider, watcher = clients(transport)
    async with provider, watcher:
        observer = Observation(watcher, "conversation-42")
        with pytest.raises(Exception) as raised:
            await complete(provider, observer, model="fixture-model", messages=[{"role": "user", "content": "hello"}])
        assert raised.value.status_code == 400
        await observer.flush()
    assert transport.watcher_requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", ['{"city":', '{"city":"Paris","city":"Tokyo"}', "[1,2]"])
async def test_malformed_tool_arguments_are_reported_without_submission(arguments):
    calls: list[dict[str, Any]] = deepcopy(CALLS[:1])
    calls[0]["function"]["arguments"] = arguments
    transport = Transport([reply({"role": "assistant", "content": None, "tool_calls": calls}, "tool_calls")])
    provider, watcher = clients(transport)
    async with provider, watcher:
        observer = Observation(watcher, "conversation-42")
        response = await complete(
            provider, observer, model="fixture-model", messages=[{"role": "user", "content": "hello"}]
        )
        await observer.flush()
    assert response.message.tool_calls[0].function.arguments == arguments
    assert observer.errors == ["ValueError"]
    assert transport.watcher_requests == []


@pytest.mark.asyncio
async def test_unsupported_content_does_not_mutate_or_silently_drop_history():
    history = [
        {"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": "sample", "format": "wav"}}]}
    ]
    original = deepcopy(history)
    transport = Transport([reply({"role": "assistant", "content": "heard"})])
    provider, watcher = clients(transport)
    async with provider, watcher:
        observer = Observation(watcher, "conversation-42")
        await complete(provider, observer, model="fixture-model", messages=history)
        await observer.flush()
    assert history == original
    assert observer.errors == ["ValueError"]
    assert transport.watcher_requests == []


def test_empty_identity_is_rejected():
    with pytest.raises(ValueError, match="conversation ID"):
        Observation(None, "")
