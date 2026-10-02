"""Configured observe/enforce policy applied through the installed provider client."""

import asyncio

import httpx
import pytest
from watcher_cohere.monitoring import ApprovalRequired, Monitor, Withheld

from tests.test_monitoring import Decisions, callbacks, clients, invoke, start_history


class Configured(Decisions):
    """Retain native provider transport and vary only the local Watcher policy."""

    def __init__(self, mode="enforce", decision="allow", *, grading_failure=False):
        super().__init__()
        self.mode, self.decision, self.grading_failure = mode, decision, grading_failure

    async def watcher(self, request):
        response = await super().watcher(request)
        outcomes = response.json()
        for result in outcomes:
            result.update(
                decision=self.decision if self.mode == "enforce" else "deferred",
                judged_decision=None if self.mode == "paused" else self.decision,
                enforcement_mode=self.mode,
                decision_source="bypass"
                if self.mode == "paused"
                else "grading_error"
                if self.grading_failure
                else "rule",
            )
            if self.grading_failure:
                result["grading_error"] = {"code": "timeout", "message": "Fixture grader timeout"}
        return httpx.Response(200, json=outcomes)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["observe", "paused"])
async def test_same_monitor_preserves_application_dispatch_for_deferred(mode, tmp_path):
    transport = Configured(mode, "deny")
    provider, watcher = clients(transport)
    path = tmp_path / "effects"
    async with provider, watcher:
        await invoke(provider, Monitor(watcher, "deferred"), start_history(), callbacks(path))
    assert path.read_text().splitlines() == ["Paris", "Tokyo"]
    assert all("settings_overrides" not in body for body in transport.watcher_requests)


@pytest.mark.asyncio
async def test_configured_grading_failure_allow_executes(tmp_path):
    transport = Configured(grading_failure=True)
    provider, watcher = clients(transport)
    path = tmp_path / "effects"
    async with provider, watcher:
        await invoke(provider, Monitor(watcher, "fail-open"), start_history(), callbacks(path))
    assert path.read_text().splitlines() == ["Paris", "Tokyo"]


@pytest.mark.asyncio
async def test_unattended_escalation_blocks_entire_batch(tmp_path):
    transport = Configured(decision="escalate")
    provider, watcher = clients(transport)
    path = tmp_path / "effects"
    async with provider, watcher:
        with pytest.raises(ApprovalRequired):
            await invoke(provider, Monitor(watcher, "unattended"), start_history(), callbacks(path))
    assert not path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [True, False, "yes"])
async def test_application_approval_holds_tool_batch_and_requires_literal_true(approved, tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()
    path = tmp_path / "effects"

    async def decide(*, tool_use_id, tool_name, tool_input, outcome):
        assert tool_use_id == outcome.tool_use_id
        assert tool_name in {"weather", "time"}
        tool_input["city"] = "mutated"
        entered.set()
        await release.wait()
        return approved

    transport = Configured(decision="escalate")
    provider, watcher = clients(transport)
    async with provider, watcher:
        monitor = Monitor(watcher, "human", approval_callback=decide)
        task = asyncio.create_task(invoke(provider, monitor, start_history(), callbacks(path)))
        try:
            await asyncio.wait_for(entered.wait(), 3)
            assert not path.exists()
            assert not task.done()
        finally:
            release.set()
        if approved is True:
            await task
        else:
            with pytest.raises(Withheld):
                await task
    assert path.read_text().splitlines() == ["Paris", "Tokyo"] if approved is True else not path.exists()
