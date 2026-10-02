"""Offline native-contract fixtures plus real public SDK transport serialization."""

import asyncio
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from watcher_continue.integration import PREFIX, convert, run_export, send

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
    with pytest.raises((KeyError, ValueError)):
        asyncio.run(run_export({}))


def test_empty_session_id_is_rejected():
    with pytest.raises(ValueError, match="session ID"):
        asyncio.run(send(None, "", []))


def test_malformed_export_is_rejected_without_leaking_content():
    result = subprocess.run(
        [sys.executable, "-m", "watcher_continue.integration"],
        input="SECRET invalid JSON",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert "SECRET" not in result.stderr
    assert "not confirmed recorded" in result.stderr


def test_duplicate_native_calls_are_rejected():
    with pytest.raises(ValueError, match="Conflicting"):
        convert(FIXTURE[:2] + [FIXTURE[1]] + FIXTURE[2:])


def test_missing_call_is_not_linked_by_name():
    with pytest.raises(ValueError, match="Missing or duplicate"):
        convert([{"message": {"role": "tool", "toolCallId": "missing", "content": "output"}, "contextItems": []}])


def test_incomplete_tool_state_is_not_fabricated():
    rows = deepcopy(FIXTURE)
    rows[1]["toolCallStates"][0]["status"] = "calling"
    with pytest.raises(ValueError, match="incomplete"):
        convert(rows)


def test_context_items_are_preserved_in_native_rendering():
    rows = deepcopy(FIXTURE)
    rows[0]["contextItems"] = [{"name": "fixture", "content": "exact context"}]
    assert convert(rows)[0]["content"][0]["text"].startswith('<context name="fixture">\nexact context\n</context>\n\n')


def test_unknown_export_version_is_rejected():
    with pytest.raises(ValueError, match="version"):
        asyncio.run(run_export({"version": 2}))


def test_compaction_and_attachments_require_explicit_support():
    rows = deepcopy(FIXTURE)
    rows[0]["conversationSummary"] = "compacted"
    with pytest.raises(ValueError, match="Compacted"):
        convert(rows)
    rows = deepcopy(FIXTURE)
    rows[0]["message"]["content"] = [{"type": "imageUrl", "imageUrl": {"url": "fixture"}}]
    with pytest.raises(ValueError, match="text"):
        convert(rows)
