"""Real provider tool loops must wait for Watcher before performing file writes."""

import asyncio
import json

import httpx
import httpx2
import pytest
from anthropic import AsyncAnthropic
from demo.app import run_demo

from watcher_sdk import (
    AsyncWatcherClient,
    WatcherAPIError,
    WatcherTimeoutError,
    WatcherValidationError,
)


class Scenario:
    """Exercise an actual provider client and public SDK with controllable HTTP replies."""

    def __init__(self, output_file, *, decision="allow", posture="enforce", fault=None, held=False):
        self.output_file = output_file
        self.decision = decision
        self.posture = posture
        self.fault = fault
        self.provider_requests = []
        self.watcher_requests = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        if not held:
            self.release.set()

    async def provider_reply(self, request):
        self.provider_requests.append(json.loads(request.content))
        is_final = len(self.provider_requests) > 1
        content = (
            [{"type": "text", "text": "Finished"}]
            if is_final
            else [
                {"type": "tool_use", "id": f"note-{i}", "name": "append_note", "input": {"text": text}}
                for i, text in enumerate(["first", "second"], 1)
            ]
        )
        return httpx2.Response(
            200,
            json={
                "id": "message-1",
                "type": "message",
                "role": "assistant",
                "model": "fixture-model",
                "content": content,
                "stop_reason": "end_turn" if is_final else "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    async def watcher_reply(self, request):
        body = json.loads(request.content)
        self.watcher_requests.append(body)
        assert body["format"] == "raw"
        pending = {
            ("content", i): {"tool_use_id": item["id"]}
            for i, item in enumerate(body["response_body"]["content"])
            if item["type"] == "tool_use"
        }
        assert body["external_ids"] == {"other": "mode-example"}
        if pending:
            self.entered.set()
            await self.release.wait()
        if self.fault == "timeout":
            raise httpx.ReadTimeout("fixture timeout", request=request)
        if self.fault in ("locked", "unavailable"):
            return httpx.Response(
                422 if self.fault == "locked" else 503,
                json={"detail": [{"loc": ["body"], "msg": "fixture refusal", "type": "value_error"}]},
            )
        outcomes = [
            {
                "tool_use_id": item["tool_use_id"],
                "decision": self.decision,
                "judged_decision": "deny"
                if self.posture == "observe"
                else ("allow" if self.decision == "deferred" else self.decision),
                "decision_source": "rule",
                "enforcement_mode": self.posture,
                "verdict": {},
                "latency_ms": 0,
            }
            for path, item in pending.items()
        ]
        if outcomes:
            if self.fault == "missing":
                outcomes.pop()
            elif self.fault == "wrong-id":
                outcomes[0]["tool_use_id"] = "unrelated-call"
            elif self.fault == "item-error":
                outcomes[0] = {"tool_use_id": outcomes[0]["tool_use_id"], "status_code": 503, "detail": "fixture"}
            elif self.fault == "mixed-deny":
                outcomes[-1].update(decision="deny", judged_decision="deny")
            elif self.fault == "no-judgment":
                outcomes[0].pop("judged_decision")
            elif self.fault == "grading-error":
                outcomes[0].update(decision_source="grading_error", judged_decision=None)
        if self.fault == "final-failure" and not pending:
            return httpx.Response(503, json={"detail": "fixture unavailable"})
        return httpx.Response(200, json=outcomes)

    async def run(self, enforcement="enforce"):
        async with (
            AsyncAnthropic(
                api_key="fixture",
                max_retries=0,
                http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(self.provider_reply)),
            ) as provider,
            AsyncWatcherClient(
                "https://watcher.test",
                httpx_client=httpx.AsyncClient(
                    base_url="https://watcher.test", transport=httpx.MockTransport(self.watcher_reply)
                ),
            ) as watcher,
        ):
            return await run_demo(
                provider,
                watcher,
                self.output_file,
                session_id="mode-example",
                model="fixture-model",
                enforcement=enforcement,
            )


@pytest.mark.asyncio
async def test_tool_files_wait_for_allowed_recorded_decisions(tmp_path):
    scenario = Scenario(tmp_path / "notes.txt", held=True)
    task = asyncio.create_task(scenario.run())
    try:
        await asyncio.wait_for(scenario.entered.wait(), timeout=5)
        assert not task.done()
        assert not scenario.output_file.exists()
        scenario.release.set()
        await asyncio.wait_for(task, timeout=5)
    finally:
        scenario.release.set()
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    assert scenario.output_file.read_text() == "first\nsecond\n"
    pending, final = scenario.watcher_requests
    assert pending["settings_overrides"] == {"enforcement": {"mode": "enforce"}}
    assert [item["id"] for item in pending["response_body"]["content"]] == ["note-1", "note-2"]
    results = final["request_body"]["messages"][-1]["content"]
    assert [item["tool_use_id"] for item in results] == ["note-1", "note-2"]
    assert all(item["content"] == "Note appended." for item in results)
    assert "Finished" in json.dumps(final["response_body"])
    assert len(scenario.provider_requests) == 2


@pytest.mark.asyncio
async def test_observation_keeps_tools_despite_underlying_denial(tmp_path):
    scenario = Scenario(tmp_path / "notes.txt", decision="deferred", posture="observe")
    await scenario.run("observe")
    assert scenario.output_file.read_text() == "first\nsecond\n"
    assert all(
        request["settings_overrides"] == {"enforcement": {"mode": "observe"}} for request in scenario.watcher_requests
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["deny", "escalate", "deferred"])
async def test_non_allow_decisions_never_open_the_tool_file(tmp_path, decision):
    scenario = Scenario(tmp_path / "notes.txt", decision=decision)
    with pytest.raises(PermissionError):
        await scenario.run()
    assert not scenario.output_file.exists()
    assert len(scenario.provider_requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("posture", ["observe", "paused"])
async def test_non_enforcing_posture_cannot_masquerade_as_allow(tmp_path, posture):
    scenario = Scenario(tmp_path / "notes.txt", posture=posture)
    with pytest.raises(RuntimeError, match="requested enforcement mode"):
        await scenario.run()
    assert not scenario.output_file.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault,error",
    [
        ("missing", RuntimeError),
        ("wrong-id", RuntimeError),
        ("item-error", RuntimeError),
        ("timeout", WatcherTimeoutError),
        ("locked", WatcherValidationError),
        ("unavailable", WatcherAPIError),
        ("mixed-deny", PermissionError),
        ("no-judgment", PermissionError),
        ("grading-error", PermissionError),
    ],
)
async def test_decision_or_recording_failure_prevents_actual_execution(tmp_path, fault, error):
    scenario = Scenario(tmp_path / "notes.txt", fault=fault)
    with pytest.raises(error):
        await scenario.run()
    assert not scenario.output_file.exists()
    assert len(scenario.provider_requests) == 1


@pytest.mark.asyncio
async def test_final_recording_failure_does_not_repeat_completed_tools(tmp_path):
    scenario = Scenario(tmp_path / "notes.txt", fault="final-failure")
    with pytest.raises(WatcherAPIError):
        await scenario.run()
    assert scenario.output_file.read_text() == "first\nsecond\n"
    assert len(scenario.provider_requests) == 2
    assert len(scenario.watcher_requests) == 2
