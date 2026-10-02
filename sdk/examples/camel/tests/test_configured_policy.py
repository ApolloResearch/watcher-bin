"""Applied policy and human approval through the installed framework's native runner."""

import asyncio
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from typing import Any

import httpx
import pytest
from demo.enforce import run_conversation
from watcher_camel.monitoring import ApprovalRequired, Monitor, ToolBlocked

from watcher_sdk import AsyncWatcherClient


def _audit_trajectory(
    calls: list[dict[str, Any]], records: dict[str, dict[str, Any]], session_id: str
) -> dict[str, Any]:
    """Model public stored decision detail independently of display categories."""
    decisions = {}
    for call in calls:
        report = records.get(call["tool_use_id"], {})
        decisions[call["tool_use_id"]] = {
            "tool_use_id": call["tool_use_id"],
            "tool_name": call["tool_name"],
            "raw_tool_call": {"tool_name": call["tool_name"], "tool_input": deepcopy(call["tool_input"])},
            "policy_decision": "escalate",
            "applied_decision": "escalate",
            "judged_decision": "escalate",
            "decision_source": "policy_gateway",
            "grades": [],
            "tool_status": report.get("tool_status", "pending"),
            "human_decision": report.get("human_decision"),
            "human_decided_at": report.get("human_decided_at"),
            "tool_call_id": "8a53c1d7-c1c6-4cfe-a7c7-2a3c6d6a26e4",
            "tool_call_decision_id": "3a64323f-e85b-45b7-a356-1847b8d0ee63",
            "tool_call_created_at": "2026-09-25T00:00:00Z",
            "created_at": "2026-09-25T00:00:00Z",
            "updated_at": "2026-09-25T00:00:00Z",
        }
    return {
        "session_id": session_id,
        "trajectory_id": "trajectory",
        "grades": [],
        "metadata": {},
        "source": "fixture",
        "created_at": "2026-09-25T00:00:00Z",
        "tool_call_decisions": decisions,
        "messages": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": call["tool_use_id"],
                        "type": "function",
                        "function": call["tool_name"],
                        "arguments": deepcopy(call["tool_input"]),
                    }
                    for call in calls
                ],
            }
        ],
    }


@asynccontextmanager
async def configured_client(
    mode="enforce",
    decision="allow",
    *,
    grading_failure=False,
    audit_reports=None,
    report_failure=False,
    report_noop=False,
):
    """Return the actual SDK over a local transport with one configured server policy."""
    requests = []
    human_choices = {}
    human_records = {}

    async def respond(request):
        body = json.loads(request.content) if request.content else {}
        session_id = "c1f7b8be-166e-4b12-81e9-d1f3d87e4725"
        if request.url.path == "/v1/sessions/search":
            return httpx.Response(
                200,
                json={
                    "sessions": [
                        {
                            "session_id": session_id,
                            "agent_platform": "other",
                            "trajectory_count": 1,
                            "latest_trajectory_id": "trajectory",
                            "message_count": 2,
                            "started_at": "2026-09-25T00:00:00Z",
                            "ended_at": "2026-09-25T00:00:00Z",
                        }
                    ],
                    "total": 1,
                    "limit": 2,
                    "offset": 0,
                },
            )
        if request.url.path == f"/v1/sessions/{session_id}/trajectories/trajectory":
            assert request.url.params["view"] == "extended"
            calls = [item["input"] for item in requests if item["input"] is not None]
            return httpx.Response(200, json=_audit_trajectory(calls, human_records, session_id))
        if request.url.path == "/v1/tool-calls/search":
            calls = [item["input"] for item in requests if item["input"] is not None]
            return httpx.Response(
                200,
                json={
                    "tool_calls": [
                        {
                            "tool_call_id": "8a53c1d7-c1c6-4cfe-a7c7-2a3c6d6a26e4",
                            "session_id": session_id,
                            "occurred_at": "2026-09-25T00:00:00Z",
                            "tool_use_id": call["tool_use_id"],
                            "message_ref": "m1",
                            "tool_name": call["tool_name"],
                            "applied_decision": "escalate",
                            "decision_category": human_choices.get(call["tool_use_id"]),
                        }
                        for call in calls
                    ],
                    "total": len(calls),
                    "limit": 100,
                    "offset": 0,
                },
            )
        if request.url.path == "/v1/tool-call-decisions/batch":
            assert body["session_id"] == session_id
            record = body["decisions"][0]
            assert (
                record["policy_decision"] == record["applied_decision"] == record["decision_source"] == "not_evaluated"
            )
            assert record["human_decision"] in {"allow", "deny"}
            assert record["tool_status"] == ("pending" if record["human_decision"] == "allow" else "blocked")
            assert record["human_decided_at"]
            if audit_reports is not None:
                audit_reports.append(record)
            if not report_failure and not report_noop:
                human_records[record["tool_use_id"]] = deepcopy(record)
                human_choices[record["tool_use_id"]] = (
                    "human_allowed" if record["human_decision"] == "allow" else "human_denied"
                )
            return httpx.Response(
                200,
                json={
                    "synced_count": 0 if report_failure else 1,
                    "synced_tool_use_ids": [] if report_failure else [record["tool_use_id"]],
                    "failed_tool_use_ids": [record["tool_use_id"]] if report_failure else [],
                    "failed_tool_call_grade_ids": [],
                },
            )
        assert request.url.path == "/v1/hooks/pre-tool-use"
        requests.append(body)
        assert "require_recording" not in request.url.params
        if body["input"] is None:
            return httpx.Response(200, json=[])
        applied = decision if mode == "enforce" else "deferred"
        response = {
            "tool_use_id": body["input"]["tool_use_id"],
            "decision": applied,
            "judged_decision": None if mode == "paused" else decision,
            "enforcement_mode": mode,
            "decision_source": "bypass" if mode == "paused" else "grading_error" if grading_failure else "rule",
            "verdict": {"summary": "Fixture decision", "explanation": "Fixture policy"},
            "latency_ms": 1,
        }
        if grading_failure:
            response["grading_error"] = {"code": "timeout", "message": "Fixture grader timeout"}
        return httpx.Response(200, json=response)

    async with (
        httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(respond)) as transport,
        AsyncWatcherClient(
            "https://watcher.invalid",
            httpx_client=transport,
            manage_external_httpx_client_lifecycle=False,
            max_retries=0,
        ) as client,
    ):
        yield client, requests


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["observe", "paused"])
async def test_same_native_hook_defers_to_normal_framework_execution(mode):
    effects = []
    async with configured_client(mode, "deny") as (client, requests):
        await run_conversation(Monitor(client, "configured"), lambda value: effects.append(value) or str(value * 2))
    assert sorted(effects) == [2, 3]
    assert all("settings_overrides" not in body for body in requests)
    assert requests[-1]["input"] is None
    assert requests[-1]["messages"][-1]["content"] == "4 and 6"


@pytest.mark.asyncio
async def test_organization_fail_open_is_an_applied_allow_not_a_transport_failure():
    effects = []
    async with configured_client(grading_failure=True) as (client, _requests):
        await run_conversation(Monitor(client, "fail-open"), lambda value: effects.append(value) or str(value * 2))
    assert sorted(effects) == [2, 3]


@pytest.mark.asyncio
async def test_unattended_escalation_never_executes():
    effects = []
    async with configured_client(decision="escalate") as (client, _requests):
        with pytest.raises(ApprovalRequired):
            await run_conversation(Monitor(client, "unattended"), lambda value: effects.append(value) or str(value * 2))
    assert effects == []


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [True, False])
async def test_native_runner_waits_for_application_approval_then_resumes_or_refuses(approved):
    entered, released = asyncio.Event(), asyncio.Event()
    effects, approvals, reports = [], [], []

    async def decide(*, tool_use_id, tool_name, tool_input, outcome):
        assert tool_name == "double"
        assert outcome.tool_use_id == tool_use_id
        assert outcome.decision == "escalate"
        approvals.append(tool_use_id)
        # The approval view must not be able to rewrite the native pending call.
        tool_input["value"] = 999
        entered.set()
        await released.wait()
        return approved

    def execute(value):
        assert any(
            record["raw_tool_call"]["tool_input"] == {"value": value} and record["human_decision"] == "allow"
            for record in reports
        )
        effects.append(value)
        return str(value * 2)

    async with configured_client(decision="escalate", audit_reports=reports) as (client, _requests):
        monitor = Monitor(client, "human", approval_callback=decide)
        task = asyncio.create_task(run_conversation(monitor, execute))
        try:
            await asyncio.wait_for(entered.wait(), 20)
            assert effects == []
            assert not task.done()
        finally:
            released.set()
        if approved:
            await asyncio.wait_for(task, 30)
        else:
            with pytest.raises(ToolBlocked):
                await asyncio.wait_for(task, 30)
    assert approvals
    assert reports
    assert {record["human_decision"] for record in reports} == ({"allow"} if approved else {"deny"})
    assert sorted(effects) == ([2, 3] if approved else [])


@pytest.mark.asyncio
async def test_truthy_application_result_is_not_human_approval():
    async def decide(**kwargs):
        return "yes"

    effects = []
    async with configured_client(decision="escalate") as (client, _requests):
        with pytest.raises(ToolBlocked):
            await run_conversation(
                Monitor(client, "literal-approval", approval_callback=decide),
                lambda value: effects.append(value) or str(value * 2),
            )
    assert effects == []


@pytest.mark.asyncio
async def test_explicit_observation_override_uses_the_same_native_callback():
    effects = []
    async with configured_client("observe", "deny") as (client, requests):
        await run_conversation(
            Monitor(client, "override", enforcement="observe"),
            lambda value: effects.append(value) or str(value * 2),
        )
    assert sorted(effects) == [2, 3]
    assert all(
        body["settings_overrides"] == {"enforcement": {"mode": "observe"}}
        for body in requests
        if body["input"] is not None
    )


@pytest.mark.asyncio
async def test_human_approval_is_not_execution_permission_until_watcher_accepts_the_report():
    async def approve(**kwargs):
        return True

    effects, reports = [], []
    async with configured_client(decision="escalate", audit_reports=reports, report_failure=True) as (
        client,
        _requests,
    ):
        with pytest.raises(ToolBlocked, match="acknowledge the human decision"):
            await run_conversation(
                Monitor(client, "audit-failure", approval_callback=approve),
                lambda value: effects.append(value) or str(value * 2),
            )
    assert reports and effects == []


@pytest.mark.asyncio
async def test_acknowledged_noop_does_not_release_a_human_approved_tool():
    async def approve(**kwargs):
        return True

    effects = []
    async with configured_client(decision="escalate", report_noop=True) as (client, _requests):
        with pytest.raises(ToolBlocked, match="expose the recorded human decision"):
            await run_conversation(
                Monitor(client, "scrub-race", approval_callback=approve),
                lambda value: effects.append(value) or str(value * 2),
            )
    assert effects == []
