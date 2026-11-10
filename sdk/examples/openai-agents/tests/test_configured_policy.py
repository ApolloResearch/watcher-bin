"""Applied policy and human approval through the installed framework's native runner."""

import asyncio
import json
from contextlib import asynccontextmanager, suppress
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from agents import function_tool
from agents.exceptions import UserError
from demo.enforce import run_conversation
from watcher_openai_agents.adapter import messages_for_watcher
from watcher_openai_agents.monitoring import ApprovalRequired, Monitor, ToolBlocked
from watcher_openai_agents.native import execute_tool

from watcher_sdk import AsyncWatcherClient


def _audit_trajectory(
    calls: list[dict[str, Any]],
    records: dict[str, dict[str, Any]],
    session_id: str,
    evaluation: dict[str, Any],
    stored_status: str = "pending",
) -> dict[str, Any]:
    """Model public stored decision detail independently of display categories."""
    decisions = {}
    for call in calls:
        report = records.get(call["tool_use_id"], {})
        decisions[call["tool_use_id"]] = {
            "tool_use_id": call["tool_use_id"],
            "tool_name": call["tool_name"],
            "raw_tool_call": {"tool_name": call["tool_name"], "tool_input": deepcopy(call["tool_input"])},
            **evaluation,
            "grades": [],
            "tool_status": report.get("tool_status", stored_status),
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
    upload_gate=None,
    stored_status="pending",
):
    """Return the actual SDK over a local transport with one configured server policy.

    A decision upload waits on ``upload_gate.release`` after setting
    ``upload_gate.started``, when a gate is given. Each call's stored status is
    ``stored_status`` until an upload reports one.
    """
    requests = []
    human_choices = {}
    outcome_records = {}
    applied = decision if mode == "enforce" else "deferred"
    source = "bypass" if mode == "paused" else "grading_error" if grading_failure else "rule"
    # What Watcher records for every call, read back with the trajectory's decisions.
    evaluation = {
        "policy_decision": applied,
        "applied_decision": applied,
        "judged_decision": None if mode == "paused" else decision,
        "decision_source": source,
    }

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
            trajectory = _audit_trajectory(calls, outcome_records, session_id, evaluation, stored_status)
            return httpx.Response(200, json=trajectory)
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
                            "applied_decision": applied,
                            "is_flagged": applied in {"deny", "escalate"},
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
            if upload_gate is not None:
                # Hold the decision upload until the test releases it.
                upload_gate.started.set()
                await upload_gate.release.wait()
            assert body["session_id"] == session_id
            record = body["decisions"][0]
            assert (
                record["policy_decision"] == record["applied_decision"] == record["decision_source"] == "not_evaluated"
            )
            if "human_decision" in record:
                assert record["human_decision"] in {"allow", "deny"}
                assert record["tool_status"] == ("pending" if record["human_decision"] == "allow" else "blocked")
                assert record["human_decided_at"]
            else:
                # A refusal or cancellation reports only its execution status.
                assert record["tool_status"] in {"blocked", "cancelled"}
            if audit_reports is not None:
                audit_reports.append(record)
            if not report_failure and not report_noop:
                outcome_records[record["tool_use_id"]] = outcome_records.get(record["tool_use_id"], {}) | deepcopy(
                    record
                )
                if "human_decision" in record:
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
        response = {
            "tool_use_id": body["input"]["tool_use_id"],
            "decision": applied,
            "judged_decision": None if mode == "paused" else decision,
            "enforcement_mode": mode,
            "decision_source": source,
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
    async with configured_client(grading_failure=True) as (client, requests):
        monitor = Monitor(client, "fail-open")
        await run_conversation(monitor, lambda value: effects.append(value) or str(value * 2))
    assert sorted(effects) == [2, 3]
    # The calls ran, so neither result may be sent as failed.
    assert monitor.errors == {}
    assert all(message.get("error") is None for message in requests[-1]["messages"] if message["role"] == "tool")


def status_report(call_id, value, status):
    """The exact outcome-only upload for one double(value) call."""
    return {
        "tool_use_id": call_id,
        "tool_name": "double",
        "raw_tool_call": {"tool_name": "double", "tool_input": {"value": value}},
        "policy_decision": "not_evaluated",
        "applied_decision": "not_evaluated",
        "decision_source": "not_evaluated",
        "tool_status": status,
    }


async def finish_siblings(before):
    """Let parallel tool tasks a failed run left behind finish their reports before the client closes."""
    siblings = asyncio.all_tasks() - before - {asyncio.current_task()}
    if siblings:
        await asyncio.wait_for(asyncio.gather(*siblings, return_exceptions=True), 10)


def by_call(reports):
    return sorted(reports, key=lambda report: report["tool_use_id"])


@pytest.mark.asyncio
async def test_unattended_escalation_never_executes():
    effects, reports = [], []
    async with configured_client(decision="escalate", audit_reports=reports) as (client, _requests):
        before = asyncio.all_tasks()
        with pytest.raises(UserError) as error:
            await run_conversation(Monitor(client, "unattended"), lambda value: effects.append(value) or str(value * 2))
        await finish_siblings(before)
        assert isinstance(error.value.__cause__, ApprovalRequired)
        assert error.value.__cause__.__cause__ is None, "Reporting the refusal failed"
    assert effects == []
    assert by_call(reports) == [status_report("double-2", 2, "blocked"), status_report("double-3", 3, "blocked")]


@pytest.mark.asyncio
async def test_watcher_denial_is_reported_blocked_and_never_marked_as_a_tool_error():
    effects, reports = [], []
    async with configured_client(decision="deny", audit_reports=reports) as (client, _requests):
        monitor = Monitor(client, "denied")
        before = asyncio.all_tasks()
        with pytest.raises(UserError) as error:
            await run_conversation(monitor, lambda value: effects.append(value) or str(value * 2))
        await finish_siblings(before)
        assert isinstance(error.value.__cause__, ToolBlocked)
        assert error.value.__cause__.__cause__ is None, "Reporting the refusal failed"
    assert effects == []
    assert by_call(reports) == [status_report("double-2", 2, "blocked"), status_report("double-3", 3, "blocked")]
    assert monitor.errors == {}


@pytest.mark.asyncio
async def test_successful_calls_are_neither_reported_nor_marked():
    effects, reports = [], []
    async with configured_client(audit_reports=reports) as (client, requests):
        monitor = Monitor(client, "allowed")
        await run_conversation(monitor, lambda value: effects.append(value) or str(value * 2))
    assert sorted(effects) == [2, 3]
    assert reports == []
    assert monitor.errors == {}
    assert all("error" not in message for message in requests[-1]["messages"] if message["role"] == "tool")


PENDING = [
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "double-2", "function": "double", "arguments": {"value": 2}}],
    }
]


@pytest.mark.asyncio
async def test_application_refusal_after_an_allow_is_reported_blocked_with_its_text_unmarked():
    reports = []
    async with configured_client(audit_reports=reports) as (client, requests):
        monitor = Monitor(client, "application-refusal")
        await monitor.before_transcript(PENDING, "double-2", "double", {"value": 2})
        assert await monitor.report_status("double-2", "double", {"value": 2}, "blocked") is True
        # The first report stands: a second one uploads nothing.
        assert await monitor.report_status("double-2", "double", {"value": 2}, "cancelled") is False
        history = [
            {"role": "user", "content": "Double 2"},
            {"type": "function_call", "call_id": "double-2", "name": "double", "arguments": '{"value":2}'},
            {"type": "function_call_output", "call_id": "double-2", "output": "Refused by the application"},
        ]
        await monitor.record(history)
    assert reports == [status_report("double-2", 2, "blocked")]
    result = next(message for message in requests[-1]["messages"] if message["role"] == "tool")
    assert result["content"] == "Refused by the application"
    assert "error" not in result


def upload_gate():
    return SimpleNamespace(started=asyncio.Event(), release=asyncio.Event())


@pytest.mark.asyncio
async def test_concurrent_status_reports_make_one_upload():
    reports, gate = [], upload_gate()
    async with configured_client(audit_reports=reports, upload_gate=gate) as (client, _requests):
        monitor = Monitor(client, "concurrent-reports")
        await monitor.before_transcript(PENDING, "double-2", "double", {"value": 2})
        first = asyncio.create_task(monitor.report_status("double-2", "double", {"value": 2}, "blocked"))
        await asyncio.wait_for(gate.started.wait(), 10)
        assert await monitor.report_status("double-2", "double", {"value": 2}, "cancelled") is False
        gate.release.set()
        assert await first is True
    assert reports == [status_report("double-2", 2, "blocked")]


@pytest.mark.asyncio
async def test_a_cancelled_reporter_whose_upload_succeeds_leaves_the_call_reported():
    reports, gate = [], upload_gate()
    async with configured_client(audit_reports=reports, upload_gate=gate) as (client, _requests):
        monitor = Monitor(client, "cancelled-reporter")
        await monitor.before_transcript(PENDING, "double-2", "double", {"value": 2})
        report = asyncio.create_task(monitor.report_status("double-2", "double", {"value": 2}, "cancelled"))
        await asyncio.wait_for(gate.started.wait(), 10)
        report.cancel()
        gate.release.set()
        with pytest.raises(asyncio.CancelledError):
            await report
        assert "double-2" in monitor.reported
        assert await monitor.report_status("double-2", "double", {"value": 2}, "blocked") is False
    assert reports == [status_report("double-2", 2, "cancelled")]


@pytest.mark.asyncio
async def test_a_paused_bypass_has_no_recorded_decision_to_report():
    reports = []
    async with configured_client("paused", audit_reports=reports) as (client, _requests):
        monitor = Monitor(client, "paused")
        await monitor.before_transcript(PENDING, "double-2", "double", {"value": 2})
        assert await monitor.report_status("double-2", "double", {"value": 2}, "blocked") is False
    assert reports == []


@pytest.mark.asyncio
async def test_a_rejected_call_is_already_reported():
    async def reject(**kwargs):
        return False

    reports = []
    async with configured_client(decision="escalate", audit_reports=reports) as (client, _requests):
        monitor = Monitor(client, "rejected-then-cancelled", approval_callback=reject)
        with pytest.raises(ToolBlocked):
            await monitor.before_transcript(PENDING, "double-2", "double", {"value": 2})
        assert await monitor.report_status("double-2", "double", {"value": 2}, "cancelled") is False
        assert monitor.unreported == {}
        with pytest.raises(ValueError):
            await monitor.report_status("double-2", "double", {"value": 2}, "completed")
    assert [(report["tool_status"], report.get("human_decision")) for report in reports] == [("blocked", "deny")]


@pytest.mark.asyncio
@pytest.mark.parametrize("stored", ["completed", "unknown", "cancelled"])
async def test_a_status_report_replaces_only_a_status_watcher_settled(stored):
    reports = []
    async with configured_client(audit_reports=reports, stored_status=stored) as (client, _requests):
        monitor = Monitor(client, "settled")
        await monitor.before_transcript(PENDING, "double-2", "double", {"value": 2})
        if stored == "cancelled":
            with pytest.raises(ToolBlocked, match="already reported"):
                await monitor.report_status("double-2", "double", {"value": 2}, "blocked")
        else:
            assert await monitor.report_status("double-2", "double", {"value": 2}, "blocked") is True
    assert reports == ([] if stored == "cancelled" else [status_report("double-2", 2, "blocked")])


@pytest.mark.asyncio
async def test_cancelled_prompt_is_reported_cancelled_without_an_invented_answer():
    entered = asyncio.Event()

    async def never_answers(**kwargs):
        entered.set()
        await asyncio.Event().wait()

    reports = []
    async with configured_client(decision="escalate", audit_reports=reports) as (client, _requests):
        monitor = Monitor(client, "cancelled-prompt", approval_callback=never_answers)
        task = asyncio.create_task(monitor.before_transcript(PENDING, "double-2", "double", {"value": 2}))
        await asyncio.wait_for(entered.wait(), 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert reports == [status_report("double-2", 2, "cancelled")]
    assert monitor.errors == {}


@pytest.mark.asyncio
async def test_cancelling_a_running_tool_reports_the_call_cancelled_and_leaves_its_result_unmarked():
    entered = asyncio.Event()

    @function_tool(failure_error_function=None)
    async def double(value: int) -> str:
        """Double an integer; the call for 3 waits until cancelled."""
        if value == 3:
            entered.set()
            await asyncio.Event().wait()
        return str(value * 2)

    history = [
        {"role": "user", "content": "Double 2 and 3"},
        {"type": "function_call", "call_id": "double-2", "name": "double", "arguments": '{"value":2}'},
        {"type": "function_call", "call_id": "double-3", "name": "double", "arguments": '{"value":3}'},
    ]

    def native(item):
        return SimpleNamespace(call_id=item["call_id"], name=item["name"], arguments=item["arguments"])

    reports = []
    async with configured_client(audit_reports=reports) as (client, requests):
        monitor = Monitor(client, "cancelled-run")
        done = await execute_tool(monitor, history, double, native(history[1]))
        task = asyncio.create_task(execute_tool(monitor, history, double, native(history[2])))
        await asyncio.wait_for(entered.wait(), 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        stopped = {"type": "function_call_output", "call_id": "double-3", "output": "Cancelled"}
        await monitor.record([*history, done, stopped])
    assert reports == [status_report("double-3", 3, "cancelled")]
    results = {message["tool_call_id"]: message for message in requests[-1]["messages"] if message["role"] == "tool"}
    assert results["double-3"]["content"] == "Cancelled"
    assert "error" not in results["double-3"]
    assert "error" not in results["double-2"]
    assert messages_for_watcher([*history, done, stopped], monitor.errors) == requests[-1]["messages"]


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [True, False])
async def test_native_runner_waits_for_application_approval_then_resumes_or_refuses(approved):
    entered, released = asyncio.Event(), asyncio.Event()
    effects, approvals = [], []

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

    reports = []
    async with configured_client(decision="escalate", audit_reports=reports) as (client, _requests):
        monitor = Monitor(client, "human", approval_callback=decide)
        before = asyncio.all_tasks()
        task = asyncio.create_task(run_conversation(monitor, lambda value: effects.append(value) or str(value * 2)))
        try:
            await asyncio.wait_for(entered.wait(), 20)
            assert effects == []
            assert not task.done()
        finally:
            released.set()
        if approved:
            await asyncio.wait_for(task, 30)
        else:
            with pytest.raises(UserError) as error:
                await asyncio.wait_for(task, 30)
            assert isinstance(error.value.__cause__, ToolBlocked)
        await finish_siblings(before)
    assert approvals
    assert sorted(effects) == ([2, 3] if approved else [])
    # The human upload carries the outcome: pending for an approval, blocked for a
    # rejection. Nothing else is uploaded, and no result is marked as a tool error.
    assert sorted((report["tool_use_id"], report["tool_status"], report["human_decision"]) for report in reports) == [
        (call_id, "pending" if approved else "blocked", "allow" if approved else "deny")
        for call_id in ("double-2", "double-3")
    ]
    assert monitor.errors == {}


@pytest.mark.asyncio
async def test_truthy_application_result_is_not_human_approval():
    async def decide(**kwargs):
        return "yes"

    effects = []
    async with configured_client(decision="escalate") as (client, _requests):
        with pytest.raises(UserError) as error:
            await run_conversation(
                Monitor(client, "literal-approval", approval_callback=decide),
                lambda value: effects.append(value) or str(value * 2),
            )
        assert isinstance(error.value.__cause__, ToolBlocked)
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
@pytest.mark.parametrize("failure", ["rejected", "acknowledged_noop"])
async def test_human_audit_failure_never_releases_native_tools(failure):
    async def approve(**kwargs):
        return True

    effects, reports = [], []
    async with configured_client(
        decision="escalate",
        audit_reports=reports,
        report_failure=failure == "rejected",
        report_noop=failure == "acknowledged_noop",
    ) as (client, _requests):
        # Native runners propagate refusals or retain them as tool errors.
        with suppress(Exception):
            await run_conversation(
                Monitor(client, "audit-failure", approval_callback=approve),
                lambda value: effects.append(value) or str(value * 2),
            )
    assert reports, "The native tool must reach the human reporting boundary"
    assert effects == []


@pytest.mark.asyncio
async def test_native_tool_waits_for_recorded_human_choice():
    async def approve(**kwargs):
        return True

    effects, reports = [], []

    def execute(value):
        assert any(
            record["raw_tool_call"]["tool_input"] == {"value": value} and record["human_decision"] == "allow"
            for record in reports
        ), "A native effect happened before its human audit upload"
        effects.append(value)
        return str(value * 2)

    async with configured_client(decision="escalate", audit_reports=reports) as (client, _requests):
        await run_conversation(Monitor(client, "recorded-human", approval_callback=approve), execute)
    assert sorted(effects) == [2, 3]
