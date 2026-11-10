"""Applied policy and human approval through the installed framework's native runner."""

import asyncio
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from demo.enforce import run_conversation
from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.adk.tools import FunctionTool
from google.genai import types
from watcher_google_adk.monitoring import ApprovalRequired, Monitor, ToolBlocked
from watcher_google_adk.native import ConversationHistory, before_tool_callback

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
    unanswered=frozenset(),
    upload_gate=None,
    stored_status="pending",
):
    """Return the actual SDK over a local transport with one configured server policy.

    Hook requests for the tool-use IDs in ``unanswered`` never get a response.
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
        if body["input"]["tool_use_id"] in unanswered:
            await asyncio.Event().wait()
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
    async with configured_client(grading_failure=True) as (client, _requests):
        await run_conversation(Monitor(client, "fail-open"), lambda value: effects.append(value) or str(value * 2))
    assert sorted(effects) == [2, 3]


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


# ADK cancels the other parallel call once one is refused. Watcher never answers
# double-3 in these tests, so it is always cancelled before it has an evaluation
# and only double-2 is reported, whatever the scheduling order.
SIBLING_UNANSWERED = frozenset({"double-3"})


@pytest.mark.asyncio
async def test_unattended_escalation_never_executes():
    effects, reports = [], []
    async with configured_client(decision="escalate", audit_reports=reports, unanswered=SIBLING_UNANSWERED) as (
        client,
        _requests,
    ):
        with pytest.raises(ApprovalRequired) as error:
            await asyncio.wait_for(
                run_conversation(Monitor(client, "unattended"), lambda value: effects.append(value) or str(value * 2)),
                20,
            )
        assert error.value.__cause__ is None, "Reporting the refusal failed"
    assert effects == []
    assert reports == [status_report("double-2", 2, "blocked")]


@pytest.mark.asyncio
async def test_watcher_denial_is_reported_blocked():
    effects, reports = [], []
    async with configured_client(decision="deny", audit_reports=reports, unanswered=SIBLING_UNANSWERED) as (
        client,
        _requests,
    ):
        with pytest.raises(ToolBlocked) as error:
            await asyncio.wait_for(
                run_conversation(Monitor(client, "denied"), lambda value: effects.append(value) or str(value * 2)),
                20,
            )
        assert error.value.__cause__ is None, "Reporting the refusal failed"
    assert effects == []
    assert reports == [status_report("double-2", 2, "blocked")]


@pytest.mark.asyncio
async def test_successful_calls_are_neither_reported_nor_marked():
    effects, reports = [], []
    async with configured_client(audit_reports=reports) as (client, requests):
        await run_conversation(Monitor(client, "allowed"), lambda value: effects.append(value) or str(value * 2))
    assert sorted(effects) == [2, 3]
    assert reports == []
    assert all("error" not in message for message in requests[-1]["messages"] if message["role"] == "tool")


@pytest.mark.asyncio
async def test_cancelled_prompt_is_reported_cancelled_without_an_invented_answer():
    entered = asyncio.Event()

    async def never_answers(**kwargs):
        entered.set()
        await asyncio.Event().wait()

    pending = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "double-2", "function": "double", "arguments": {"value": 2}}],
        }
    ]
    reports = []
    async with configured_client(decision="escalate", audit_reports=reports) as (client, _requests):
        monitor = Monitor(client, "cancelled-prompt", approval_callback=never_answers)
        task = asyncio.create_task(monitor.before_transcript(pending, "double-2", "double", {"value": 2}))
        await asyncio.wait_for(entered.wait(), 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert reports == [status_report("double-2", 2, "cancelled")]


PENDING = [
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "double-2", "function": "double", "arguments": {"value": 2}}],
    }
]


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


class ConfirmationModel(BaseLlm):
    """Request double(2); answer once the call has a result ADK lets the model see."""

    async def generate_content_async(self, llm_request, stream=False):
        if any(
            part.function_response and part.function_response.name == "double"
            for content in llm_request.contents
            for part in content.parts or []
        ):
            content = types.Content(role="model", parts=[types.Part(text="Done")])
        else:
            call = types.FunctionCall(id="double-2", name="double", args={"value": 2})
            content = types.Content(role="model", parts=[types.Part(function_call=call)])
        yield LlmResponse(content=content)


class ConfirmationSession:
    """One ADK session whose tool requires confirmation, run through the native callback."""

    def __init__(self, monitor, tool, **agent_options):
        self.monitor = monitor
        self.history = ConversationHistory()
        self.callback = before_tool_callback(monitor, self.history)
        agent = LlmAgent(
            name="confirming",
            model=ConfirmationModel(model="deterministic"),
            tools=[FunctionTool(tool, require_confirmation=True)],
            before_model_callback=self.history.before_model_callback,
            before_tool_callback=self.callback,
            **agent_options,
        )
        self.runner = InMemoryRunner(agent=agent, app_name="confirming")
        self.session_id = ""
        self.request_id = ""

    async def start(self):
        """Run until ADK asks for confirmation of double-2."""
        session = await self.runner.session_service.create_session(app_name="confirming", user_id="person")
        self.session_id = session.id
        requests = []
        async for event in self.runner.run_async(
            user_id="person",
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text="Go")]),
        ):
            requests += [call.id for call in event.get_function_calls() if call.name == "adk_request_confirmation"]
        assert len(requests) == 1
        self.request_id = requests[0]
        return self

    async def answer(self, confirmed):
        """Submit one answer as its own user message; return the exception it raised, or None."""
        response = types.FunctionResponse(
            id=self.request_id, name="adk_request_confirmation", response={"confirmed": confirmed}
        )
        reply = types.Content(role="user", parts=[types.Part(function_response=response)])
        try:
            async for _event in self.runner.run_async(user_id="person", session_id=self.session_id, new_message=reply):
                pass
        except Exception as error:
            return error
        return None

    async def record(self):
        """Record the session's history through the Monitor, as an application does after a turn."""
        session = await self.runner.session_service.get_session(
            app_name="confirming", user_id="person", session_id=self.session_id
        )
        assert session is not None
        await self.monitor.record(self.history.messages(session))

    async def record_stored(self):
        """Record the session's stored events directly through the Monitor.

        Concurrent submissions interleave events in storage that each run's own
        session view never saw, and ConversationHistory refuses such a history,
        so this reads the stored order back as an application would.
        """
        session = await self.runner.session_service.get_session(
            app_name="confirming", user_id="person", session_id=self.session_id
        )
        assert session is not None
        await self.monitor.record([event.content for event in session.events if event.content is not None])


def doubling(effects):
    """A tool that records each run's argument in effects."""

    def double(value: int) -> str:
        """Double an integer."""
        effects.append(value)
        return str(value * 2)

    return double


async def run_with_confirmation(monitor, answers, effects, before_answers=None):
    """Run a tool that requires confirmation through the native callback, answer it, then record.

    ``answers`` are the person's choices, each submitted to the same session as
    its own user message; none leaves the request unanswered. ``before_answers``
    is awaited once the confirmation is requested and before any answer.
    Returns the callback, so a test can drive its second pass again, and what
    each submission did: None when it finished, otherwise the exception it raised.
    """
    session = await ConfirmationSession(monitor, doubling(effects)).start()
    if before_answers is not None:
        await before_answers()
    outcomes = [await session.answer(answer) for answer in answers]
    await session.record()
    return session.callback, outcomes


def answered(confirmed):
    """The ToolContext fields ADK sets on the second pass for double-2."""
    return SimpleNamespace(function_call_id="double-2", tool_confirmation=SimpleNamespace(confirmed=confirmed))


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", [False, True, None])
async def test_native_confirmation_answers(answer):
    """A rejection is reported blocked with ADK's refusal text unmarked; approval runs; no answer stays pending."""
    effects, reports = [], []
    async with configured_client(audit_reports=reports) as (client, requests):
        await run_with_confirmation(Monitor(client, "confirmation"), () if answer is None else (answer,), effects)
    evaluated = [body["input"]["tool_use_id"] for body in requests if body["input"] is not None]
    assert evaluated == ["double-2"], "Watcher must judge the call once, before confirmation"
    recorded = requests[-1]["messages"]
    assert not any("adk_request_confirmation" in json.dumps(message) for message in recorded)
    results = [message for message in recorded if message["role"] == "tool"]
    if answer is False:
        assert effects == []
        assert reports == [status_report("double-2", 2, "blocked")]
        assert results == [
            {
                "role": "tool",
                "content": '{"error": "This tool call is rejected."}',
                "tool_call_id": "double-2",
                "function": "double",
            }
        ]
    elif answer is True:
        assert effects == [2]
        assert reports == []
        assert results == [{"role": "tool", "content": "4", "tool_call_id": "double-2", "function": "double"}]
    else:
        assert effects == []
        assert reports == []
        assert results == []


@pytest.mark.asyncio
async def test_a_replayed_approval_runs_the_call_once():
    effects, reports = [], []
    async with configured_client(audit_reports=reports) as (client, requests):
        _, outcomes = await run_with_confirmation(Monitor(client, "replayed"), (True, True), effects)
    assert effects == [2]
    assert outcomes[0] is None
    assert isinstance(outcomes[1], ToolBlocked), outcomes
    assert reports == []
    results = [message for message in requests[-1]["messages"] if message["role"] == "tool"]
    assert results == [{"role": "tool", "content": "4", "tool_call_id": "double-2", "function": "double"}]


@pytest.mark.asyncio
async def test_an_approval_after_a_rejection_never_runs_the_call():
    effects, reports = [], []
    async with configured_client(audit_reports=reports) as (client, requests):
        _, outcomes = await run_with_confirmation(
            Monitor(client, "rejected-then-approved"), (False, True, False), effects
        )
    assert effects == []
    assert outcomes[0] is None
    assert isinstance(outcomes[1], ToolBlocked), outcomes
    assert outcomes[2] is None
    assert reports == [status_report("double-2", 2, "blocked")]
    results = [message for message in requests[-1]["messages"] if message["role"] == "tool"]
    assert results == [
        {
            "role": "tool",
            "content": '{"error": "This tool call is rejected."}',
            "tool_call_id": "double-2",
            "function": "double",
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["cancelled", "blocked"])
async def test_a_reported_status_revokes_an_unanswered_confirmation(status):
    """The application stops the call before anyone answers; a later approval must not run it."""
    effects, reports = [], []
    async with configured_client(audit_reports=reports) as (client, requests):
        monitor = Monitor(client, "reported")

        async def application_stops_the_call():
            assert await monitor.report_status("double-2", "double", {"value": 2}, status) is True

        _, outcomes = await run_with_confirmation(monitor, (True, False), effects, application_stops_the_call)
    assert effects == []
    assert isinstance(outcomes[0], ToolBlocked), outcomes
    assert outcomes[1] is None
    assert reports == [status_report("double-2", 2, status)]
    results = [message for message in requests[-1]["messages"] if message["role"] == "tool"]
    assert results == [
        {
            "role": "tool",
            "content": '{"error": "This tool call is rejected."}',
            "tool_call_id": "double-2",
            "function": "double",
        }
    ]


def upload_gate():
    return SimpleNamespace(started=asyncio.Event(), release=asyncio.Event())


@pytest.mark.asyncio
async def test_an_approval_during_a_status_upload_is_refused():
    effects, reports, gate = [], [], upload_gate()
    async with configured_client(audit_reports=reports, upload_gate=gate) as (client, _requests):
        monitor = Monitor(client, "upload-in-flight")
        session = await ConfirmationSession(monitor, doubling(effects)).start()
        report = asyncio.create_task(monitor.report_status("double-2", "double", {"value": 2}, "cancelled"))
        await asyncio.wait_for(gate.started.wait(), 10)
        refused = await session.answer(True)
        gate.release.set()
        assert await report is True
    assert effects == []
    assert isinstance(refused, ToolBlocked), refused
    assert reports == [status_report("double-2", 2, "cancelled")]


@pytest.mark.asyncio
async def test_a_cancelled_reporter_still_stops_the_call_once_its_upload_succeeds():
    effects, reports, gate = [], [], upload_gate()
    async with configured_client(audit_reports=reports, upload_gate=gate) as (client, _requests):
        monitor = Monitor(client, "cancelled-reporter")
        session = await ConfirmationSession(monitor, doubling(effects)).start()
        report = asyncio.create_task(monitor.report_status("double-2", "double", {"value": 2}, "blocked"))
        await asyncio.wait_for(gate.started.wait(), 10)
        report.cancel()
        gate.release.set()
        with pytest.raises(asyncio.CancelledError):
            await report
        refused = await session.answer(True)
    assert effects == []
    assert isinstance(refused, ToolBlocked), refused
    assert reports == [status_report("double-2", 2, "blocked")]
    assert "double-2" in monitor.reported
    assert "double-2" in monitor.stopped


@pytest.mark.asyncio
async def test_a_failed_status_report_still_stops_the_call():
    effects, reports = [], []
    async with configured_client(audit_reports=reports, report_failure=True) as (client, _requests):
        monitor = Monitor(client, "failed-report")
        session = await ConfirmationSession(monitor, doubling(effects)).start()
        with pytest.raises(ToolBlocked):
            await monitor.report_status("double-2", "double", {"value": 2}, "blocked")
        refused = await session.answer(True)
    assert effects == []
    assert isinstance(refused, ToolBlocked), refused
    assert "double-2" in monitor.stopped
    assert "double-2" not in monitor.reported, "A failed upload must leave the report free to retry"


@pytest.mark.asyncio
async def test_a_replayed_rejection_during_an_approved_run_keeps_the_runs_error():
    """While the approved tool runs, a replayed rejection arrives and is refused; the run then fails."""
    entered, release = asyncio.Event(), asyncio.Event()

    async def double(value: int) -> str:
        """Fail once released, as a tool whose disk filled up."""
        entered.set()
        await release.wait()
        raise RuntimeError("Disk full")

    def tool_error(tool, args, tool_context, error):
        return {"error": str(error)}

    reports = []
    async with configured_client(audit_reports=reports) as (client, requests):
        monitor = Monitor(client, "replay-during-run")
        session = await ConfirmationSession(monitor, double, on_tool_error_callback=tool_error).start()
        approval = asyncio.create_task(session.answer(True))
        await asyncio.wait_for(entered.wait(), 10)
        replay = await session.answer(False)
        release.set()
        assert await asyncio.wait_for(approval, 10) is None
        await session.record_stored()
    assert isinstance(replay, ToolBlocked), replay
    assert reports == []
    assert monitor.confirmations == {"double-2": True}
    results = [message for message in requests[-1]["messages"] if message["role"] == "tool"]
    assert results == [
        {
            "role": "tool",
            "content": '{"error": "Disk full"}',
            "tool_call_id": "double-2",
            "function": "double",
            "error": {"type": "unknown", "message": "Disk full"},
        }
    ]


@pytest.mark.asyncio
async def test_a_rerun_of_a_rejected_second_pass_does_not_upload_again():
    effects, reports = [], []
    async with configured_client(audit_reports=reports) as (client, _requests):
        callback, _ = await run_with_confirmation(Monitor(client, "rerun"), (False,), effects)
        assert await callback(SimpleNamespace(name="double"), {"value": 2}, answered(False)) is None
    assert reports == [status_report("double-2", 2, "blocked")]
    assert effects == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name, arguments", [("double", {"value": 3}), ("triple", {"value": 2})])
async def test_a_second_pass_with_another_name_or_arguments_is_refused(name, arguments):
    effects, reports = [], []
    async with configured_client(audit_reports=reports) as (client, _requests):
        callback, _ = await run_with_confirmation(Monitor(client, "changed"), (), effects)
        with pytest.raises(ToolBlocked):
            await callback(SimpleNamespace(name=name), arguments, answered(True))
        with pytest.raises(ToolBlocked):
            await callback(SimpleNamespace(name=name), arguments, answered(False))
    assert reports == []


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmed", [True, False])
async def test_a_confirmation_answer_for_a_call_not_released_here_is_refused(confirmed):
    callback = before_tool_callback(Monitor(object(), "unreleased"), ConversationHistory())
    with pytest.raises(ToolBlocked):
        await callback(SimpleNamespace(name="double"), {"value": 2}, answered(confirmed))


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
    # The human upload carries the outcome; a rejection is not reported a second time.
    assert all("human_decision" in record for record in reports)
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
