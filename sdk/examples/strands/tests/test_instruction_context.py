"""Installed Strands agents retain their separate instructions in every Watcher submission."""

import asyncio
import json
from contextlib import asynccontextmanager
from copy import deepcopy

import httpx
import pytest
from demo.enforce import run_conversation as run_monitored
from demo.observe import DeterministicModel
from demo.observe import run_conversation as run_observed
from strands import Agent, tool
from strands.types.content import Messages
from watcher_strands import Monitor, WatcherAgent, agent_history, observe

from watcher_sdk import AsyncWatcherClient

INSTRUCTION = "Use double only for non-negative integers."


@asynccontextmanager
async def recording_client(requests):
    """Capture actual SDK requests and return valid local allow/recording outcomes."""

    async def respond(request):
        body = json.loads(request.content)
        requests.append(body)

        def outcome(call):
            return {
                "decision": "allow",
                "judged_decision": "allow",
                "enforcement_mode": "enforce",
                "decision_source": "rule",
                "tool_use_id": call["tool_use_id"],
                "latency_ms": 1,
                "verdict": {"summary": "Fixture", "explanation": "Fixture"},
            }

        pending = body["input"]
        result = (
            []
            if pending is None
            else [outcome(call) for call in pending]
            if isinstance(pending, list)
            else outcome(pending)
        )
        return httpx.Response(200, json=result)

    async with AsyncWatcherClient(
        httpx_client=httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(respond))
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_installed_agent_preserves_system_prompt_before_tools_and_in_final_recording():
    requests, model_prompts, model_histories, effects = [], [], [], []

    class CapturingModel(DeterministicModel):
        async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
            model_prompts.append(system_prompt)
            model_histories.append(deepcopy(messages))
            async for event in super().stream(messages, tool_specs=tool_specs, system_prompt=system_prompt, **kwargs):
                yield event

    @tool
    def double(value: int) -> str:
        """Double a native fixture value and retain its actual execution."""
        effects.append(value)
        return str(value * 2)

    async with recording_client(requests) as client:
        monitor = Monitor(client, "configured-instructions")
        agent = WatcherAgent(
            monitor,
            asyncio.get_running_loop(),
            model=CapturingModel(),
            tools=[double],
            callback_handler=None,
            system_prompt=INSTRUCTION,
        )
        await asyncio.to_thread(agent, "Double 2 and 3")
        native_history = deepcopy(agent.messages)
        history = agent_history(agent)
        await monitor.record(history)
        assert agent.messages == native_history
        history[1]["content"][0]["text"] = "Changed snapshot"
        assert agent.messages == native_history

    assert sorted(effects) == [2, 3]
    assert model_prompts == [INSTRUCTION, INSTRUCTION]
    assert all(message["role"] != "system" for snapshot in model_histories for message in snapshot)
    assert len([request for request in requests if request["input"] is not None]) == 2
    assert requests[-1]["input"] is None
    assert all(request["messages"][0] == {"role": "system", "content": INSTRUCTION} for request in requests)
    assert requests[-1]["messages"][-1] == {"role": "assistant", "content": "4 and 6"}


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["monitor", "observe"])
async def test_native_demos_preserve_configured_instructions_in_recorded_history(mode):
    requests = []
    async with recording_client(requests) as client:
        if mode == "monitor":
            await run_monitored(Monitor(client, "demo-instructions"), system_prompt=INSTRUCTION)
        else:
            history = await run_observed(system_prompt=INSTRUCTION)
            await observe(client, "demo-instructions", history)
    assert all(request["messages"][0] == {"role": "system", "content": INSTRUCTION} for request in requests)
    assert requests[-1]["input"] is None
    assert requests[-1]["messages"][-1] == {"role": "assistant", "content": "4 and 6"}


@pytest.mark.parametrize("system_prompt", [None, ""])
def test_absent_system_prompt_keeps_a_detached_native_history(system_prompt):
    messages: Messages = [{"role": "user", "content": [{"text": "hello"}]}]
    agent = Agent(model=DeterministicModel(), callback_handler=None, messages=messages, system_prompt=system_prompt)
    history = agent_history(agent)
    assert history == messages
    history[0]["content"][0]["text"] = "Changed snapshot"
    assert agent.messages == [{"role": "user", "content": [{"text": "hello"}]}]
