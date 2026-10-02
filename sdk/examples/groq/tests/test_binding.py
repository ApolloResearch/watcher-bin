"""Bind callbacks to captured arguments despite caller mutation during grading."""

import asyncio
from copy import deepcopy

import pytest
from watcher_groq.integration import fetch
from watcher_groq.monitoring import Monitor

from tests.support import CALLS, HISTORY, Transport, clients, reply


@pytest.mark.asyncio
async def test_mutation_while_waiting_cannot_change_executed_arguments():
    transport, effects = Transport(), []
    transport.release.clear()

    async def weather(**arguments):
        effects.append(arguments)

    async with clients(transport) as (provider, watcher):
        _, exchange = await fetch(provider, {"model": "fixture-model", "messages": HISTORY})
        task = asyncio.create_task(Monitor(watcher, "conversation").dispatch(exchange, {"weather": weather}))
        await asyncio.wait_for(transport.started.wait(), 1)
        exchange["response"]["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = '{"city":"changed"}'
        transport.release.set()
        await task
    assert effects == [{"city": "Paris"}, {"city": "Tokyo"}]


@pytest.mark.asyncio
async def test_boolean_and_number_arguments_reach_callback_unchanged():
    calls = deepcopy(CALLS[:1])
    calls[0]["function"]["arguments"] = '{"value":false,"count":0}'
    transport, effects = Transport([reply(calls=calls)]), []

    async def weather(**arguments):
        effects.append(arguments)

    async with clients(transport) as (provider, watcher):
        _, exchange = await fetch(provider, {"model": "fixture-model", "messages": HISTORY})
        await Monitor(watcher, "conversation").dispatch(exchange, {"weather": weather})
    assert type(effects[0]["value"]) is bool and type(effects[0]["count"]) is int
