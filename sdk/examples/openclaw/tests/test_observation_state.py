"""Stress real SDK observation with long histories and persistent retry progress."""

import asyncio
import json
import os
import time
from typing import Any

import httpx
import pytest
from filelock import FileLock
from watcher_openclaw_bridge import checkpoint as module
from watcher_openclaw_bridge.checkpoint import call_fingerprint, state_path
from watcher_openclaw_bridge.monitoring import observe

from watcher_sdk import AsyncWatcherClient, WatcherError


def history(count):
    """Each new call has its own earlier context, so it cannot share one grading batch."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": "Work through these tools"}]
    for index in range(count):
        messages += [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": f"call-{index}", "function": "tool", "arguments": {"n": index}}],
            },
            {"role": "tool", "tool_call_id": f"call-{index}", "content": f"result-{index}"},
        ]
    return messages + [{"role": "assistant", "content": "Final answer"}]


def outcome(call):
    return {
        "tool_use_id": call["tool_use_id"],
        "decision": "deferred",
        "judged_decision": "allow",
        "enforcement_mode": "observe",
        "decision_source": "rule",
        "verdict": {},
        "latency_ms": 1,
    }


def test_forty_calls_keep_final_snapshot_before_bounded_partial_grading(tmp_path, record_testsuite_property):
    requests = []
    delay = 0.1
    budget_seconds = 2
    checkpoint = tmp_path / "state.json"
    messages = history(40)

    async def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if body["input"]:
            await asyncio.sleep(delay)
        return httpx.Response(200, json=[outcome(c) for c in body["input"]])

    async def exercise():
        nonlocal delay
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await observe(client, "native:long", history(1), checkpoint_path=checkpoint)
            requests.clear()
            started = time.monotonic()
            with pytest.raises(TimeoutError):
                await observe(
                    client, "native:long", messages, checkpoint_path=checkpoint, budget_seconds=budget_seconds
                )
            elapsed = time.monotonic() - started
            assert elapsed < budget_seconds + 3
            assert requests[0]["input"] == [] and requests[0]["messages"] == messages
            completed = set(json.loads(checkpoint.read_text()))
            record_testsuite_property("partial_observation_elapsed_seconds", elapsed)
            record_testsuite_property("partial_observation_budget_seconds", budget_seconds)
            record_testsuite_property("partial_observation_completed_calls", len(completed))
            record_testsuite_property("partial_observation_new_completed_calls", len(completed) - 1)
            assert 1 < len(completed) < 40
            for request in requests[1:]:
                call = request["input"][0]
                assert not any(m.get("tool_call_id") == call["tool_use_id"] for m in request["messages"])
                assert request["messages"][-1]["tool_calls"][0]["id"] == call["tool_use_id"]
            requests.clear()
            delay = 0
            await observe(client, "native:long", messages, checkpoint_path=checkpoint)
            assert len(json.loads(checkpoint.read_text())) == 40
            resumed = [
                {"id": c["tool_use_id"], "function": c["tool_name"], "arguments": c["tool_input"]}
                for r in requests[1:]
                for c in r["input"]
            ]
            assert all(call_fingerprint(c) not in completed for c in resumed)
            assert len(resumed) == 40 - len(completed)
            requests.clear()
            await observe(client, "native:long", messages, checkpoint_path=checkpoint)
            assert len(requests) == 1 and requests[0]["input"] == []

    asyncio.run(exercise())


def test_snapshot_failure_does_not_advance_or_grade(tmp_path):
    checkpoint = tmp_path / "state.json"
    requests = []

    async def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(503, json={"error": {"message": "unavailable"}})

    async def exercise():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            with pytest.raises(WatcherError):
                await observe(client, "native:s", history(1), checkpoint_path=checkpoint)

    asyncio.run(exercise())
    assert len(requests) == 1 and requests[0]["input"] == [] and not checkpoint.exists()


def test_reset_progress_replays_calls_after_remote_session_loss(tmp_path):
    """A snapshot acknowledgment cannot detect remote deletion; reset permits replay."""
    checkpoint = tmp_path / "state.json"
    recorded_calls = set()

    async def respond(request):
        body = json.loads(request.content)
        recorded_calls.update(call["tool_use_id"] for call in body["input"])
        return httpx.Response(200, json=[outcome(c) for c in body["input"]])

    async def exercise():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await observe(client, "native:s", history(2), checkpoint_path=checkpoint)
            assert recorded_calls == {"call-0", "call-1"}
            recorded_calls.clear()
            await observe(client, "native:s", history(2), checkpoint_path=checkpoint)
            assert not recorded_calls, "A transcript receipt cannot reveal missing remote judgments"
            checkpoint.unlink()
            await observe(client, "native:s", history(2), checkpoint_path=checkpoint)
            assert recorded_calls == {"call-0", "call-1"}

    asyncio.run(exercise())


def test_busy_checkpoint_still_attempts_latest_snapshot(tmp_path):
    checkpoint = tmp_path / "state.json"
    requests = []

    async def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=[])

    async def exercise():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            with FileLock(str(checkpoint) + ".lock"), pytest.raises(ValueError, match="Another observation"):
                await observe(client, "native:s", history(1), checkpoint_path=checkpoint)

    asyncio.run(exercise())
    assert len(requests) == 1 and requests[0]["messages"][-1]["content"] == "Final answer"


def test_checkpoint_partition_and_private_content(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHER_OBSERVATION_STATE_DIR", str(tmp_path))
    paths = {
        state_path("session", url, key)
        for url, key in [("https://one/api", "secret"), ("https://two/api", "secret"), ("https://one/api", "another")]
    }
    assert len(paths) == 3
    assert all("secret" not in str(path) and "session" not in str(path) for path in paths)
    assert call_fingerprint({"id": "x", "function": "t", "arguments": {"flag": False}}) != call_fingerprint(
        {"id": "x", "function": "t", "arguments": {"flag": 0}}
    )


@pytest.mark.parametrize("budget", [0, -1, 41, float("inf"), float("nan")])
def test_invalid_budgets_do_not_contact_watcher(budget):
    with pytest.raises(ValueError):
        asyncio.run(observe(None, "native:s", [], budget_seconds=budget))


def test_concurrent_callbacks_keep_snapshot_and_resume_new_calls(tmp_path):
    checkpoint = tmp_path / "state.json"
    requests = []

    async def exercise():
        entered = asyncio.Event()
        release = asyncio.Event()

        async def respond(request):
            body = json.loads(request.content)
            requests.append(body)
            if body["input"] and not release.is_set():
                entered.set()
                await release.wait()
            return httpx.Response(200, json=[outcome(c) for c in body["input"]])

        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            first = asyncio.create_task(observe(client, "native:s", history(1), checkpoint_path=checkpoint))
            await asyncio.wait_for(entered.wait(), 5)
            with pytest.raises(ValueError, match="Another observation"):
                await observe(client, "native:s", history(2), checkpoint_path=checkpoint)
            assert requests[-1]["input"] == [] and requests[-1]["messages"] == history(2)
            release.set()
            await first
            requests.clear()
            await observe(client, "native:s", history(2), checkpoint_path=checkpoint)
            assert [c["tool_use_id"] for r in requests for c in r["input"]] == ["call-1"]

    asyncio.run(exercise())


def test_stalled_checkpoint_io_is_killed_and_reaped(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    os.mkfifo(path)
    workers = []
    spawn = asyncio.create_subprocess_exec

    async def capture(*args, **kwargs):
        process = await spawn(*args, **kwargs)
        workers.append(process)
        return process

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", capture)

    async def respond(request):
        assert json.loads(request.content)["input"] == []
        return httpx.Response(200, json=[])

    async def exercise():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            started = time.monotonic()
            with pytest.raises(TimeoutError):
                await observe(client, "native:s", history(1), checkpoint_path=path, budget_seconds=0.2)
            assert time.monotonic() - started < 3

    asyncio.run(exercise())
    assert len(workers) == 1 and workers[0].returncode is not None
    with pytest.raises(ProcessLookupError):
        os.kill(workers[0].pid, 0)
    with FileLock(str(path) + ".lock", timeout=0):
        pass


@pytest.mark.parametrize("initial_policy", ["paused", "grading_error"])
def test_unjudged_calls_remain_eligible_after_policy_recovers(tmp_path, initial_policy):
    """A paused or failed evaluation must not permanently suppress a later judgment."""
    checkpoint = tmp_path / "state.json"
    requests = []
    policy = initial_policy

    async def respond(request):
        body = json.loads(request.content)
        assert "settings_overrides" not in body
        requests.append(body)
        results = []
        for call in body["input"]:
            result = outcome(call)
            if policy == "paused":
                result.update(
                    enforcement_mode="paused", decision="deferred", judged_decision=None, decision_source="bypass"
                )
            elif policy == "grading_error":
                result.update(
                    enforcement_mode="enforce",
                    decision="allow",
                    judged_decision="allow",
                    decision_source="grading_error",
                )
                result["grading_error"] = {"code": "timeout", "message": "fixture timeout"}
            results.append(result)
        return httpx.Response(200, json=results)

    async def exercise():
        nonlocal policy
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await observe(client, "resumed-session", history(1), checkpoint_path=checkpoint)
            assert json.loads(checkpoint.read_text()) == []
            assert [call["tool_use_id"] for request in requests for call in request["input"]] == ["call-0"]
            policy = "observe"
            requests.clear()
            await observe(client, "resumed-session", history(1), checkpoint_path=checkpoint)
            assert len(json.loads(checkpoint.read_text())) == 1
            assert [call["tool_use_id"] for request in requests for call in request["input"]] == ["call-0"]
            requests.clear()
            await observe(client, "resumed-session", history(1), checkpoint_path=checkpoint)
            assert len(requests) == 1 and requests[0]["input"] == []

    asyncio.run(exercise())
