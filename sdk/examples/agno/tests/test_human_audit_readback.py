"""Bind human approval to stored trajectory evidence, including routine escalations."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest
from watcher_agno.monitoring import Monitor


def response(**fields):
    return SimpleNamespace(**fields, to_dict=lambda: deepcopy(fields))


class StoredAuditClient:
    """Model public responses with a real stored choice and a NULL display category."""

    def __init__(self, deny_threshold=11, *, corruption=None, before_upload=False):
        self.uploads: list[dict[str, Any]] = []
        self.category_queries = 0
        self.corruption = corruption
        self.before_upload = before_upload
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()
        self.failure: Exception | None = None
        self.decision: dict[str, Any] = {
            "tool_use_id": "pending",
            "tool_name": "write",
            "raw_tool_call": {"tool_name": "write", "tool_input": {"value": True}},
            "policy_decision": "escalate",
            "applied_decision": "escalate",
            "judged_decision": "escalate",
            "decision_source": "threshold" if deny_threshold == 11 else "policy_gateway",
            "enforcement_mode": "enforce",
            "flag_threshold": 0,
            "deny_threshold": deny_threshold,
            "tool_status": "pending",
            "human_decision": None,
            "human_decided_at": None,
            "grades": [] if deny_threshold == 11 else [{"tool_call_grade_id": "grade", "grade": {"score": 7}}],
        }
        self.original = deepcopy(self.decision)

    async def search_sessions(self, **kwargs):
        return response(total=1, sessions=[response(session_id="session", latest_trajectory_id="trajectory")])

    async def search_tool_calls(self, **kwargs):
        if kwargs.get("decision_categories"):
            self.category_queries += 1
            return response(total=0, tool_calls=[])
        return response(
            total=1,
            tool_calls=[
                response(tool_use_id="pending", tool_name="write", applied_decision="escalate", decision_category=None)
            ],
        )

    async def upload_tool_call_decisions_batch(self, *, decisions, **kwargs):
        self.started.set()
        await self.release.wait()
        if self.failure is not None:
            raise self.failure
        self.uploads.extend(deepcopy(decisions))
        assert len(decisions) == 1
        payload = decisions[0]
        assert (
            payload["policy_decision"] == payload["applied_decision"] == payload["decision_source"] == "not_evaluated"
        )
        for key in ("human_decision", "human_decided_at", "tool_status"):
            self.decision[key] = payload[key]
        return response(
            synced_count=1, synced_tool_use_ids=["pending"], failed_tool_use_ids=[], failed_tool_call_grade_ids=[]
        )

    async def get_trajectory(self, session_id, trajectory_id, view):
        assert (session_id, trajectory_id) == ("session", "trajectory")
        assert str(view) == "extended"
        call: dict[str, Any] = {"id": "pending", "type": "function", "function": "write", "arguments": {"value": True}}
        decision = deepcopy(self.decision)
        if self.corruption and (self.before_upload or self.uploads):
            if self.corruption == "call-id":
                call["id"] = "another"
            elif self.corruption == "call-name":
                call["function"] = "another"
            elif self.corruption == "call-type":
                call["type"] = "custom"
            elif self.corruption == "call-arguments":
                call["arguments"] = {"value": 1}
            elif self.corruption == "decision-id":
                decision["tool_use_id"] = "another"
            elif self.corruption == "decision-name":
                decision["tool_name"] = "another"
            elif self.corruption == "decision-arguments":
                decision["raw_tool_call"]["tool_input"] = {"value": 1}
            elif self.corruption == "human-choice":
                decision["human_decision"] = None
            elif self.corruption == "tool-status":
                decision["tool_status"] = "success"
            elif self.corruption == "evaluation":
                decision["applied_decision"] = "allow"
            elif self.corruption == "grades":
                decision["grades"] = []
            elif self.corruption == "scrub":
                return response(session_id=session_id, trajectory_id=trajectory_id, messages=[], tool_call_decisions={})
        return response(
            session_id=session_id,
            trajectory_id=trajectory_id,
            messages=[{"role": "assistant", "content": "", "tool_calls": [call]}],
            tool_call_decisions={"pending": decision},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("deny_threshold", [11, 8])
@pytest.mark.parametrize("approved", [False, True])
async def test_always_escalate_reads_the_stored_human_choice(deny_threshold, approved):
    client = StoredAuditClient(deny_threshold)
    monitor = Monitor(client, "always-ask")
    await monitor.report_human_decision("pending", "write", {"value": True}, approved=approved)
    assert client.category_queries == 0
    assert len(client.uploads) == 1
    assert client.decision["human_decision"] == ("allow" if approved else "deny")
    assert client.decision["tool_status"] == ("pending" if approved else "blocked")
    for key in ("policy_decision", "applied_decision", "judged_decision", "decision_source", "grades"):
        assert client.decision[key] == client.original[key]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption",
    [
        "call-id",
        "call-name",
        "call-type",
        "call-arguments",
        "decision-id",
        "decision-name",
        "decision-arguments",
        "human-choice",
        "tool-status",
        "evaluation",
        "grades",
        "scrub",
    ],
)
async def test_positive_upload_does_not_authorize_mismatching_stored_evidence(corruption):
    client = StoredAuditClient(8, corruption=corruption)
    monitor = Monitor(client, "mismatching-readback")
    effects = []
    with pytest.raises(RuntimeError):
        await monitor.report_human_decision("pending", "write", {"value": True}, approved=True)
        effects.append("executed")
    assert effects == []


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["call-type", "call-arguments", "decision-arguments"])
async def test_wrong_pending_identity_is_rejected_before_upload(corruption):
    client = StoredAuditClient(8, corruption=corruption, before_upload=True)
    with pytest.raises(RuntimeError):
        await Monitor(client, "wrong-pending").report_human_decision("pending", "write", {"value": True}, approved=True)
    assert client.uploads == []


@pytest.mark.asyncio
async def test_audit_failure_takes_priority_after_cancellation():
    client = StoredAuditClient(8)
    client.release.clear()
    client.failure = OSError("Audit unavailable after cancellation")
    task = asyncio.create_task(
        Monitor(client, "cancel-failure").report_human_decision("pending", "write", {"value": True}, approved=True)
    )
    await asyncio.wait_for(client.started.wait(), 1)
    task.cancel()
    client.release.set()
    with pytest.raises(OSError, match="Audit unavailable after cancellation"):
        await asyncio.wait_for(task, 1)
    assert client.uploads == []
