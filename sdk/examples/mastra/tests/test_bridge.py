"""Exercise real Mastra output across the Python SDK bridge, with Watcher mocked."""

import asyncio
import json
import os
import subprocess
from pathlib import Path

import httpx
import pytest
from watcher_mastra_bridge.bridge import observe_snapshots

from watcher_sdk import AsyncWatcherClient


@pytest.mark.asyncio
async def test_native_mastra_snapshots_reach_public_sdk(tmp_path):
    completed = await asyncio.to_thread(
        subprocess.run,
        ["node", str(Path(__file__).parent / "fixtures" / "observation.mjs")],
        cwd=Path(__file__).parent,
        env={**os.environ, "SNAPSHOT_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    captured = []

    def handler(request):
        payload = json.loads(request.content)
        captured.append(payload)
        assert "require_recording" not in request.url.params
        outcomes = [
            {
                "decision": "deferred",
                "judged_decision": "deny",
                "enforcement_mode": "observe",
                "decision_source": "rule",
                "verdict": {},
                "latency_ms": 1,
                "tool_use_id": item["tool_use_id"],
            }
            for item in payload["input"]
        ]
        return httpx.Response(200, json=outcomes)

    async with AsyncWatcherClient(
        "https://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as watcher:
        queue = await observe_snapshots(watcher, [tmp_path / "0.json", tmp_path / "1.json"], "mastra-session")
    assert queue.errors == []
    assert captured[0]["input"] == [
        {"tool_use_id": "call-a", "tool_name": "weather", "tool_input": {"city": "Paris"}},
        {"tool_use_id": "call-b", "tool_name": "weather", "tool_input": {"city": "Tokyo"}},
    ]
    assert captured[-1]["input"] == []
    assert captured[-1]["messages"][-1]["content"][0]["text"] == "Finished."
    assert captured[-1]["external_ids"] == {"other": "mastra-session"}
