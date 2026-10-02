"""Regression coverage using the recording emitted by the contained native CLI."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path

import httpx
from watcher_qwen_code.integration import PREFIX, convert, send

from watcher_sdk import AsyncWatcherClient


def captured_records():
    return [
        json.loads(line)
        for line in (Path(__file__).parent / "fixtures/native-recording.jsonl").read_text().splitlines()
    ]


def test_captured_native_call_ids_results_and_assistant_tail():
    records = captured_records()
    before = deepcopy(records)
    messages = convert(records)
    calls = [call for message in messages for call in message.get("tool_calls", [])]
    results = [message for message in messages if message["role"] == "tool"]
    assert [call["id"] for call in calls] == ["call00001", "call00002"]
    assert [call["function"] for call in calls] == ["read_file", "read_file"]
    assert calls[0]["arguments"] == {"file_path": "/tmp/native-workspace/first.txt"}
    assert calls[1]["arguments"] == {"file_path": "/tmp/native-workspace/second.txt"}
    assert [message["tool_call_id"] for message in results] == ["call00001", "call00002"]
    assert "SDK50_NATIVE_FIRST_FILE" in json.dumps(results[0]["content"])
    assert "SDK50_NATIVE_SECOND_FILE" in json.dumps(results[1]["content"])
    assert messages[-1]["role"] == "assistant"
    assert "sdk50 native completed" in json.dumps(messages[-1]["content"])
    assert records == before


def test_captured_recording_reaches_public_sdk_with_monitoring_and_final_flush():
    received = []

    def respond(request):
        body = json.loads(request.content)
        received.append(body)
        assert "require_recording" not in request.url.params
        outcomes = [
            {
                "tool_use_id": item["tool_use_id"],
                "decision": "deferred",
                "judged_decision": "allow",
                "enforcement_mode": "observe",
                "decision_source": "rule",
                "verdict": {},
                "latency_ms": 1,
            }
            for item in body["input"]
        ]
        return httpx.Response(200, json=outcomes)

    async def exercise():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://watcher.invalid", transport=httpx.MockTransport(respond))
        ) as client:
            await send(client, "captured-native-session", convert(captured_records()))

    asyncio.run(exercise())
    assert [item["tool_use_id"] for body in received for item in body["input"]] == ["call00001", "call00002"]
    assert received[-1]["input"] == []
    assert received[-1]["external_ids"] == {"other": PREFIX + "captured-native-session"}
    assert received[-1]["messages"][-1]["role"] == "assistant"
    assert "sdk50 native completed" in json.dumps(received[-1]["messages"][-1]["content"])
