"""Amp SDK executes and parses an isolated CLI process; no real Amp model runs."""

import asyncio
import json
from pathlib import Path

import httpx
from watcher_amp.integration import run_amp

from watcher_sdk import AsyncWatcherClient


def test_native_sdk_subprocess_stream(tmp_path, monkeypatch):
    records = json.loads((Path(__file__).parent / "fixtures/fixture.json").read_text())
    for record in records:
        record["session_id"] = "amp-native-fixture"
    records.append(
        {
            "type": "result",
            "subtype": "success",
            "session_id": "amp-native-fixture",
            "is_error": False,
            "result": "finished",
            "duration_ms": 1,
            "num_turns": 1,
        }
    )
    executable = tmp_path / "amp-fixture.js"
    executable.write_text(
        "process.stdin.resume(); process.stdin.on('end', () => {"
        + "for(const row of "
        + json.dumps(records)
        + ") console.log(JSON.stringify(row)); });"
    )
    monkeypatch.setenv("AMP_CLI_PATH", str(executable))
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        outcomes = [
            {
                "tool_use_id": item["tool_use_id"],
                "decision": "deferred",
                "judged_decision": "allow",
                "enforcement_mode": "observe",
                "decision_source": "rule",
                "latency_ms": 1,
                "verdict": {"summary": "fixture"},
            }
            for item in body["input"]
        ]
        return httpx.Response(200, json=outcomes)

    async def exercise():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://watcher.test", transport=httpx.MockTransport(respond))
        ) as client:
            await run_amp("Run two safe commands", str(tmp_path), client)

    asyncio.run(exercise())
    assert requests[-1]["external_ids"] == {"other": "amp:amp-native-fixture"}
    assert "finished" in str(requests[-1]["messages"][-1]["content"])
    assert [i["tool_use_id"] for request in requests for i in request["input"]] == ["call-a", "call-b"]
