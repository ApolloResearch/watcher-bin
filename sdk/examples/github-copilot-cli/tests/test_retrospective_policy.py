"""Historical assessments inherit server policy and never claim to block past actions."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from pydantic import JsonValue
from watcher_github_copilot_cli.monitoring import assess

from watcher_sdk import AsyncWatcherClient


@pytest.mark.parametrize(
    "mode,decision,judged,source",
    [
        ("enforce", "allow", "allow", "rule"),
        ("enforce", "deny", "deny", "triage"),
        ("enforce", "escalate", "escalate", "triage"),
        ("observe", "deferred", "deny", "triage"),
        ("paused", "deferred", None, "bypass"),
        ("enforce", "allow", "allow", "grading_error"),
    ],
)
def test_retrospective_policy_is_inherited(
    tmp_path: Path, mode: str, decision: str, judged: str | None, source: str
) -> None:
    already_finished = tmp_path / "completed-action"
    already_finished.write_text("native action already happened")
    messages: list[dict[str, JsonValue]] = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "native-call", "function": "write", "arguments": {}}],
        },
        {"role": "tool", "tool_call_id": "native-call", "content": "finished"},
        {"role": "assistant", "content": "final answer"},
    ]
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        assert "settings_overrides" not in body
        outcomes = []
        for call in body["input"]:
            result = {
                "tool_use_id": call["tool_use_id"],
                "decision": decision,
                "judged_decision": judged,
                "enforcement_mode": mode,
                "decision_source": source,
                "verdict": {},
                "latency_ms": 1,
            }
            if source == "grading_error":
                result["grading_error"] = {"code": "timeout", "message": "fixture timeout"}
            outcomes.append(result)
        return httpx.Response(200, json=outcomes)

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await assess(client, "native-session", messages)

    asyncio.run(run())
    assert already_finished.read_text() == "native action already happened"
    assert len(requests) == 1 and len(requests[0]["input"]) == 1
    assert requests[0]["messages"] == messages[:1]
