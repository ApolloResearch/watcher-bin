"""Public SDK and native exit-code contract; this does not execute the Windsurf IDE."""

import asyncio
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from watcher_windsurf.pre_tool_ephemeral import apply_policy

from watcher_sdk import AsyncWatcherClient, WatcherError

PAYLOAD = {
    "agent_action_name": "pre_run_command",
    "trajectory_id": "native-trajectory",
    "execution_id": "native-turn",
    "tool_info": {"command_line": "cat fixture.txt", "cwd": "/fixture"},
}


@pytest.mark.parametrize(
    "decision",
    [
        "allow",
        "deny",
        "escalate",
        "deferred",
        "observe",
        "paused",
        "wrong-id",
        "missing-judgment",
        "unknown-source",
        "http-error",
    ],
)
def test_ephemeral_action_requires_completed_allow(tmp_path, decision):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        body = {
            "tool_use_id": None,
            "decision": "allow",
            "judged_decision": "allow",
            "enforcement_mode": "enforce",
            "decision_source": "rule",
            "verdict": {},
            "latency_ms": 1,
        }
        if decision in {"deny", "escalate", "deferred"}:
            body["decision"] = decision
        if decision in {"observe", "paused"}:
            body["enforcement_mode"] = decision
        if decision == "wrong-id":
            body["tool_use_id"] = "invented"
        if decision == "missing-judgment":
            body.pop("judged_decision")
        if decision == "unknown-source":
            body["decision_source"] = "not-a-public-stage"
        return httpx.Response(
            503 if decision == "http-error" else 200,
            json={"error": {"message": "unavailable"}} if decision == "http-error" else body,
        )

    marker = tmp_path / "marker"

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, PAYLOAD)
            marker.write_text("allowed")

    if decision == "allow":
        asyncio.run(run())
    else:
        with pytest.raises((PermissionError, WatcherError, KeyError, ValueError, TypeError)):
            asyncio.run(run())
    assert marker.exists() == (decision == "allow")
    assert requests[0]["ephemeral"] is True and requests[0]["messages"] == []
    assert "external_ids" not in requests[0] and "tool_use_id" not in requests[0]["input"]
    assert requests[0]["input"]["tool_input"] == PAYLOAD["tool_info"]
    assert requests[0]["input"]["cwd"] == "/fixture"


def test_pending_ephemeral_response_cannot_release_action(tmp_path):
    marker = tmp_path / "marker"

    async def run():
        entered, release = asyncio.Event(), asyncio.Event()

        async def respond(request):
            entered.set()
            await release.wait()
            return httpx.Response(
                200,
                json={
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

            async def act():
                await apply_policy(client, PAYLOAD)
                marker.write_text("allowed")

            task = asyncio.create_task(act())
            await asyncio.wait_for(entered.wait(), 5)
            assert not task.done() and not marker.exists()
            release.set()
            await task
        assert marker.exists()

    asyncio.run(run())


@pytest.mark.parametrize(
    "event,arguments",
    [
        ("pre_read_code", {"file_path": "/fixture/file"}),
        ("pre_write_code", {"file_path": "/fixture/file", "edits": [{"old_string": "before", "new_string": "after"}]}),
        (
            "pre_mcp_tool_use",
            {
                "mcp_server_name": "fixture",
                "mcp_tool_name": "write",
                "mcp_tool_arguments": {"enabled": False, "count": 0},
            },
        ),
    ],
)
def test_documented_native_arguments_are_preserved(event, arguments):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "decision": "allow",
                "judged_decision": "allow",
                "enforcement_mode": "enforce",
                "decision_source": "rule",
                "verdict": {},
                "latency_ms": 1,
            },
        )

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, {"agent_action_name": event, "tool_info": arguments})

    asyncio.run(run())
    assert requests[0]["input"]["tool_name"] == event
    assert json.dumps(requests[0]["input"]["tool_input"], sort_keys=True) == json.dumps(arguments, sort_keys=True)
    assert "cwd" not in requests[0]["input"]


@pytest.mark.parametrize("allowed,response_delay", [(True, 0), (False, 0), (True, 11)])
def test_pre_hook_process_uses_exit_two_veto(monkeypatch, allowed, response_delay):
    """A valid slow full grade can complete under the default request budget."""
    monkeypatch.delenv("WATCHER_TIMEOUT_SECONDS", raising=False)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert body["ephemeral"] is True
            assert body["mode"] == "full"
            # This delay exercises a real HTTP deadline, not thread ordering.
            threading.Event().wait(response_delay)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "decision": "allow" if allowed else "deny",
                        "judged_decision": "allow" if allowed else "deny",
                        "enforcement_mode": "enforce",
                        "decision_source": "rule",
                        "verdict": {},
                        "latency_ms": 1,
                    }
                ).encode()
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        result = subprocess.run(
            [sys.executable, "-m", "watcher_windsurf.pre_tool_ephemeral"],
            input=json.dumps(PAYLOAD),
            capture_output=True,
            text=True,
            env={**os.environ, "WATCHER_URL": f"http://127.0.0.1:{server.server_port}", "WATCHER_API_KEY": "fixture"},
            timeout=30,
            check=False,
        )
        assert result.returncode == (0 if allowed else 2)
        assert result.stdout == ""
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)


@pytest.mark.parametrize(
    "payload",
    [
        {"agent_action_name": "post_write_code", "tool_info": {"file_path": "/fixture"}},
        {"agent_action_name": "pre_run_command", "tool_info": {"cwd": "/fixture"}},
        {"agent_action_name": "pre_run_command", "tool_info": {"cwd": "/fixture", "command_line": 0}},
        {
            "agent_action_name": "pre_mcp_tool_use",
            "tool_info": {"mcp_server_name": "fixture", "mcp_tool_arguments": {}},
        },
        {
            "agent_action_name": "pre_write_code",
            "tool_info": {"file_path": "/fixture", "edits": [{"old_string": "before", "new_string": 7}]},
        },
        {
            "agent_action_name": "pre_mcp_tool_use",
            "tool_info": {
                "mcp_server_name": "fixture",
                "mcp_tool_name": "write",
                "mcp_tool_arguments": {"value": float("nan")},
            },
        },
    ],
)
def test_incomplete_or_post_action_cannot_reach_transport_or_side_effect(tmp_path, payload):
    requests = []
    marker = tmp_path / "not-written"

    def respond(request):
        requests.append(request)
        raise AssertionError("Invalid actions must fail before transport")

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, payload)
            marker.write_text("unsafe action")

    with pytest.raises(ValueError):
        asyncio.run(run())
    assert not marker.exists() and not requests
