"""Prove actual native requests cannot reach client-tool side effects without approval."""

import asyncio
import json
from copy import deepcopy

import httpx
import pytest
from watcher_cohere.monitoring import Monitor, RecordingFailed, Withheld, run_turn

from tests import test_integration as native
from watcher_sdk import WatcherError


@pytest.fixture(autouse=True)
def private_gateway_keys(monkeypatch):
    monkeypatch.setenv("PORTKEY_VIRTUAL_KEY", "fixture-virtual-key")
    monkeypatch.setenv("HELICONE_API_KEY", "fixture-gateway-key")


class Decisions(native.Transport):
    """Serve native model responses and deterministic public Watcher HTTP outcomes."""

    def __init__(self, outcome="allow"):
        super().__init__([tool_reply(), text_reply()])
        self.outcome = outcome

    async def watcher(self, request):
        payload = json.loads(request.content)
        self.watcher_requests.append(payload)
        self.started.set()
        await self.release.wait()
        assert "require_recording" not in request.url.params
        if self.outcome == "post_record_failure" and not payload["input"]:
            return httpx.Response(503, json={"detail": "fixture post-execution recording failure"})
        if self.outcome == "transport":
            raise httpx.ConnectError("fixture transport failure", request=request)
        if self.outcome == "timeout":
            raise httpx.ReadTimeout("fixture timeout", request=request)
        if self.outcome in ("recording_failure", "locked_override"):
            return httpx.Response(
                503 if self.outcome == "recording_failure" else 422, json={"detail": "fixture refusal"}
            )
        outcomes = []
        for item in payload["input"]:
            value = {
                "decision": "allow",
                "judged_decision": "allow",
                "decision_source": "rule",
                "enforcement_mode": "enforce",
                "verdict": {},
                "latency_ms": 1,
                "tool_use_id": item["tool_use_id"],
            }
            if self.outcome in ("deny", "escalate", "deferred"):
                value["decision"] = self.outcome
                value["judged_decision"] = "deny"
            elif self.outcome == "observe":
                value["enforcement_mode"] = "observe"
            elif self.outcome == "paused":
                value.update(
                    decision="deferred",
                    enforcement_mode="paused",
                    decision_source="not_evaluated",
                    judged_decision=None,
                )
            elif self.outcome == "wrong_id":
                value["tool_use_id"] = "unrelated-call"
            elif self.outcome == "missing_id":
                del value["tool_use_id"]
            elif self.outcome == "missing_judgment":
                del value["judged_decision"]
            elif self.outcome == "grading_error":
                value["grading_error"] = {"code": "grader_failed", "message": "fixture failure"}
            outcomes.append(value)
        if self.outcome == "incomplete":
            outcomes = []
        if self.outcome == "second_denied" and len(outcomes) > 1:
            outcomes[1].update(decision="deny", judged_decision="deny")
        headers = {} if self.outcome == "missing_recording" else {"X-Watcher-Recording": "complete"}
        return httpx.Response(200, json=outcomes, headers=headers)


def clients(transport):
    return native.clients(transport)


def start_history():
    return [{"role": "user", "content": "Find weather in Paris and Tokyo."}]


def tool_reply():
    return native.reply({"role": "assistant", "content": None, "tool_calls": deepcopy(native.CALLS)}, "tool_calls")


def text_reply():
    return native.reply({"role": "assistant", "content": "Finished."})


async def invoke(provider, monitor, history, functions):
    return await run_turn(
        provider, monitor, model="fixture-model", messages=history, functions=functions, tools=native.TOOLS
    )


async def observe(provider, observation):
    return await native.complete(
        provider, observation, model="fixture-model", messages=start_history(), tools=native.TOOLS
    )


def callbacks(path):
    async def execute(*, city):
        with path.open("a") as stream:
            stream.write(city + "\n")
        return {"city": city, "value": "fixture"}

    return {"weather": execute, "time": execute}


@pytest.mark.asyncio
async def test_native_allow_executes_and_records_results_and_final_answer(tmp_path):
    transport = Decisions()
    provider, watcher = clients(transport)
    path = tmp_path / "effects"
    async with provider, watcher:
        monitor = Monitor(watcher, "enforce-session")
        history = await invoke(provider, monitor, start_history(), callbacks(path))
        history = await invoke(provider, monitor, history, callbacks(path))
    assert path.read_text().splitlines() == ["Paris", "Tokyo"]
    before, results, final = transport.watcher_requests
    assert before["mode"] == "full"
    assert "settings_overrides" not in before
    assert before["external_ids"] == final["external_ids"] == {"other": "enforce-session"}
    assert not any(message["role"] == "tool" for message in before["messages"])
    assert [row["tool_call_id"] for row in results["messages"] if row["role"] == "tool"] == [
        item["tool_use_id"] for item in before["input"]
    ]
    assert final["messages"][:-1] == results["messages"]
    assert final["input"] == []
    assert "Finished." in str(final["messages"][-1]["content"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [
        "deny",
        "escalate",
        "deferred",
        "observe",
        "paused",
        "wrong_id",
        "missing_id",
        "missing_judgment",
        "grading_error",
        "incomplete",
        "transport",
        "timeout",
        "recording_failure",
        "locked_override",
        "second_denied",
    ],
)
async def test_native_refusal_or_incomplete_decision_prevents_all_side_effects(tmp_path, outcome):
    transport = Decisions(outcome)
    provider, watcher = clients(transport)
    path = tmp_path / "effects"
    async with provider, watcher:
        with pytest.raises((Withheld, WatcherError, ValueError)):
            await invoke(provider, Monitor(watcher, "blocked-session"), start_history(), callbacks(path))
    assert not path.exists()
    assert len(transport.provider_requests) == 1


@pytest.mark.asyncio
async def test_native_tool_waits_while_monitor_decision_is_pending(tmp_path):
    transport = Decisions()
    transport.release.clear()
    provider, watcher = clients(transport)
    path = tmp_path / "effects"
    async with provider, watcher:
        task = asyncio.create_task(
            invoke(provider, Monitor(watcher, "pending-session"), start_history(), callbacks(path))
        )
        try:
            await asyncio.wait_for(transport.started.wait(), 3)
            assert not task.done()
            assert not path.exists()
        finally:
            transport.release.set()
        await task
    assert path.read_text().splitlines() == ["Paris", "Tokyo"]


@pytest.mark.asyncio
async def test_observation_remains_independent_of_deny_judgment(tmp_path):
    transport = native.Transport([tool_reply()])
    transport.release.clear()
    provider, watcher = clients(transport)
    path = tmp_path / "effects"
    async with provider, watcher:
        observation = native.Observation(watcher, "observe-session")
        response = await observe(provider, observation)
        assert response is not None
        await callbacks(path)["weather"](city="Paris")
        assert path.read_text() == "Paris\n"
        transport.release.set()
        await observation.flush()
        assert observation.errors == []
        assert len(observation.judgments) == 2


@pytest.mark.asyncio
async def test_same_native_identity_cannot_execute_twice(tmp_path):
    transport = Decisions()
    transport.responses = iter([tool_reply(), tool_reply()])
    provider, watcher = clients(transport)
    path = tmp_path / "effects"
    async with provider, watcher:
        monitor = Monitor(watcher, "repeated-session")
        await invoke(provider, monitor, start_history(), callbacks(path))
        with pytest.raises(Withheld, match="Repeated execution"):
            await invoke(provider, monitor, start_history(), callbacks(path))
    assert path.read_text().splitlines() == ["Paris", "Tokyo"]


@pytest.mark.asyncio
async def test_new_native_ids_allow_repeated_tool_names_after_results(tmp_path):
    transport = Decisions()
    second = tool_reply()
    for call, key in zip(second["message"]["tool_calls"], ["call_c", "call_d"], strict=True):
        call["id"] = key
    transport.responses = iter([tool_reply(), second, text_reply()])
    provider, watcher = clients(transport)
    path = tmp_path / "effects"
    async with provider, watcher:
        monitor = Monitor(watcher, "fresh-repeat-session")
        history = await invoke(provider, monitor, start_history(), callbacks(path))
        history = await invoke(provider, monitor, history, callbacks(path))
        await invoke(provider, monitor, history, callbacks(path))
    assert path.read_text().splitlines() == ["Paris", "Tokyo", "Paris", "Tokyo"]
    grades = [request for request in transport.watcher_requests if request["input"]]
    assert len(grades) == 2
    assert {item["tool_use_id"] for item in grades[0]["input"]}.isdisjoint(
        {item["tool_use_id"] for item in grades[1]["input"]}
    )
    assert transport.watcher_requests[-1]["messages"][:-1] == transport.watcher_requests[-2]["messages"]


@pytest.mark.asyncio
async def test_incomplete_native_response_cannot_execute_any_tool(tmp_path):
    transport = Decisions()
    response = tool_reply()
    response["finish_reason"] = "MAX_TOKENS"
    transport.responses = iter([response])
    provider, watcher = clients(transport)
    path = tmp_path / "effects"
    async with provider, watcher:
        with pytest.raises((Withheld, WatcherError, ValueError)):
            await invoke(provider, Monitor(watcher, "incomplete-provider"), start_history(), callbacks(path))
    assert not path.exists()
    assert transport.watcher_requests == []


@pytest.mark.asyncio
async def test_record_failure_preserves_results_for_retry_without_dispatch(tmp_path):
    transport = Decisions("post_record_failure")
    provider, watcher = clients(transport)
    path = tmp_path / "effects"
    async with provider, watcher:
        monitor = Monitor(watcher, "record-recovery")
        with pytest.raises(RecordingFailed) as raised:
            await invoke(provider, monitor, start_history(), callbacks(path))
        failure = raised.value
        assert [row["tool_call_id"] for row in failure.messages if row["role"] == "tool"] == [
            item["tool_use_id"] for item in transport.watcher_requests[0]["input"]
        ]
        assert path.read_text().splitlines() == ["Paris", "Tokyo"]
        transport.outcome = "allow"
        await monitor.record(failure.messages)
        await invoke(provider, monitor, failure.history, callbacks(path))
    assert path.read_text().splitlines() == ["Paris", "Tokyo"]
    assert all(request["input"] == [] for request in transport.watcher_requests[1:])
    assert "Finished." in str(transport.watcher_requests[-1]["messages"][-1]["content"])


@pytest.mark.asyncio
async def test_unknown_native_tool_is_recorded_without_execution(tmp_path):
    transport = Decisions()
    response = tool_reply()
    response["message"]["tool_calls"][0]["function"]["name"] = "unregistered_tool"
    transport.responses = iter([response])
    provider, watcher = clients(transport)
    path = tmp_path / "effects"
    async with provider, watcher:
        with pytest.raises(Withheld, match="Unregistered tool"):
            await invoke(provider, Monitor(watcher, "unknown-tool"), start_history(), callbacks(path))
    assert not path.exists()
    assert len(transport.watcher_requests) == 1
    assert transport.watcher_requests[0]["input"] == []
    assert transport.watcher_requests[0]["messages"][-1]["tool_calls"][0]["function"] == "unregistered_tool"
