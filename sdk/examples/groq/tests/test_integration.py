"""Verify native provider calls preserve exact HTTP pairs and application history."""

from copy import deepcopy

import pytest
from groq import BadRequestError
from watcher_groq.integration import Observation, complete

from tests.support import CALLS, HISTORY, TOOLS, Transport, clients, reply


@pytest.mark.asyncio
async def test_native_parallel_calls_results_and_final_answer_preserve_wire_pair():
    transport = Transport([reply(calls=CALLS), reply()], mode="observe", decision="deny")
    history = deepcopy(HISTORY)
    async with clients(transport) as (provider, watcher):
        observation = Observation(watcher, "conversation")
        first = await complete(provider, observation, model="fixture-model", messages=history, tools=TOOLS)
        assert history == HISTORY
        assert [call.id for call in first.choices[0].message.tool_calls] == ["call-a", "call-b"]
        history += [
            reply(calls=CALLS)["choices"][0]["message"],
            {"role": "tool", "tool_call_id": "call-b", "content": "warm"},
            {"role": "tool", "tool_call_id": "call-a", "content": "cool"},
        ]
        await complete(provider, observation, model="fixture-model", messages=history)
        await observation.flush()
    assert observation.errors == []
    assert len(transport.watcher_requests) == 2
    first, last = transport.watcher_requests
    assert first["external_ids"] == last["external_ids"] == {"other": "conversation"}
    assert first["response_body"]["provider_extension"] == {"kept": True, "null": None}
    assert last["request_body"]["messages"] == history
    assert last["response_body"]["choices"][0]["message"]["content"] == "Done"
    assert [item.tool_use_id for item in observation.judgments] == ["call-a", "call-b"]


@pytest.mark.asyncio
async def test_provider_failure_does_not_create_successful_exchange():
    transport = Transport([{"error": {"message": "invalid", "type": "invalid_request_error"}}], provider_status=400)
    async with clients(transport) as (provider, watcher):
        observation = Observation(watcher, "conversation")
        with pytest.raises(BadRequestError):
            await complete(provider, observation, model="fixture-model", messages=HISTORY)
        await observation.flush()
    assert transport.watcher_requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", ["{", '{"x":1,"x":2}', "NaN", "[1]"])
async def test_ambiguous_tool_argument_observation_fails_visibly(arguments):
    calls = deepcopy(CALLS[:1])
    calls[0]["function"]["arguments"] = arguments
    transport = Transport([reply(calls=calls)], mode="observe")
    async with clients(transport) as (provider, watcher):
        observation = Observation(watcher, "conversation")
        await complete(provider, observation, model="fixture-model", messages=HISTORY)
        await observation.flush()
    assert observation.error_count == 1
    assert transport.watcher_requests == []
