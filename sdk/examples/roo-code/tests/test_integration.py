"""Offline native-contract fixtures plus real public SDK transport serialization."""

import asyncio
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from watcher_roo_code_bridge.integration import PREFIX, convert, run_hook, send

from watcher_sdk import AsyncWatcherClient, WatcherError

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "fixture.json").read_text())


def test_limited_contract_does_not_invent_tool_identities():
    messages = convert(FIXTURE)
    assert all(not message.get("tool_calls") for message in messages)
    assert "finished" in str(messages[-1]["content"])


def test_does_not_mutate_input():
    original = deepcopy(FIXTURE)
    convert(FIXTURE)
    assert original == FIXTURE


def test_complete_snapshots_include_incremental_final_tail():
    early = convert(FIXTURE[:-1])
    final = convert(FIXTURE)
    assert final[: len(early)] == early
    assert len(final) == len(early) + 1
    assert convert(FIXTURE) == final


def test_sdk_transport_preserves_native_identity():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=[])

    async def exercise():
        transport = httpx.MockTransport(respond)
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://watcher.test", transport=transport)
        ) as client:
            await send(client, "native-session", convert(FIXTURE))

    asyncio.run(exercise())
    body = json.loads(requests[0].content)
    assert body["input"] == []
    assert body["external_ids"] == {"other": PREFIX + "native-session"}
    assert body["messages"] == convert(FIXTURE)
    assert "require_recording" not in requests[0].url.params


def test_incomplete_response_is_not_reported_as_success():
    async def exercise():
        transport = httpx.MockTransport(lambda _: httpx.Response(503, json={"error": {"message": "unavailable"}}))
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://watcher.test", transport=transport)
        ) as client:
            with pytest.raises(WatcherError):
                await send(client, "native-session", convert(FIXTURE))

    asyncio.run(exercise())


def test_missing_native_path_is_explicit():
    with pytest.raises((KeyError, ValueError)):
        asyncio.run(run_hook({}))


def test_empty_session_id_is_rejected():
    with pytest.raises(ValueError, match="session ID"):
        asyncio.run(send(None, "", []))


def test_malformed_hook_does_not_block_or_leak_content():
    result = subprocess.run(
        [sys.executable, "-m", "watcher_roo_code_bridge.integration"],
        input="SECRET invalid JSON",
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout == "{}\n"
    assert "SECRET" not in result.stderr
    assert "not confirmed recorded" in result.stderr
