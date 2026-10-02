"""Exercise native framework execution and the public Watcher SDK transport."""

import os

os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_TELEMETRY_DISABLED"] = "true"
os.environ["CREWAI_TESTING"] = "true"
os.environ["CREWAI_TRACING_ENABLED"] = "false"

import json
from copy import deepcopy

import httpx
import pytest
from demo.observe import run_conversation
from watcher_crewai.adapter import IncompleteObservationError, messages_for_watcher, observe

from watcher_sdk import AsyncWatcherClient, WatcherValidationError


@pytest.mark.asyncio
async def test_native_tools_and_final_answer_reach_monitor():
    history = await run_conversation()
    before = deepcopy(history)
    transcript = messages_for_watcher(history)
    assert transcript[0] == {"role": "user", "content": "Double 2 and 3"}
    assert transcript[-1] == {"role": "assistant", "content": "4 and 6"}
    calls = [call for message in transcript for call in message.get("tool_calls", [])]
    ids = [call["id"] for call in calls]
    assert len(ids) == len(set(ids))
    assert [{**call, "id": f"double-{index + 2}"} for index, call in enumerate(calls[:2])] == [
        {"id": "double-2", "function": "double", "arguments": {"value": 2}},
        {"id": "double-3", "function": "double", "arguments": {"value": 3}},
    ]
    results = [message for message in transcript if message["role"] == "tool"]
    assert [item["tool_call_id"] for item in results] == ids
    results = [{**item, "tool_call_id": f"double-{index + 2}"} for index, item in enumerate(results[:2])]
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
    assert final_uploads[1]["external_ids"] == {"other": "crewai:one"}
    assert [{**item, "tool_use_id": f"double-{index + 2}"} for index, item in enumerate(last_inputs[:2])] == [
        {"tool_name": "double", "tool_input": {"value": 2}, "tool_use_id": "double-2"},
        {"tool_name": "double", "tool_input": {"value": 3}, "tool_use_id": "double-3"},
    ]
    assert "settings_overrides" not in evaluations[-1]
    assert final_uploads[1]["input"] is None
    assert [item.judged_decision for item in outcomes] == ["allow", "allow"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing-outcomes", "http-error"])
async def test_observation_failure_does_not_reexecute_native_tools(failure):
    executions = []
    history = await run_conversation(executions=executions)
    before_executions = deepcopy(executions)
    assert len(executions) == 2

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
    assert executions == before_executions


@pytest.mark.asyncio
async def test_complete_snapshots_not_delta_are_required():
    history = await run_conversation()
    with pytest.raises(ValueError):
        first_result = next(index for index, message in enumerate(history) if message["role"] == "tool")
        messages_for_watcher(history[first_result:])
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


@pytest.mark.asyncio
async def test_native_llm_system_prompt_and_observations_are_preserved():
    history = await run_conversation()
    system_prompts = [message["content"] for message in history if message["role"] == "system"]
    assert any("calculator" in content for content in system_prompts)
    assert any("Action Input:" in message["content"] for message in history if message["role"] == "assistant")
    assert len(system_prompts) == 3
