"""Exercise the actual OpenAI LLM extension through LlamaIndex's FunctionAgent."""

import json

import httpx
import pytest
from llama_index.core.base.llms.types import ChatMessage, ToolCallBlock
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.llms.openai import OpenAI
from openai.types.chat import ChatCompletion
from watcher_llamaindex.adapter import messages_for_watcher
from watcher_llamaindex.monitoring import Monitor, ToolBlocked
from watcher_llamaindex.native import MonitoredFunctionAgent

from watcher_sdk import AsyncWatcherClient


def reply(final=False):
    message: dict = {"role": "assistant", "content": "done" if final else None}
    if not final:
        message["tool_calls"] = [
            {"id": "native-call", "type": "function", "function": {"name": "weather", "arguments": '{"city":"Paris"}'}}
        ]
    return {
        "id": "fixture",
        "object": "chat.completion",
        "created": 1,
        "model": "gpt-4o",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop" if final else "tool_calls"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,decision,allowed",
    [
        ("enforce", "allow", True),
        ("enforce", "deny", False),
        ("enforce", "escalate", False),
        ("observe", "deny", True),
        ("paused", "allow", True),
    ],
)
async def test_real_openai_model_native_calls_wait_for_matching_watcher_policy(mode, decision, allowed):
    provider_requests = []
    watcher_requests = []
    effects = []

    def model_transport(request):
        body = json.loads(request.content)
        provider_requests.append(body)
        return httpx.Response(200, json=reply(any(item["role"] == "tool" for item in body["messages"])))

    def watcher_transport(request):
        body = json.loads(request.content)
        watcher_requests.append(body)
        assert body.get("settings_overrides") is None
        item = body.get("input")
        if not item:
            return httpx.Response(200, json=[])
        assert item["tool_use_id"] == "native-call" and item["tool_input"] == {"city": "Paris"}
        return httpx.Response(
            200,
            json={
                "tool_use_id": item["tool_use_id"],
                "decision": "deferred" if mode in ("observe", "paused") else decision,
                "judged_decision": None if mode == "paused" else decision,
                "decision_source": "bypass" if mode == "paused" else "rule",
                "enforcement_mode": mode,
                "verdict": {},
                "latency_ms": 0,
            },
        )

    async def weather(city: str) -> str:
        """Return deterministic local weather after the framework's native gate."""
        effects.append(city)
        return "clear"

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(model_transport)) as http,
        AsyncWatcherClient(
            "http://watcher.invalid",
            httpx_client=httpx.AsyncClient(
                base_url="http://watcher.invalid", transport=httpx.MockTransport(watcher_transport)
            ),
        ) as watcher,
    ):
        model = OpenAI(
            model="gpt-4o", api_key="fixture-key", api_base="http://fixture/v1", max_retries=0, async_http_client=http
        )
        memory = ChatMemoryBuffer.from_defaults(token_limit=10000, tokenizer_fn=lambda text: list(text))
        monitor = Monitor(watcher, "real-openai")
        agent = MonitoredFunctionAgent(llm=model, tools=[weather], monitor=monitor)
        if allowed:
            await agent.run("Read Paris weather", memory=memory)
            history = memory.get_all()
            assert any(isinstance(block, ToolCallBlock) for message in history for block in message.blocks)
            assert any(message.additional_kwargs.get("tool_calls") for message in history)
            await monitor.record(history)
            converted = messages_for_watcher(history)
            assert [m["tool_call_id"] for m in converted if m["role"] == "tool"] == ["native-call"]
            assert converted[-1]["content"] == "done"
        else:
            with pytest.raises(ToolBlocked):
                await agent.run("Read Paris weather", memory=memory)
    assert effects == (["Paris"] if allowed else [])
    assert len(provider_requests) == (2 if allowed else 1)
    assert watcher_requests


def test_legacy_sdk_tool_objects_and_plain_mappings_produce_same_identity():
    response = ChatCompletion.model_validate(reply())
    calls = response.choices[0].message.tool_calls
    assert calls is not None
    call = calls[0]
    model_message = ChatMessage(role="assistant", content="", additional_kwargs={"tool_calls": [call]})
    mapping_message = ChatMessage(
        role="assistant", content="", additional_kwargs={"tool_calls": [call.model_dump(mode="json")]}
    )
    assert (
        messages_for_watcher([model_message])
        == messages_for_watcher([mapping_message])
        == [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "native-call", "function": "weather", "arguments": {"city": "Paris"}}],
            }
        ]
    )


def test_conflicting_block_and_legacy_arguments_are_not_silently_preferred():
    message = ChatMessage(
        role="assistant",
        blocks=[ToolCallBlock(tool_call_id="native-call", tool_name="weather", tool_kwargs={"city": "Paris"})],
        additional_kwargs={
            "tool_calls": [
                {
                    "id": "native-call",
                    "type": "function",
                    "function": {"name": "weather", "arguments": '{"city":"Tokyo"}'},
                }
            ]
        },
    )
    with pytest.raises(ValueError, match="representations disagree"):
        messages_for_watcher([message])
