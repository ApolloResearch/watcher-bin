"""Native runtime tests with deterministic provider and Watcher HTTP boundaries."""

import asyncio
import json
from copy import deepcopy

import httpx
import pytest
from google.genai import errors, types
from watcher_google_genai.integration import Observation, complete, make_client

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
        provider = make_client(
            "fixture-key", "https://provider.invalid", httpx.AsyncClient(transport=httpx.MockTransport(self.provider))
        )
        watcher = AsyncWatcherClient(
            "https://watcher.invalid",
            httpx_client=httpx.AsyncClient(
                base_url="https://watcher.invalid", transport=httpx.MockTransport(self.watcher)
            ),
            max_retries=0,
        )
        return provider, watcher


def start_history():
    return [types.Content(role="user", parts=[types.Part(text="Find weather and time.")])]


def tool_reply():
    return {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {"functionCall": {"id": "google-a", "name": "weather", "args": {"city": "Paris"}}},
                        {"functionCall": {"id": "google-b", "name": "time", "args": {"city": "Tokyo"}}},
                    ],
                },
                "finishReason": "STOP",
                "index": 0,
            }
        ]
    }


def text_reply():
    return {
        "candidates": [
            {"content": {"role": "model", "parts": [{"text": "Finished."}]}, "finishReason": "STOP", "index": 0}
        ]
    }


def with_results(history, response):
    return [
        *history,
        response.candidates[0].content,
        types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(id="google-b", name="time", response={"value": "12:00"})
                ),
                types.Part(
                    function_response=types.FunctionResponse(id="google-a", name="weather", response={"value": "cool"})
                ),
            ],
        ),
    ]


def unsupported_history():
    return [
        types.Content(role="user", parts=[types.Part(inline_data=types.Blob(mime_type="image/png", data=b"image"))])
    ]


def ambiguous_history():
    return [
        *start_history(),
        types.Content(
            role="model",
            parts=[
                types.Part(function_call=types.FunctionCall(name="weather", args={"city": "Paris"})),
                types.Part(function_call=types.FunctionCall(name="weather", args={"city": "Tokyo"})),
            ],
        ),
        types.Content(
            role="user",
            parts=[types.Part(function_response=types.FunctionResponse(name="weather", response={"value": "warm"}))],
        ),
    ]


def mark_incomplete(response):
    response["candidates"][0]["finishReason"] = "MAX_TOKENS"


def final_text(response):
    return response.candidates[0].content.parts[0].text


async def invoke(provider, observer, history):
    return await complete(
        provider,
        observer,
        model="fixture-model",
        contents=history,
        tools=[
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="weather",
                        parameters=types.Schema(
                            type=types.Type.OBJECT, properties={"city": types.Schema(type=types.Type.STRING)}
                        ),
                    ),
                    types.FunctionDeclaration(
                        name="time",
                        parameters=types.Schema(
                            type=types.Type.OBJECT, properties={"city": types.Schema(type=types.Type.STRING)}
                        ),
                    ),
                ]
            )
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
        {"tool_use_id": "google-a", "tool_name": "weather", "tool_input": {"city": "Paris"}},
        {"tool_use_id": "google-b", "tool_name": "time", "tool_input": {"city": "Tokyo"}},
    ]
    assert last["input"] == []
    assert [m["role"] for m in last["messages"]] == ["user", "assistant", "tool", "tool", "assistant"]
    assert [last["messages"][2]["tool_call_id"], last["messages"][3]["tool_call_id"]] == ["google-b", "google-a"]
    assert final_text(final) == "Finished."
    assert [r.tool_use_id for r in observer.judgments] == ["google-a", "google-b"]
    assert transport.provider_requests[0].url.path == "/v1beta/models/fixture-model:generateContent"


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
        with pytest.raises(errors.ClientError):
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
async def test_missing_native_ids_use_stable_history_positions_with_unique_names():
    first_response = tool_reply()
    for part in first_response["candidates"][0]["content"]["parts"]:
        del part["functionCall"]["id"]
    transport = Transport([first_response, text_reply()])
    provider, watcher = transport.clients()
    async with provider, watcher:
        observer = Observation(watcher, "fallback-conversation")
        history = start_history()
        first = await invoke(provider, observer, history)
        history = with_results(history, first)
        for part in history[-1].parts:
            part.function_response.id = None
        await invoke(provider, observer, history)
        await observer.flush()
    assert observer.errors == []
    assert transport.watcher_requests[0]["input"][0]["tool_use_id"] == "genai-1-0"
    assert transport.watcher_requests[0]["input"][1]["tool_use_id"] == "genai-1-1"
    assert transport.watcher_requests[1]["messages"][2]["tool_call_id"] == "genai-1-1"
    assert transport.watcher_requests[1]["messages"][3]["tool_call_id"] == "genai-1-0"
