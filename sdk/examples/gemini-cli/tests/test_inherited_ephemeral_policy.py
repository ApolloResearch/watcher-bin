"""Valid inherited observation and grading-failure policy preserve native dispatch."""

import asyncio
import json

import httpx
import pytest
from watcher_gemini_cli.enforcement import apply_policy

from watcher_sdk import AsyncWatcherClient


@pytest.mark.parametrize("mode", ["observe", "paused", "grading-failure-allow"])
def test_valid_inherited_ephemeral_policy(tmp_path, monkeypatch, mode):
    monkeypatch.setenv("WATCHER_EPHEMERAL_PRE_TOOL", "1")
    marker = tmp_path / "effect"

    def respond(request):
        body = json.loads(request.content)
        assert body["ephemeral"] is True and "settings_overrides" not in body
        result = {
            "tool_use_id": None,
            "decision": "allow" if mode == "grading-failure-allow" else "deferred",
            "judged_decision": "allow" if mode == "grading-failure-allow" else None if mode == "paused" else "deny",
            "enforcement_mode": "enforce" if mode == "grading-failure-allow" else mode,
            "decision_source": "grading_error"
            if mode == "grading-failure-allow"
            else "bypass"
            if mode == "paused"
            else "rule",
            "verdict": {},
            "latency_ms": 1,
        }
        if mode == "grading-failure-allow":
            result["grading_error"] = {"code": "timeout", "message": "fixture timeout"}
        return httpx.Response(200, json=result)

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, "native-session", [], {"function": "read", "arguments": {}})
            marker.write_text("executed")

    asyncio.run(run())
    assert marker.read_text() == "executed"
