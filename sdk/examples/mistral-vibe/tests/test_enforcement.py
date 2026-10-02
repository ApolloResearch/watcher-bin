"""Ephemeral approval must complete before a local side effect; no recording is claimed."""

import asyncio
import json

import httpx
import pytest
from watcher_mistral_vibe.enforcement import apply_policy

from watcher_sdk import AsyncWatcherClient, WatcherError


@pytest.mark.parametrize("call_id", [None, "native-call"])
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
        "bypass",
        "http",
        "transport",
        "empty",
    ],
)
def test_ephemeral_decision_controls_execution_without_a_recording_receipt(tmp_path, monkeypatch, call_id, failure):
    monkeypatch.setenv("WATCHER_EPHEMERAL_PRE_TOOL", "1")
    marker = tmp_path / "executed"
    calls = []
    call = {"function": "read_file", "arguments": {"path": "fixture.txt"}}
    if call_id is not None:
        call["id"] = call_id

    async def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body["ephemeral"] is True and body["mode"] == "full"
        assert isinstance(body["input"], dict)
        assert "require_recording" not in request.url.params
        assert "settings_overrides" not in body
        assert body["input"].get("tool_use_id") == call_id
        if failure == "transport":
            raise httpx.ReadTimeout("Fixture transport error", request=request)
        outcome = {
            "tool_use_id": call_id,
            "decision": "allow",
            "judged_decision": "allow",
            "enforcement_mode": "enforce",
            "decision_source": "rule",
            "verdict": {},
            "latency_ms": 1,
        }
        if failure in {"deny", "escalate", "deferred"}:
            outcome["decision"] = failure
        elif failure in {"paused", "observe"}:
            outcome["enforcement_mode"] = failure
        elif failure == "identity":
            outcome["tool_use_id"] = "a-different-call"
        elif failure == "missing-judgment":
            outcome.pop("judged_decision")
        elif failure in {"grading-error", "bypass"}:
            outcome["decision_source"] = "grading_error" if failure == "grading-error" else "bypass"
        return httpx.Response(503 if failure == "http" else 200, json=[] if failure == "empty" else outcome)

    async def execute():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, "native-session", [{"role": "user", "content": "Read fixture.txt"}], call)
            marker.write_text("executed")

    if failure is None:
        asyncio.run(execute())
        assert marker.read_text() == "executed"
    else:
        with pytest.raises((PermissionError, WatcherError, httpx.HTTPError)):
            asyncio.run(execute())
        assert not marker.exists()
    assert len(calls) == 1


def test_ephemeral_veto_requires_explicit_operator_opt_in(monkeypatch):
    monkeypatch.delenv("WATCHER_EPHEMERAL_PRE_TOOL", raising=False)

    async def respond(request):
        pytest.fail("Disabled ephemeral integration must not send a request")

    async def execute():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, "native-session", [], {"function": "read_file", "arguments": {}})

    with pytest.raises(PermissionError):
        asyncio.run(execute())


def test_pending_ephemeral_response_has_no_side_effect(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHER_EPHEMERAL_PRE_TOOL", "1")
    marker = tmp_path / "executed"

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def respond(request):
            entered.set()
            await release.wait()
            return httpx.Response(
                200,
                json={
                    "tool_use_id": None,
                    "decision": "allow",
                    "judged_decision": "allow",
                    "enforcement_mode": "enforce",
                    "decision_source": "rule",
                    "verdict": {},
                    "latency_ms": 1,
                },
            )

        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:

            async def execute():
                await apply_policy(client, "native-session", [], {"function": "read_file", "arguments": {}})
                marker.write_text("executed")

            task = asyncio.create_task(execute())
            await asyncio.wait_for(entered.wait(), 5)
            assert not marker.exists() and not task.done()
            release.set()
            await task
        assert marker.read_text() == "executed"

    asyncio.run(scenario())
