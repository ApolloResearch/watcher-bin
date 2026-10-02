"""Applied policy is checked before an application side effect."""

import asyncio
import json

import httpx
import pytest
from watcher_cline_bridge.enforcement import apply_policy, pending_messages

from watcher_sdk import AsyncWatcherClient, WatcherError

CALL = {"id": "native-call", "function": "write_file", "arguments": {"path": "marker"}}
MESSAGES = [{"role": "user", "content": "Write the marker after approval"}]


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "deny",
        "escalate",
        "deferred",
        "paused",
        "observe",
        "identity",
        "missing-judgment",
        "grading-error",
        "unknown-source",
        "http",
        "empty",
    ],
)
def test_execution_requires_complete_matching_approval(tmp_path, failure):
    """A real SDK response must pass every approval check before the marker is written."""
    marker = tmp_path / "side-effect"
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["mode"] == "full" and "require_recording" not in request.url.params
        assert "settings_overrides" not in body
        outcome = {
            "tool_use_id": CALL["id"],
            "decision": "allow",
            "judged_decision": "allow",
            "enforcement_mode": "enforce",
            "decision_source": "rule",
            "verdict": {},
            "latency_ms": 1,
        }
        if failure in {"deny", "escalate", "deferred"}:
            outcome["decision"] = failure
        if failure in {"paused", "observe"}:
            outcome["enforcement_mode"] = failure
        if failure == "identity":
            outcome["tool_use_id"] = "another-call"
        if failure == "missing-judgment":
            outcome.pop("judged_decision")
        if failure == "grading-error":
            outcome["decision_source"] = "grading_error"
        if failure == "unknown-source":
            outcome["decision_source"] = "unknown-stage"
        return httpx.Response(
            503 if failure == "http" else 200,
            json={"error": {"message": "fixture unavailable"}}
            if failure == "http"
            else []
            if failure == "empty"
            else [outcome],
        )

    async def execute():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, "native-session", MESSAGES, CALL)
            marker.write_text("executed")

    if failure is None:
        asyncio.run(execute())
        assert marker.read_text() == "executed"
    else:
        with pytest.raises((PermissionError, WatcherError, KeyError)):
            asyncio.run(execute())
        assert not marker.exists()
    assert len(requests) == 1
    assert requests[0]["messages"][-1]["tool_calls"][0]["id"] == CALL["id"]


def test_pending_response_cannot_execute(tmp_path):
    """An unreleased real SDK transport response leaves the actual side effect absent."""
    marker = tmp_path / "side-effect"

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def respond(request):
            entered.set()
            await release.wait()
            return httpx.Response(
                200,
                json=[
                    {
                        "tool_use_id": CALL["id"],
                        "decision": "allow",
                        "judged_decision": "allow",
                        "enforcement_mode": "enforce",
                        "decision_source": "rule",
                        "verdict": {},
                        "latency_ms": 1,
                    }
                ],
            )

        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:

            async def execute():
                await apply_policy(client, "native-session", MESSAGES, CALL)
                marker.write_text("executed")

            task = asyncio.create_task(execute())
            await asyncio.wait_for(entered.wait(), 5)
            assert not marker.exists() and not task.done()
            release.set()
            await task
        assert marker.read_text() == "executed"

    asyncio.run(scenario())


@pytest.mark.parametrize("shape", ["completed", "conflict", "duplicate", "empty-id"])
def test_invalid_native_identity_is_rejected(shape):
    history = pending_messages(MESSAGES, CALL)
    call = dict(CALL)
    if shape == "completed":
        history.append({"role": "tool", "tool_call_id": CALL["id"], "content": "already done"})
    if shape == "conflict":
        call["arguments"] = {"path": "another"}
    if shape == "duplicate":
        history.append(history[-1])
    if shape == "empty-id":
        call["id"] = ""
    with pytest.raises(ValueError):
        pending_messages(history, call)


def test_repeated_and_parallel_calls_preserve_native_ids():
    other = {**CALL, "id": "second-call"}
    history = [{"role": "assistant", "content": "", "tool_calls": [CALL, other]}]
    assert pending_messages(history, other) == history
    assert pending_messages(history, CALL) == history
    assert len(history) == 1


@pytest.mark.parametrize(
    "recorded,current",
    [
        ({"flag": False}, {"flag": 0}),
        ({"flag": True}, {"flag": 1}),
        ({"value": [False]}, {"value": [0]}),
        ({"value": 0}, {"value": 0.0}),
        ({"value": []}, {"value": ()}),
        ({"value": 1}, {"value": float("nan")}),
        ({"value": 1}, {"value": float("inf")}),
        ({"value": 1}, {1: "value"}),
    ],
)
def test_argument_identity_mismatch_cannot_write(tmp_path, recorded, current):
    """A mismatched native callback cannot reach a real write or an SDK request."""
    marker = tmp_path / "not-written"
    requests = []

    def respond(request):
        requests.append(request)
        raise AssertionError("Conflicting identities must fail before transport")

    history = pending_messages(MESSAGES, {**CALL, "arguments": recorded})

    async def execute():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, "native-session", history, {**CALL, "arguments": current})
            marker.write_text("unsafe write")

    with pytest.raises(ValueError):
        asyncio.run(execute())
    assert not marker.exists() and not requests


@pytest.mark.parametrize("cwd", [None, "/native/workspace"])
def test_native_cwd_is_preserved_without_inventing_one(cwd):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=[
                {
                    "tool_use_id": CALL["id"],
                    "decision": "allow",
                    "judged_decision": "allow",
                    "enforcement_mode": "enforce",
                    "decision_source": "rule",
                    "verdict": {},
                    "latency_ms": 1,
                }
            ],
        )

    async def check():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, "session", MESSAGES, CALL, cwd=cwd)

    asyncio.run(check())
    submitted = requests[0]["input"][0]
    if cwd is None:
        assert "cwd" not in submitted
    else:
        assert submitted["cwd"] == cwd
    assert "cwd" not in requests[0]["messages"][-1]["tool_calls"][0]


@pytest.mark.parametrize("mode", ["observe", "paused", "grading-failure-allow"])
def test_valid_configured_policy_preserves_native_dispatch(tmp_path, mode):
    marker = tmp_path / "effect"

    def respond(request):
        body = json.loads(request.content)
        assert "settings_overrides" not in body
        outcome = {
            "tool_use_id": CALL["id"],
            "decision": "allow" if mode == "grading-failure-allow" else "deferred",
            "judged_decision": "allow" if mode == "grading-failure-allow" else None if mode == "paused" else "deny",
            "enforcement_mode": "enforce" if mode == "grading-failure-allow" else mode,
            "decision_source": "grading_error"
            if mode == "grading-failure-allow"
            else "bypass"
            if mode == "paused"
            else "rule",
            "verdict": {},
            "latency_ms": 1,
        }
        if mode == "grading-failure-allow":
            outcome["grading_error"] = {"code": "timeout", "message": "Configured fixture timeout"}
        return httpx.Response(200, json=[outcome])

    async def execute():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, "configured", MESSAGES, CALL)
            marker.write_text("executed")

    asyncio.run(execute())
    assert marker.read_text() == "executed"
