"""A call the Monitor withholds without recording its status is reported after record().

Watcher settles a call it let through whose later result has no error as
completed, so the refusal text the agent saw for a withheld call would read as
a completed run. The fake stores and settles like Watcher: a status upload fails
for a call not yet stored, replaces a settled status, and creates the record of
a call Watcher holds no decision for.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from copy import deepcopy

import httpx
import pytest
from google.genai import types
from watcher_google_adk.monitoring import Monitor, StatusNotRecorded, ToolBlocked

from watcher_sdk import AsyncWatcherClient, WatcherAPIError, WatcherConnectionError, WatcherTimeoutError

SESSION = "c1f7b8be-166e-4b12-81e9-d1f3d87e4725"
AT = "2026-09-25T00:00:00Z"
PENDING = [
    {"role": "user", "content": "Double 2"},
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "double-2", "function": "double", "arguments": {"value": 2}}],
    },
]
# The native history the application records, with the refusal text the agent saw.
REFUSED = [
    types.Content(role="user", parts=[types.Part(text="Double 2")]),
    types.Content(
        role="model",
        parts=[types.Part(function_call=types.FunctionCall(id="double-2", name="double", args={"value": 2}))],
    ),
    types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id="double-2", name="double", response={"result": "The call did not run"}
                )
            )
        ],
    ),
]
# A later history without the withheld call, as when the application starts the
# conversation again: Watcher stores it as another branch of the same session.
RESTARTED = [types.Content(role="user", parts=[types.Part(text="Start again")])]

BOTH = [
    {"role": "user", "content": "Double 2 and 3"},
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": "double-2", "function": "double", "arguments": {"value": 2}},
            {"id": "double-3", "function": "double", "arguments": {"value": 3}},
        ],
    },
]
BOTH_REFUSED = [
    types.Content(role="user", parts=[types.Part(text="Double 2 and 3")]),
    types.Content(
        role="model",
        parts=[
            types.Part(function_call=types.FunctionCall(id=f"double-{value}", name="double", args={"value": value}))
            for value in (2, 3)
        ],
    ),
    types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=f"double-{value}", name="double", response={"result": "The call did not run"}
                )
            )
            for value in (2, 3)
        ],
    ),
]


def stored_decision(call, verdict):
    """One decision record as extended trajectory detail returns it."""
    return {
        "tool_use_id": call["tool_use_id"],
        "tool_name": call["tool_name"],
        "raw_tool_call": {"tool_name": call["tool_name"], "tool_input": deepcopy(call["tool_input"])},
        "policy_decision": verdict,
        "applied_decision": verdict,
        "judged_decision": None if verdict == "not_evaluated" else verdict,
        "decision_source": "not_evaluated" if verdict == "not_evaluated" else "rule",
        "grades": [],
        "tool_status": "pending",
        "human_decision": None,
        "human_decided_at": None,
        "tool_call_id": "8a53c1d7-c1c6-4cfe-a7c7-2a3c6d6a26e4",
        "tool_call_decision_id": "3a64323f-e85b-45b7-a356-1847b8d0ee63",
        "tool_call_created_at": AT,
        "created_at": AT,
        "updated_at": AT,
    }


def status_report(status):
    return {
        "tool_use_id": "double-2",
        "tool_name": "double",
        "raw_tool_call": {"tool_name": "double", "tool_input": {"value": 2}},
        "policy_decision": "not_evaluated",
        "applied_decision": "not_evaluated",
        "decision_source": "not_evaluated",
        "tool_status": status,
    }


def receipt(call_id, synced):
    return httpx.Response(
        200,
        json={
            "synced_count": 1 if synced else 0,
            "synced_tool_use_ids": [call_id] if synced else [],
            "failed_tool_use_ids": [] if synced else [call_id],
            "failed_tool_call_grade_ids": [],
        },
    )


class StoredWatcher:
    """Store transcripts and decisions, and merge status uploads, as Watcher does.

    A hook request stores its transcript and Watcher's ``verdict`` before
    answering. ``hook`` "timeout" or "hang" then fails or never answers, so
    Watcher holds a decision the client never received; "unreachable" fails
    before storing anything. A transcript-only request settles each pending
    call with a result: completed if Watcher allowed it and the result has no
    ``error``, otherwise unknown. Every call any
    stored transcript holds stays stored, as on another branch of the session,
    while the trajectory shows only the latest transcript. The first ``hidden``
    session searches find nothing, and the first ``refused`` uploads, and every
    upload for a call in ``refusing``, fail as for a call not yet stored.
    ``forbidden`` refuses every upload's permission, and ``restricted`` hides
    a stored call's arguments. ``readback`` "forbidden" or "unavailable" fails
    the first call lookup after a stored upload, and ``corrupt`` edits every
    call lookup's response. Tool-call search is down unless ``searchable``, so
    a report made at once (report_status, a human decision) fails. Watcher
    stores the first upload for the call ID in ``stall`` but leaves it
    unanswered until ``release`` is set, and then fails it with a 503. When
    that upload is cancelled and ``linger`` is set, its cleanup sets
    ``lingering`` and waits for ``finish``, then lets the cancellation through
    ("cancelled") or fails as a dropped connection ("failed"). With
    ``cancel_record``, the next transcript-only request cancels the task that
    sent it just after Watcher accepts the transcript.
    """

    def __init__(
        self,
        hook="answer",
        verdict="allow",
        *,
        hidden=0,
        refused=0,
        refusing=(),
        forbidden=False,
        restricted=False,
        readback=None,
        corrupt=None,
        searchable=False,
        stall=None,
        linger=None,
        cancel_record=False,
    ):
        self.hook, self.verdict, self.hidden, self.refused = hook, verdict, hidden, refused
        self.refusing = set(refusing)
        self.forbidden, self.restricted, self.searchable = forbidden, restricted, searchable
        self.readback, self.corrupt, self.unreadable = readback, corrupt, None
        self.messages: list[dict] = []
        self.calls: dict[str, dict] = {}
        self.decisions: dict[str, dict] = {}
        self.uploads: list[dict] = []
        self.lookups = 0
        self.entered = asyncio.Event()
        self.stall, self.release, self.cancel_record = stall, asyncio.Event(), cancel_record
        self.linger, self.lingering, self.finish = linger, asyncio.Event(), asyncio.Event()

    async def respond(self, request):
        body = json.loads(request.content) if request.content else {}
        if request.url.path == "/v1/sessions/search":
            self.hidden -= 1
            sessions = [] if self.hidden >= 0 or not self.messages else [{"session_id": SESSION}]
            for session in sessions:
                session.update(agent_platform="other", trajectory_count=1, latest_trajectory_id="trajectory")
                session.update(message_count=len(self.messages), started_at=AT, ended_at=AT)
            return httpx.Response(200, json={"sessions": sessions, "total": len(sessions), "limit": 2, "offset": 0})
        if request.url.path == f"/v1/sessions/{SESSION}/trajectories/trajectory":
            trajectory = {"session_id": SESSION, "trajectory_id": "trajectory", "grades": [], "metadata": {}}
            # Extended detail types every tool call, as the server's message model does.
            messages = deepcopy(self.messages)
            for message in messages:
                for call in message.get("tool_calls") or []:
                    call["type"] = "function"
            trajectory.update(source="fixture", created_at=AT, messages=messages)
            return httpx.Response(200, json=trajectory | {"tool_call_decisions": self.decisions})
        if request.url.path == f"/v1/sessions/{SESSION}/tool-call":
            self.lookups += 1
            if self.unreadable:
                status, self.unreadable = 403 if self.unreadable == "forbidden" else 503, None
                return httpx.Response(status, json={"detail": "Fixture readback failure"})
            call = self.calls.get(request.url.params["tool_use_id"])
            if call is None:
                return httpx.Response(404, json={"detail": "Session not found"})
            decision = self.decisions.get(call["id"])
            detail = {"tool_use_id": call["id"], "tool_name": call["function"], "occurred_at": AT, "is_flagged": False}
            detail.update(can_read_findings=True, can_read_content=not self.restricted, has_result=False, result=None)
            detail["arguments"] = None if self.restricted else deepcopy(call["arguments"])
            detail["decision"] = None if decision is None else decision | {"raw_tool_call": {}}
            if self.corrupt:
                self.corrupt(detail)
            return httpx.Response(200, json=detail)
        if request.url.path == "/v1/tool-calls/search":
            if not self.searchable:
                return httpx.Response(503, json={"detail": "Fixture outage"})
            items = [
                {
                    "tool_call_id": decision["tool_call_id"],
                    "session_id": SESSION,
                    "occurred_at": AT,
                    "is_flagged": False,
                    "tool_use_id": call_id,
                    "message_ref": "message",
                    "tool_name": decision["tool_name"],
                    "applied_decision": decision["applied_decision"],
                }
                for call_id, decision in self.decisions.items()
            ]
            return httpx.Response(200, json={"tool_calls": items, "total": len(items), "limit": 100, "offset": 0})
        if request.url.path == "/v1/tool-call-decisions/batch":
            record = body["decisions"][0]
            self.uploads.append(record)
            if self.forbidden:
                return httpx.Response(403, json={"detail": "Fixture permission"})
            self.refused -= 1
            if self.refused >= 0 or record["tool_use_id"] not in self.calls or record["tool_use_id"] in self.refusing:
                return receipt(record["tool_use_id"], synced=False)
            call = {"tool_use_id": record["tool_use_id"], "tool_name": record["tool_name"]}
            call["tool_input"] = record["raw_tool_call"]["tool_input"]
            decision = self.decisions.setdefault(call["tool_use_id"], stored_decision(call, "not_evaluated"))
            decision["tool_status"] = record["tool_status"]
            decision.update({key: record[key] for key in ("human_decision", "human_decided_at") if key in record})
            self.unreadable, self.readback = self.readback, None
            if self.stall == call["tool_use_id"]:
                self.stall = None
                self.entered.set()
                try:
                    await self.release.wait()
                except asyncio.CancelledError:
                    if self.linger is None:
                        raise
                    self.lingering.set()
                    await self.finish.wait()
                    if self.linger == "failed":
                        raise httpx.ReadError("Fixture connection dropped", request=request) from None
                    raise
                return httpx.Response(503, json={"detail": "Fixture outage"})
            return receipt(call["tool_use_id"], synced=True)
        assert request.url.path == "/v1/hooks/pre-tool-use"
        call = body["input"]
        if self.hook == "unreachable" and call is not None:
            raise httpx.ConnectError("Fixture outage", request=request)
        self.messages = deepcopy(body["messages"])
        for message in self.messages:
            for stored in message.get("tool_calls") or []:
                self.calls.setdefault(stored["id"], deepcopy(stored))
        if call is None:
            for message in self.messages:
                decision = self.decisions.get(message.get("tool_call_id"))
                if decision and decision["tool_status"] == "pending":
                    clean = message.get("error") is None and decision["applied_decision"] == "allow"
                    decision["tool_status"] = "completed" if clean else "unknown"
            sender = asyncio.current_task()
            if self.cancel_record and sender is not None:
                self.cancel_record = False
                asyncio.get_running_loop().call_soon(sender.cancel)
            return httpx.Response(200, json=[])
        self.decisions[call["tool_use_id"]] = stored_decision(call, self.verdict)
        if self.hook == "timeout":
            raise httpx.ReadTimeout("Fixture timeout", request=request)
        if self.hook == "hang":
            self.entered.set()
            await asyncio.Event().wait()
        outcome = {"decision": self.verdict, "judged_decision": self.verdict, "enforcement_mode": "enforce"}
        outcome.update(decision_source="rule", tool_use_id=call["tool_use_id"], latency_ms=1)
        return httpx.Response(200, json=outcome | {"verdict": {"summary": "Fixture", "explanation": "Fixture"}})


async def reject(**kwargs):
    return False


@asynccontextmanager
async def monitor_for(fake, **options):
    async with (
        httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(fake.respond)) as transport,
        AsyncWatcherClient(
            "https://watcher.invalid",
            httpx_client=transport,
            manage_external_httpx_client_lifecycle=False,
            max_retries=0,
        ) as client,
    ):
        yield Monitor(client, "withheld", **options)


async def withhold(monitor, fake, expected):
    """Submit the pending call, cancelling it while Watcher grades when the fake never answers."""
    task = asyncio.create_task(monitor.before_transcript(PENDING, "double-2", "double", {"value": 2}))
    if fake.hook == "hang":
        await asyncio.wait_for(fake.entered.wait(), 10)
        task.cancel()
    with pytest.raises(expected) as error:
        await task
    return error.value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hook, expected, status, verdict",
    [
        ("timeout", WatcherTimeoutError, "blocked", "allow"),
        ("hang", asyncio.CancelledError, "cancelled", "allow"),
        ("unreachable", WatcherConnectionError, "blocked", "not_evaluated"),
    ],
)
async def test_a_call_withheld_before_watcher_answered_is_reported_after_record(hook, expected, status, verdict):
    """Watcher may record an allow the client never saw; the call never ran, so record() replaces its settlement."""
    fake = StoredWatcher(hook)
    async with monitor_for(fake) as monitor:
        await withhold(monitor, fake, expected)
        assert fake.uploads == []
        await monitor.record(REFUSED)
    assert fake.uploads == [status_report(status)]
    assert fake.decisions["double-2"]["tool_status"] == status
    assert fake.decisions["double-2"]["applied_decision"] == verdict
    assert monitor.unreported == {}


@pytest.mark.asyncio
async def test_record_waits_for_watcher_to_store_the_call():
    fake = StoredWatcher("timeout", hidden=2, refused=1)
    async with monitor_for(fake) as monitor:
        await withhold(monitor, fake, WatcherTimeoutError)
        await monitor.record(REFUSED)
    assert fake.uploads == [status_report("blocked")] * 2
    assert fake.decisions["double-2"]["tool_status"] == "blocked"


@pytest.mark.asyncio
async def test_a_failed_late_report_raises_after_recording_and_the_next_record_retries_it():
    fake = StoredWatcher("timeout", refused=1000)
    async with monitor_for(fake, human_audit_timeout=0.3) as monitor:
        await withhold(monitor, fake, WatcherTimeoutError)
        with pytest.raises(StatusNotRecorded, match="withheld call") as error:
            await monitor.record(REFUSED)
        assert isinstance(error.value.__cause__, TimeoutError)
        assert set(error.value.failures) == error.value.retrying == {"double-2"}
        # The transcript was accepted, and its refusal text settled the call.
        assert fake.decisions["double-2"]["tool_status"] == "completed"
        assert "double-2" in monitor.unreported
        assert "double-2" not in monitor.reported
        fake.refused = 0
        await monitor.record(REFUSED)
    assert fake.decisions["double-2"]["tool_status"] == "blocked"
    assert monitor.unreported == {}


@pytest.mark.asyncio
async def test_retryable_failures_stop_after_late_report_attempts():
    fake = StoredWatcher("timeout", refused=1000)
    async with monitor_for(fake, human_audit_timeout=0.3, late_report_attempts=2) as monitor:
        await withhold(monitor, fake, WatcherTimeoutError)
        for retrying in ({"double-2"}, set()):
            with pytest.raises(StatusNotRecorded) as error:
                await monitor.record(REFUSED)
            assert error.value.retrying == retrying
        assert isinstance(monitor.unrecorded["double-2"], TimeoutError)
        lookups = fake.lookups
        await monitor.record(REFUSED)
        assert fake.lookups == lookups
    assert monitor.unreported == {}
    assert fake.decisions["double-2"]["tool_status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["forbidden", "restricted"])
async def test_a_permanent_failure_is_not_retried(fault):
    fake = StoredWatcher("timeout", **{fault: True})
    async with monitor_for(fake) as monitor:
        await withhold(monitor, fake, WatcherTimeoutError)
        with pytest.raises(StatusNotRecorded) as error:
            await monitor.record(REFUSED)
        assert set(error.value.failures) == set(monitor.unrecorded) == {"double-2"}
        assert error.value.retrying == set()
        lookups = fake.lookups
        await monitor.record(REFUSED)
        assert fake.lookups == lookups
    assert len(fake.uploads) == (1 if fault == "forbidden" else 0)
    assert monitor.unreported == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("readback", ["forbidden", "unavailable"])
async def test_a_status_stored_before_its_readback_failed_is_not_uploaded_again(readback):
    """The status may be stored although the Monitor could not confirm it; a later lookup that sees it stops."""
    fake = StoredWatcher("timeout", readback=readback)
    async with monitor_for(fake) as monitor:
        await withhold(monitor, fake, WatcherTimeoutError)
        with pytest.raises(StatusNotRecorded) as error:
            await monitor.record(REFUSED)
        assert fake.decisions["double-2"]["tool_status"] == "blocked"
        assert error.value.retrying == (set() if readback == "forbidden" else {"double-2"})
        await monitor.record(REFUSED)
    assert len(fake.uploads) == 1
    assert monitor.unreported == {}
    assert set(monitor.unrecorded) == ({"double-2"} if readback == "forbidden" else set())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corrupt",
    [
        lambda detail: detail.update(tool_use_id="double-3"),
        lambda detail: detail.update(tool_name="triple"),
        lambda detail: detail["arguments"].update(value=2.0),
        lambda detail: detail["decision"].update(tool_use_id="double-3"),
        lambda detail: detail["decision"].update(tool_name="triple"),
    ],
    ids=["call ID", "function", "argument type", "decision call ID", "decision tool name"],
)
async def test_a_stored_call_that_contradicts_the_withheld_one_is_not_uploaded(corrupt):
    fake = StoredWatcher("timeout", corrupt=corrupt)
    async with monitor_for(fake) as monitor:
        await withhold(monitor, fake, WatcherTimeoutError)
        with pytest.raises(StatusNotRecorded) as error:
            await monitor.record(REFUSED)
    assert isinstance(error.value.failures["double-2"], ToolBlocked)
    assert error.value.retrying == set()
    assert fake.uploads == []


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["forbidden", "refused"])
async def test_a_human_rejection_reported_later_settles_the_withheld_call(fault):
    """A rejection whose upload failed is withheld; once it is recorded, nothing stays queued or given up on."""
    fake = StoredWatcher(verdict="escalate", **({"forbidden": True} if fault == "forbidden" else {"refused": 1000}))
    async with monitor_for(fake, approval_callback=reject, human_audit_timeout=0.3) as monitor:
        await withhold(monitor, fake, WatcherAPIError)
        # Without the call's result, Watcher keeps it pending, as a human decision needs.
        with pytest.raises(StatusNotRecorded):
            await monitor.record(REFUSED[:2])
        assert "double-2" in (monitor.unrecorded if fault == "forbidden" else monitor.unreported)
        fake.forbidden, fake.refused, fake.searchable = False, 0, True
        await monitor.report_human_decision("double-2", "double", {"value": 2}, approved=False)
        assert monitor.unreported == monitor.unrecorded == monitor.late_attempts == {}
        assert "double-2" in monitor.reported
        uploads = len(fake.uploads)
        await monitor.record(REFUSED)
        assert len(fake.uploads) == uploads
    assert fake.decisions["double-2"]["tool_status"] == "blocked"
    assert fake.decisions["double-2"]["human_decision"] == "deny"


@pytest.mark.asyncio
async def test_record_finds_a_withheld_call_missing_from_the_latest_trajectory():
    """Watcher records the status of a call on any branch of the session, so the lookup searches them all."""
    fake = StoredWatcher("timeout")
    async with monitor_for(fake) as monitor:
        await withhold(monitor, fake, WatcherTimeoutError)
        await monitor.record(RESTARTED)
    assert fake.uploads == [status_report("blocked")]
    assert fake.decisions["double-2"]["tool_status"] == "blocked"


@pytest.mark.asyncio
async def test_a_late_report_pauses_longer_between_lookups():
    """Pauses double from 0.1 s up to 1 s: 1.6 s of waiting takes five lookups, not sixteen."""
    fake = StoredWatcher("timeout", refused=1000)
    async with monitor_for(fake, human_audit_timeout=1.6, late_report_attempts=1) as monitor:
        await withhold(monitor, fake, WatcherTimeoutError)
        with pytest.raises(StatusNotRecorded):
            await monitor.record(REFUSED)
    assert 2 <= len(fake.uploads) <= 6


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["blocked", "cancelled"])
async def test_a_call_already_blocked_or_cancelled_keeps_its_status(status):
    fake = StoredWatcher("timeout")
    async with monitor_for(fake) as monitor:
        await withhold(monitor, fake, WatcherTimeoutError)
        fake.decisions["double-2"]["tool_status"] = status
        await monitor.record(REFUSED)
    assert fake.uploads == []
    assert fake.decisions["double-2"]["tool_status"] == status
    assert monitor.unreported == {}


@pytest.mark.asyncio
async def test_a_denial_whose_report_failed_is_reported_after_record():
    fake = StoredWatcher(verdict="deny")
    async with monitor_for(fake) as monitor:
        refusal = await withhold(monitor, fake, ToolBlocked)
        assert refusal.__cause__ is not None, "The immediate report should have failed"
        assert fake.uploads == []
        await monitor.record(REFUSED)
    assert fake.uploads == [status_report("blocked")]
    assert fake.decisions["double-2"]["tool_status"] == "blocked"
    assert fake.decisions["double-2"]["applied_decision"] == "deny"


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", [RuntimeError("The prompt failed"), "yes"])
async def test_a_failed_approval_callback_reports_only_the_execution_status(answer):
    async def ask(**kwargs):
        if isinstance(answer, Exception):
            raise answer
        return answer

    fake = StoredWatcher(verdict="escalate")
    async with monitor_for(fake, approval_callback=ask) as monitor:
        await withhold(monitor, fake, RuntimeError if isinstance(answer, Exception) else ToolBlocked)
        await monitor.record(REFUSED)
    assert fake.uploads == [status_report("blocked")]
    assert fake.decisions["double-2"]["human_decision"] is None


@pytest.mark.asyncio
async def test_only_the_reports_that_failed_stay_queued():
    fake = StoredWatcher("timeout", refusing={"double-3"})
    async with monitor_for(fake, human_audit_timeout=0.3) as monitor:
        for value in (2, 3):
            with pytest.raises(WatcherTimeoutError):
                await monitor.before_transcript(BOTH, f"double-{value}", "double", {"value": value})
        with pytest.raises(ToolBlocked, match="withheld call"):
            await monitor.record(BOTH_REFUSED)
        assert set(monitor.unreported) == {"double-3"}
        assert monitor.reported == {"double-2"}
        fake.refusing.clear()
        await monitor.record(BOTH_REFUSED)
    assert {call_id: decision["tool_status"] for call_id, decision in fake.decisions.items()} == {
        "double-2": "blocked",
        "double-3": "blocked",
    }
    assert [upload["tool_use_id"] for upload in fake.uploads].count("double-2") == 1
    assert monitor.unreported == {}


@pytest.mark.asyncio
async def test_cancelling_record_stops_its_late_reports_at_once():
    """The call whose report was stopped stays queued without using an attempt, and the next record() reports it."""
    fake = StoredWatcher("timeout", refused=1000)
    async with monitor_for(fake) as monitor:
        await withhold(monitor, fake, WatcherTimeoutError)
        task = asyncio.create_task(monitor.record(REFUSED))
        while not fake.uploads:
            await asyncio.sleep(0.01)
        loop = asyncio.get_running_loop()
        cancelled_at = loop.time()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert loop.time() - cancelled_at < 1
        assert "double-2" in monitor.unreported
        assert "double-2" not in monitor.reported
        assert monitor.late_attempts == monitor.unrecorded == {}
        fake.refused = 0
        await monitor.record(REFUSED)
    assert fake.decisions["double-2"]["tool_status"] == "blocked"
    assert monitor.unreported == {}


@pytest.mark.asyncio
async def test_a_status_stored_by_an_upload_that_record_cancelled_is_not_uploaded_again():
    """Watcher may store an upload whose answer the cancellation discarded; the next lookup finds it."""
    fake = StoredWatcher("timeout", stall="double-2")
    async with monitor_for(fake) as monitor:
        await withhold(monitor, fake, WatcherTimeoutError)
        task = asyncio.create_task(monitor.record(REFUSED))
        await asyncio.wait_for(fake.entered.wait(), 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert fake.decisions["double-2"]["tool_status"] == "blocked"
        assert "double-2" in monitor.unreported
        assert "double-2" not in monitor.reported
        assert monitor.late_attempts == {}
        await monitor.record(REFUSED)
    assert len(fake.uploads) == 1
    assert monitor.unreported == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("stored", ["unknown", "blocked"])
async def test_a_rejection_reported_again_replaces_what_watcher_recorded_from_the_refusal(stored):
    """The withheld call never ran, so a status settled from its refusal text, or reported without the choice, gives way."""
    fake = StoredWatcher(verdict="escalate", forbidden=stored == "unknown")
    async with monitor_for(fake, approval_callback=reject) as monitor:
        await withhold(monitor, fake, WatcherAPIError)
        if stored == "unknown":
            with pytest.raises(StatusNotRecorded):
                await monitor.record(REFUSED)
            assert "double-2" in monitor.unrecorded
        else:
            await monitor.record(REFUSED)
        assert fake.decisions["double-2"]["tool_status"] == stored
        fake.forbidden, fake.searchable = False, True
        await monitor.report_human_decision("double-2", "double", {"value": 2}, approved=False)
        assert monitor.unreported == monitor.unrecorded == {}
    assert fake.decisions["double-2"]["tool_status"] == "blocked"
    assert fake.decisions["double-2"]["human_decision"] == "deny"
    assert fake.decisions["double-2"]["applied_decision"] == "escalate"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["released", "decided"])
async def test_a_later_rejection_never_replaces_a_released_call_or_a_recorded_choice(case):
    """An approved call may have run, and a choice already recorded stands."""

    async def ask(**kwargs):
        return case == "released"

    fake = StoredWatcher(verdict="escalate", searchable=case == "released")
    async with monitor_for(fake, approval_callback=ask) as monitor:
        if case == "released":
            await monitor.before_transcript(PENDING, "double-2", "double", {"value": 2})
            await monitor.record(REFUSED)
        else:
            await withhold(monitor, fake, WatcherAPIError)
            await monitor.record(REFUSED)
            fake.decisions["double-2"].update(human_decision="deny", human_decided_at=AT)
            fake.searchable = True
        stored = deepcopy(fake.decisions["double-2"])
        with pytest.raises(ToolBlocked):
            await monitor.report_human_decision("double-2", "double", {"value": 2}, approved=False)
    assert fake.decisions["double-2"] == stored


@pytest.mark.asyncio
async def test_a_rejection_recorded_while_the_late_report_runs_settles_the_call():
    """The late report failing afterwards neither queues the call again nor raises."""
    fake = StoredWatcher(verdict="escalate", stall="double-2")
    async with monitor_for(fake, approval_callback=reject) as monitor:
        await withhold(monitor, fake, WatcherAPIError)
        task = asyncio.create_task(monitor.record(REFUSED))
        await asyncio.wait_for(fake.entered.wait(), 10)
        fake.searchable = True
        await monitor.report_human_decision("double-2", "double", {"value": 2}, approved=False)
        fake.release.set()
        await task
        assert "double-2" in monitor.reported
        assert monitor.unreported == monitor.unrecorded == monitor.late_attempts == {}
    assert fake.decisions["double-2"]["human_decision"] == "deny"


@pytest.mark.asyncio
async def test_cancelling_record_as_its_reports_start_releases_their_claims():
    """A report cancelled before it reached Watcher leaves its call queued for the next record()."""
    fake = StoredWatcher("timeout", hidden=1000, cancel_record=True)
    async with monitor_for(fake) as monitor:
        await withhold(monitor, fake, WatcherTimeoutError)
        task = asyncio.create_task(monitor.record(REFUSED))
        with pytest.raises(asyncio.CancelledError):
            await task
        assert fake.uploads == []
        assert "double-2" in monitor.unreported
        assert "double-2" not in monitor.reported
        assert monitor.late_attempts == monitor.unrecorded == {}
        fake.hidden = 0
        await monitor.record(REFUSED)
    assert fake.decisions["double-2"]["tool_status"] == "blocked"
    assert monitor.unreported == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("other", ["confirmed", "failed"])
async def test_cancelling_record_keeps_the_outcome_of_reports_that_finished(other):
    """Only the call whose report was stopped stays queued; a confirmed status or a failure stands."""
    seen = []

    def watch(detail):
        seen.append(detail["tool_use_id"])
        if other == "failed" and detail["tool_use_id"] == "double-3":
            detail["tool_name"] = "triple"

    fake = StoredWatcher("timeout", corrupt=watch, stall="double-2")
    async with monitor_for(fake) as monitor:
        for value in (2, 3):
            with pytest.raises(WatcherTimeoutError):
                await monitor.before_transcript(BOTH, f"double-{value}", "double", {"value": value})
        task = asyncio.create_task(monitor.record(BOTH_REFUSED))
        await asyncio.wait_for(fake.entered.wait(), 10)
        # The other call's lookups, including the readback of a confirmed status, are done.
        while seen.count("double-3") < (2 if other == "confirmed" else 1):
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert set(monitor.unreported) == {"double-2"}
        assert monitor.reported == ({"double-3"} if other == "confirmed" else set())
        assert set(monitor.unrecorded) == ({"double-3"} if other == "failed" else set())
        assert monitor.late_attempts == {}


async def within(seconds, awaitable):
    async with asyncio.timeout(seconds):
        return await awaitable


@pytest.mark.asyncio
async def test_a_timeout_around_record_raises_timeout_error():
    """record() lets an enclosing asyncio.timeout's own cancellation through, so the timeout reports its expiry."""
    fake = StoredWatcher("timeout", refused=1000)
    async with monitor_for(fake) as monitor:
        await withhold(monitor, fake, WatcherTimeoutError)
        with pytest.raises(TimeoutError):
            await within(0.5, monitor.record(REFUSED))
        assert "double-2" in monitor.unreported
        assert "double-2" not in monitor.reported
        assert monitor.late_attempts == monitor.unrecorded == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("first", ["cancel", "timeout"])
@pytest.mark.parametrize("ending", ["cancelled", "failed"])
async def test_record_keeps_the_call_claimed_until_its_cancelled_report_stops(first, ending):
    """A second cancellation while a report's cleanup runs does not release its call; the cancellation still propagates."""
    fake = StoredWatcher("timeout", stall="double-2", linger=ending)
    async with monitor_for(fake) as monitor:
        await withhold(monitor, fake, WatcherTimeoutError)
        recording = monitor.record(REFUSED)
        task = asyncio.create_task(within(0.3, recording) if first == "timeout" else recording)
        await asyncio.wait_for(fake.entered.wait(), 10)
        if first == "cancel":
            task.cancel()
        await asyncio.wait_for(fake.lingering.wait(), 10)
        task.cancel()
        await asyncio.sleep(0.1)
        assert not task.done()
        assert "double-2" in monitor.reported
        # Another record() meanwhile leaves the claimed call to the report still stopping.
        uploads = len(fake.uploads)
        await monitor.record(REFUSED)
        assert len(fake.uploads) == uploads
        fake.finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert "double-2" in monitor.unreported
        assert "double-2" not in monitor.reported
        assert monitor.late_attempts == ({} if ending == "cancelled" else {"double-2": 1})
        assert monitor.unrecorded == {}
