"""Historical assessments inherit server policy and never claim to block past actions."""

import asyncio
import json

import httpx
import pytest
from watcher_mistral_vibe.monitoring import observe

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
def test_retrospective_policy_is_inherited(tmp_path, mode, decision, judged, source):
    already_finished = tmp_path / "completed-action"
    already_finished.write_text("native action already happened")
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "native-call", "function": "write", "arguments": {}}],
        },
        {"role": "tool", "tool_call_id": "native-call", "content": "finished"},
        {"role": "assistant", "content": "final answer"},
    ]
    requests = []

    def respond(request):
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
            await observe(client, "native-session", messages)

    asyncio.run(run())
    assert already_finished.read_text() == "native action already happened"
    assert any(request["input"] == [] and request["messages"] == messages for request in requests)
    assert sum(len(request["input"]) for request in requests) == 1
