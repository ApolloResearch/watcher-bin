"""Offline native-contract fixtures plus real public SDK transport serialization."""

import asyncio
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from watcher_mistral_vibe.integration import PREFIX, convert, run_hook, send

from watcher_sdk import AsyncWatcherClient

FIXTURE = json.loads((Path(__file__).parent / "fixtures/fixture.json").read_text())


def test_native_transcript_preserves_parallel_tools_results_and_final_tail():
    messages = convert(FIXTURE)
    calls = [call for message in messages for call in message.get("tool_calls", [])]
    results = [message["tool_call_id"] for message in messages if message["role"] == "tool"]
    assert [call["id"] for call in calls] == ["call-a", "call-b"]
    assert results == ["call-b", "call-a"]
    assert calls[0]["arguments"] == {"command": "pwd"}
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
        body = json.loads(request.content)
        outcomes = [
            {
                "tool_use_id": item["tool_use_id"],
                "decision": "deferred",
                "judged_decision": "allow",
                "enforcement_mode": "observe",
                "decision_source": "rule",
                "latency_ms": 1,
                "verdict": {
                    "summary": "fixture",
                    "explanation": "fixture",
                    "confidence": 1,
                    "score": None,
                    "risk_level": "low",
                },
            }
            for item in body["input"]
        ]
        return httpx.Response(200, json=outcomes)

    async def exercise():
        transport = httpx.MockTransport(respond)
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://watcher.test", transport=transport)
        ) as client:
            await send(client, "native-session", convert(FIXTURE))

    asyncio.run(exercise())
    body = json.loads(requests[-1].content)
    assert body["input"] == []
    assert body["external_ids"] == {"other": PREFIX + "native-session"}
    assert body["messages"] == convert(FIXTURE)
    assert "require_recording" not in requests[-1].url.params
    assert all(json.loads(request.content)["mode"] == "triage_only" for request in requests[:-1])


def test_incomplete_response_is_not_reported_as_success():
    async def exercise():
        transport = httpx.MockTransport(lambda _: httpx.Response(200, json=[]))
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://watcher.test", transport=transport)
        ) as client:
            with pytest.raises(ValueError):
                await send(client, "native-session", convert(FIXTURE))

    asyncio.run(exercise())


def test_missing_native_path_is_explicit():
    with pytest.raises(ValueError, match="transcript path"):
        asyncio.run(run_hook({"transcript_path": None, "session_id": "s"}))


def test_empty_session_id_is_rejected():
    with pytest.raises(ValueError, match="session ID"):
        asyncio.run(send(None, "", []))


def test_malformed_hook_does_not_block_or_leak_content():
    result = subprocess.run(
        [sys.executable, "-m", "watcher_mistral_vibe.integration"],
        input="SECRET invalid JSON",
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout == "{}\n"
    assert "SECRET" not in result.stderr
    assert "not confirmed recorded" in result.stderr
