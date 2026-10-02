"""A returned human choice finishes its bounded audit before cancellation propagates."""

import asyncio
from types import SimpleNamespace

import pytest
from watcher_vercel_ai_bridge.monitoring import Monitor


def value(**fields):
    """Model a public SDK response; this suite tests cancellation, not server storage."""
    return SimpleNamespace(**fields, to_dict=lambda: fields)


class AuditClient:
    """Hold the upload in flight so cancellation and completion order are explicit."""

    def __init__(self, arguments=None):
        self.arguments = {"path": "output"} if arguments is None else arguments
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.uploads = []
        self.confirmed = False
        self.active = False

    async def search_sessions(self, **kwargs):
        return value(total=1, sessions=[value(session_id="session", latest_trajectory_id="trajectory")])

    async def search_tool_calls(self, **kwargs):
        category = kwargs.get("decision_categories")
        if category:
            assert self.uploads
            self.confirmed = True
        return value(
            total=1,
            tool_calls=[
                value(
                    tool_use_id="pending",
                    tool_name="write",
                    applied_decision="escalate",
                    decision_category=category[0] if category else None,
                )
            ],
        )

    async def get_trajectory(self, session_id, trajectory_id, view):
        assert str(view) == "extended"
        self.confirmed = bool(self.uploads)
        reported = self.uploads[0] if self.uploads else {}
        call = {"id": "pending", "type": "function", "function": "write", "arguments": self.arguments}
        decision = {
            "tool_use_id": "pending",
            "tool_name": "write",
            "raw_tool_call": {"tool_name": "write", "tool_input": self.arguments},
            "policy_decision": "escalate",
            "applied_decision": "escalate",
            "judged_decision": "escalate",
            "decision_source": "policy_gateway",
            "grades": [],
            "tool_status": reported.get("tool_status", "pending"),
            "human_decision": reported.get("human_decision"),
            "human_decided_at": reported.get("human_decided_at"),
        }
        return value(
            session_id=session_id,
            trajectory_id=trajectory_id,
            messages=[{"role": "assistant", "content": "", "tool_calls": [call]}],
            tool_call_decisions={"pending": decision},
        )

    async def upload_tool_call_decisions_batch(self, *, decisions, **kwargs):
        self.active = True
        self.started.set()
        try:
            await self.release.wait()
            self.uploads.extend(decisions)
            return value(
                synced_count=1, synced_tool_use_ids=["pending"], failed_tool_use_ids=[], failed_tool_call_grade_ids=[]
            )
        finally:
            self.active = False


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [False, True])
@pytest.mark.parametrize("cancellations", [1, 2])
async def test_supplied_choice_is_uploaded_and_read_back_before_cancellation(approved, cancellations):
    client = AuditClient()
    monitor = Monitor(client, "audit-cancellation")
    effects = []

    async def execute_after_audit():
        await monitor.report_human_decision("pending", "write", {"path": "output"}, approved=approved)
        effects.append("tool executed")

    task = asyncio.create_task(execute_after_audit())
    await asyncio.wait_for(client.started.wait(), 1)
    try:
        for _ in range(cancellations):
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done(), "Cancellation discarded the accepted choice before its audit completed"
        assert client.uploads == [] and effects == []
    finally:
        client.release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)
    assert client.confirmed and not client.active and effects == []
    assert len(client.uploads) == 1
    assert client.uploads[0]["human_decision"] == ("allow" if approved else "deny")
    assert client.uploads[0]["tool_status"] == ("pending" if approved else "blocked")


@pytest.mark.asyncio
async def test_cancelled_reporting_keeps_its_deadline_and_never_releases_execution():
    client = AuditClient({})
    monitor = Monitor(client, "audit-deadline")
    monitor.human_audit_timeout = 0.05
    task = asyncio.create_task(monitor.report_human_decision("pending", "write", {}, approved=True))
    await asyncio.wait_for(client.started.wait(), 1)
    task.cancel()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(task, 1)
    assert client.uploads == [] and not client.confirmed and not client.active


@pytest.mark.asyncio
async def test_audit_lookup_failure_propagates_without_authorizing_execution(
    monkeypatch: pytest.MonkeyPatch,
):
    client = AuditClient()

    async def fail(**kwargs):
        raise OSError("Audit unavailable")

    monkeypatch.setattr(client, "search_sessions", fail)
    with pytest.raises(OSError, match="Audit unavailable"):
        await Monitor(client, "audit-error").report_human_decision("pending", "write", {}, approved=True)
    assert client.uploads == [] and not client.active


@pytest.mark.asyncio
async def test_waiting_for_human_choice_stays_cancellable_without_an_audit():
    client = AuditClient()
    entered = asyncio.Event()

    async def decide(**kwargs):
        entered.set()
        await asyncio.Event().wait()

    async def escalate(*args, **kwargs):
        return value(
            tool_use_id="pending",
            decision="escalate",
            judged_decision="escalate",
            enforcement_mode="enforce",
            decision_source="rule",
        )

    client.pre_tool_use_hook = escalate
    monitor = Monitor(client, "undecided", approval_callback=decide)
    history = [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "pending", "function": "write", "arguments": {}}]}
    ]
    task = asyncio.create_task(monitor.before_transcript(history, "pending", "write", {}))
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)
    assert not client.started.is_set() and client.uploads == []
