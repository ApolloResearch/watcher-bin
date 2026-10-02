"""Observe mode reports asynchronous failures and bounds pending work."""

import asyncio

import pytest
from watcher_huggingface_inference.integration import Observation, complete, fetch

from tests.support import HISTORY, Transport, clients, reply


@pytest.mark.asyncio
async def test_slow_grading_does_not_delay_observed_native_response():
    transport = Transport([reply()], mode="observe")
    transport.release.clear()
    async with clients(transport) as (provider, watcher):
        observation = Observation(watcher, "conversation")
        response = await asyncio.wait_for(complete(provider, observation, model="fixture-model", messages=HISTORY), 1)
        await asyncio.wait_for(transport.started.wait(), 1)
        assert response.choices[0].message.content == "Done" and transport.watcher_requests == []
        transport.release.set()
        await observation.flush()
    assert observation.errors == []


@pytest.mark.asyncio
async def test_watcher_transport_failure_is_visible():
    transport = Transport([reply()], mode="observe", watcher_status=503)
    async with clients(transport) as (provider, watcher):
        observation = Observation(watcher, "conversation")
        await complete(provider, observation, model="fixture-model", messages=HISTORY)
        await observation.flush()
    assert observation.error_count == 1


@pytest.mark.asyncio
async def test_pending_queue_is_bounded_and_keeps_arrival_order():
    transport = Transport([reply()], mode="observe")
    transport.release.clear()
    async with clients(transport) as (provider, watcher):
        _, exchange = await fetch(provider, {"model": "fixture-model", "messages": HISTORY})
        observation = Observation(watcher, "conversation")
        for _ in range(33):
            observation.enqueue(exchange)
        assert observation.errors == ["ObservationQueueFull"]
        transport.release.set()
        await observation.flush()
    assert len(transport.watcher_requests) == 32


def test_empty_identity_rejected():
    with pytest.raises(ValueError, match="conversation ID"):
        Observation(None, "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,decision,mutation,count",
    [
        ("enforce", "allow", None, 2),
        ("enforce", "deny", None, 2),
        ("enforce", "escalate", None, 2),
        ("observe", "deny", None, 2),
        ("paused", "allow", None, 0),
        ("enforce", "allow", "failure-allow", 0),
    ],
)
async def test_advisory_queue_respects_server_policy_without_mode_override(mode, decision, mutation, count):
    transport = Transport(mode=mode, decision=decision, mutation=mutation)
    async with clients(transport) as (provider, watcher):
        observation = Observation(watcher, "advisory")
        response = await complete(provider, observation, model="fixture-model", messages=HISTORY)
        await observation.flush()
    assert response is not None
    assert observation.errors == [] and len(observation.judgments) == count
    assert transport.watcher_requests[0].get("settings_overrides") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["missing", "wrong-id", "missing-id", "duplicate", "reverse"])
async def test_advisory_ids_are_complete_unique_and_order_independent(mutation):
    transport = Transport(mode="observe", mutation=mutation)
    async with clients(transport) as (provider, watcher):
        observation = Observation(watcher, "advisory")
        response = await complete(provider, observation, model="fixture-model", messages=HISTORY)
        await observation.flush()
    assert response is not None
    if mutation == "reverse":
        assert observation.errors == [] and len(observation.judgments) == 2
    else:
        assert observation.error_count == 1 and observation.judgments == []
