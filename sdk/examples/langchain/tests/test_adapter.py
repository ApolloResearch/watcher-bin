"""Native execution plus real public SDK serialization; no Watcher server is contacted."""

import json
from copy import deepcopy

import httpx
import pytest
from demo.observe import run_conversation
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from watcher_langchain.adapter import IncompleteObservationError, messages_for_watcher, observe

from watcher_sdk import AsyncWatcherClient, WatcherValidationError


@pytest.mark.asyncio
async def test_native_lifecycle_complete_history_and_final_tail():
    history = await run_conversation()
    snapshot = deepcopy(history)
    sent = []

    async def respond(request):
        sent.append(json.loads(request.content))
        assert "require_recording" not in request.url.params
        body = json.loads(request.content)
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
        await observe(client, "conversation-1", history[:-1])
        outcomes = await observe(client, "conversation-1", history)
    assert history == snapshot
    final_uploads = [body for body in sent if body["input"] is None]
    evaluations = [body for body in sent if body["input"] is not None]
    last_inputs = [call for body in evaluations for call in body["input"]][-len(outcomes) :]
    assert len(final_uploads) == 2
    assert final_uploads[0]["messages"] == final_uploads[1]["messages"][:-1]
    assert final_uploads[1]["messages"] == [
        {"role": "user", "content": "Double 2 and 3"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "double-2", "function": "double", "arguments": {"value": 2}},
                {"id": "double-3", "function": "double", "arguments": {"value": 3}},
            ],
        },
        {"role": "tool", "content": "4", "tool_call_id": "double-2", "function": "double"},
        {"role": "tool", "content": "6", "tool_call_id": "double-3", "function": "double"},
        {"role": "assistant", "content": "4 and 6"},
    ]
    assert final_uploads[1]["input"] is None
    assert last_inputs == [
        {"tool_name": "double", "tool_input": {"value": 2}, "tool_use_id": "double-2"},
        {"tool_name": "double", "tool_input": {"value": 3}, "tool_use_id": "double-3"},
    ]
    assert "settings_overrides" not in evaluations[-1]
    assert [item.judged_decision for item in outcomes] == ["allow", "allow"]
    assert final_uploads[1]["external_ids"] == {"other": "langchain:conversation-1"}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing-outcomes", "http-error"])
async def test_recording_failures_surface_after_native_run(failure):
    history = await run_conversation()
    assert history[-1].content == "4 and 6"

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
    assert history[-1].content == "4 and 6"


@pytest.mark.parametrize(
    "messages",
    [
        [AIMessageChunk(content="partial")],
        [HumanMessage(content=[{"type": "image_url", "image_url": "unsupported"}])],
        [AIMessage(content="", tool_calls=[{"id": "", "name": "double", "args": {}}])],
        [ToolMessage(content="4", tool_call_id="missing")],
        [AIMessage(content="", invalid_tool_calls=[{"id": "x", "name": "double", "args": "{bad", "error": "bad"}])],
    ],
)
def test_unsupported_input_fails_explicitly(messages):
    with pytest.raises(ValueError):
        messages_for_watcher(messages)


def test_parallel_out_of_order_results_and_error():
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {"id": "a", "name": "double", "args": {"value": 2}},
                {"id": "b", "name": "double", "args": {"value": 3}},
            ],
        ),
        ToolMessage(content="failed", tool_call_id="b", status="error"),
        ToolMessage(content="4", tool_call_id="a"),
    ]
    result = messages_for_watcher(messages)
    assert result[1] == {
        "role": "tool",
        "content": "failed",
        "tool_call_id": "b",
        "function": "double",
        "error": {"type": "unknown", "message": "failed"},
    }
    result[0]["tool_calls"][0]["arguments"]["value"] = 99
    assert isinstance(messages[0], AIMessage)
    assert messages[0].tool_calls[0]["args"] == {"value": 2}


def test_duplicate_ids_and_results_rejected():
    call = AIMessage(content="", tool_calls=[{"id": "a", "name": "double", "args": {}}])
    with pytest.raises(ValueError):
        messages_for_watcher([call, call])
    result = ToolMessage(content="4", tool_call_id="a")
    with pytest.raises(ValueError):
        messages_for_watcher([call, result, result])


def test_anthropic_tool_blocks_match_native_calls_and_preserve_text():
    message = AIMessage(
        content=[
            {"type": "text", "text": "Doubling"},
            {"type": "tool_use", "id": "x", "name": "double", "input": {"value": 2}},
        ],
        tool_calls=[{"id": "x", "name": "double", "args": {"value": 2}}],
    )
    before = deepcopy(message)
    transcript = messages_for_watcher([message, ToolMessage(content="4", tool_call_id="x")])
    assert transcript[0] == {
        "role": "assistant",
        "content": "Doubling",
        "tool_calls": [{"id": "x", "function": "double", "arguments": {"value": 2}}],
    }
    assert transcript[1]["tool_call_id"] == "x"
    assert message == before


@pytest.mark.parametrize("mismatch", ["id", "name", "input", "duplicate"])
def test_anthropic_conflicting_or_duplicate_tool_blocks_fail(mismatch):
    block = {"type": "tool_use", "id": "x", "name": "double", "input": {"value": 2}}
    if mismatch != "duplicate":
        block[mismatch] = {"value": 3} if mismatch == "input" else "different"
    message = AIMessage(
        content=[block, deepcopy(block)] if mismatch == "duplicate" else [block],
        tool_calls=[{"id": "x", "name": "double", "args": {"value": 2}}],
    )
    with pytest.raises(ValueError, match="must match one native tool call exactly"):
        messages_for_watcher([message])
