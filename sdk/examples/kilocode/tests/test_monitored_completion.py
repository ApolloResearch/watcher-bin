"""A monitored completion uploads its transcript without requesting another grade."""

import asyncio
import json

import httpx
import pytest
from watcher_kilocode_bridge.integration import send

from watcher_sdk import AsyncWatcherClient


def test_monitored_completion_does_not_regrade_prior_calls():
    messages = [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "prior", "function": "read", "arguments": {}}]},
        {"role": "tool", "tool_call_id": "prior", "content": "result"},
        {"role": "assistant", "content": "finished"},
    ]
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["input"] == []
        assert body["messages"] == messages
        assert "settings_overrides" not in body
        return httpx.Response(200, json=[])

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await send(client, "native-session", messages, record_only=True)

    asyncio.run(run())
    assert len(requests) == 1


def test_monitored_completion_rejects_unexpected_outcomes():
    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(
                base_url="http://fixture", transport=httpx.MockTransport(lambda _: httpx.Response(200, json={}))
            )
        ) as client:
            with pytest.raises((ValueError, KeyError, TypeError)):
                await send(client, "native-session", [], record_only=True)

    asyncio.run(run())
