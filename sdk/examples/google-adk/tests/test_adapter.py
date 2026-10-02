"""Exercise native framework execution and the public Watcher SDK transport."""

import json
from copy import deepcopy

import httpx
import pytest
from demo.observe import run_conversation
from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types
from watcher_google_adk.adapter import IncompleteObservationError, messages_for_watcher, observe

from watcher_sdk import AsyncWatcherClient, WatcherValidationError


@pytest.mark.asyncio
async def test_native_tools_and_final_answer_reach_monitor():
    history = await run_conversation()
    before = deepcopy(history)
    transcript = messages_for_watcher(history)
    assert transcript[0] == {"role": "system", "content": 'You are an agent. Your internal name is "example".'}
    assert transcript[1] == {"role": "user", "content": "Double 2 and 3"}
    assert transcript[-1] == {"role": "assistant", "content": "4 and 6"}
    calls = [call for message in transcript for call in message.get("tool_calls", [])]
    assert calls == [
        {"id": "double-2", "function": "double", "arguments": {"value": 2}},
        {"id": "double-3", "function": "double", "arguments": {"value": 3}},
    ]
    results = [message for message in transcript if message["role"] == "tool"]
    assert results == [
        {"role": "tool", "content": "4", "tool_call_id": "double-2", "function": "double"},
        {"role": "tool", "content": "6", "tool_call_id": "double-3", "function": "double"},
    ]
    sent = []

    async def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        assert "require_recording" not in request.url.params
        outcomes = [
            {
                "decision": "deferred",
                "judged_decision": "allow",
                "decision_source": "rule",
                "enforcement_mode": "observe",
                "tool_use_id": call["tool_use_id"],
                "verdict": {
                    "severity_score": None,
                    "severity_label": None,
                    "summary": "Allowed",
                    "explanation": "fixture",
                },
                "latency_ms": 1,
            }
            for call in body["input"] or []
        ]
        return httpx.Response(200, json=outcomes)

    async with (
        httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(respond)) as transport,
        AsyncWatcherClient(
            "https://watcher.invalid", httpx_client=transport, manage_external_httpx_client_lifecycle=False
        ) as client,
    ):
        await observe(client, "one", history[:-1])
        outcomes = await observe(client, "one", history)
    assert history == before
    final_uploads = [body for body in sent if body["input"] is None]
    evaluations = [body for body in sent if body["input"] is not None]
    last_inputs = [call for body in evaluations for call in body["input"]][-len(outcomes) :]
    assert len(final_uploads) == 2
    assert final_uploads[0]["messages"] == transcript[:-1]
    assert final_uploads[1]["messages"] == transcript
    assert final_uploads[1]["external_ids"] == {"other": "google-adk:one"}
    assert last_inputs == [
        {"tool_name": "double", "tool_input": {"value": 2}, "tool_use_id": "double-2"},
        {"tool_name": "double", "tool_input": {"value": 3}, "tool_use_id": "double-3"},
    ]
    assert "settings_overrides" not in evaluations[-1]
    assert final_uploads[1]["input"] is None
    assert [item.judged_decision for item in outcomes] == ["allow", "allow"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing-outcomes", "http-error"])
async def test_observation_failure_does_not_reexecute_native_tools(failure):
    history = await run_conversation()

    async def respond(request):
        return (
            httpx.Response(200, json=[])
            if failure == "missing-outcomes"
            else httpx.Response(422, json={"detail": [{"loc": ["body"], "msg": "rejected", "type": "value_error"}]})
        )

    async with (
        httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(respond)) as transport,
        AsyncWatcherClient(
            "https://watcher.invalid", httpx_client=transport, manage_external_httpx_client_lifecycle=False
        ) as client,
    ):
        with pytest.raises(IncompleteObservationError if failure == "missing-outcomes" else WatcherValidationError):
            await observe(client, "one", history)
    assert messages_for_watcher(history)[-1]["content"] == "4 and 6"


@pytest.mark.asyncio
async def test_complete_snapshots_not_delta_are_required():
    history = await run_conversation()
    with pytest.raises(ValueError):
        messages_for_watcher(history[-2:])
    assert messages_for_watcher(history)[-1]["content"] == "4 and 6"


@pytest.mark.asyncio
async def test_source_is_not_mutated_by_conversion():
    history = await run_conversation()
    before = deepcopy(history)
    messages = messages_for_watcher(history)
    for item in messages:
        for call in item.get("tool_calls", []):
            call["arguments"]["value"] = 99
    assert history == before


def test_unknown_native_message_rejected():
    with pytest.raises(ValueError):
        messages_for_watcher([object()])


@pytest.mark.asyncio
async def test_empty_identity_rejected_before_network():
    async with AsyncWatcherClient("https://watcher.invalid") as client:
        with pytest.raises(ValueError):
            await observe(client, "", [])


def test_empty_history_supported():
    assert messages_for_watcher([]) == []


class DictionaryResultModel(BaseLlm):
    """Request one argument-free native tool, then finish after its dictionary result."""

    async def generate_content_async(self, llm_request, stream=False):
        if any(part.function_response for content in llm_request.contents for part in content.parts or []):
            content = types.Content(role="model", parts=[types.Part(text="Done")])
        else:
            content = types.Content(
                role="model",
                parts=[types.Part(function_call=types.FunctionCall(id="status-call", name="status", args=None))],
            )
        yield LlmResponse(content=content)


@pytest.mark.asyncio
async def test_native_adk_dictionary_tool_and_absent_arguments():
    def status() -> dict:
        """Return a structured native tool result without arguments."""
        return {"status": "ok", "value": 4, "nested": {"ready": True}}

    runner = InMemoryRunner(
        agent=LlmAgent(name="dictionary_example", model=DictionaryResultModel(model="deterministic"), tools=[status]),
        app_name="dictionary-example",
    )
    session = await runner.session_service.create_session(app_name="dictionary-example", user_id="test")
    async for _event in runner.run_async(
        user_id="test",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="Get status")]),
    ):
        pass
    session = await runner.session_service.get_session(
        app_name="dictionary-example",
        user_id="test",
        session_id=session.id,
    )
    assert session is not None
    history = [event.content for event in session.events if event.content is not None]
    transcript = messages_for_watcher(history)
    calls = [call for message in transcript for call in message.get("tool_calls", [])]
    assert calls == [{"id": "status-call", "function": "status", "arguments": {}}]
    result = next(message for message in transcript if message["role"] == "tool")
    assert result["tool_call_id"] == "status-call"
    assert json.loads(result["content"]) == status()
    assert transcript[-1] == {"role": "assistant", "content": "Done"}


@pytest.mark.parametrize("payload", [{"nested": [1, True, None]}, [1, "two"], 4, None])
def test_adk_wrapped_json_results_are_serialized_losslessly(payload):
    history = [
        types.Content(
            role="model", parts=[types.Part(function_call=types.FunctionCall(id="x", name="status", args=None))]
        ),
        types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id="x",
                        name="status",
                        response={"result": payload},
                    )
                )
            ],
        ),
    ]
    before = deepcopy(history)
    transcript = messages_for_watcher(history)
    assert transcript[0]["tool_calls"][0]["arguments"] == {}
    assert json.loads(transcript[1]["content"]) == payload
    assert history == before
