"""Native Cursor stdin/output contract without claiming installed Cursor dispatch."""

import asyncio
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from watcher_cursor.integration import run_hook as journal_event


@pytest.mark.parametrize("decision", ["allow", "deny", "missing-outcome", "identity-error", "http-error"])
def test_pre_tool_process_returns_only_verified_permission(tmp_path, monkeypatch, decision):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            outcome = {
                "tool_use_id": "wrong" if decision == "identity-error" else "call-a",
                "decision": "deny" if decision == "deny" else "allow",
                "judged_decision": "deny" if decision == "deny" else "allow",
                "decision_source": "rule",
                "enforcement_mode": "enforce",
                "verdict": {},
                "latency_ms": 1,
            }
            self.send_response(503 if decision == "http-error" else 200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {"error": {"message": "fixture failure"}}
                    if decision == "http-error"
                    else []
                    if decision == "missing-outcome"
                    else [outcome]
                ).encode()
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    monkeypatch.setenv("WATCHER_STATE_DIR", str(tmp_path))
    asyncio.run(
        journal_event(
            {"hook_event_name": "beforeSubmitPrompt", "conversation_id": "native-session", "prompt": "Read the fixture"}
        )
    )
    payload = {
        "hook_event_name": "preToolUse",
        "conversation_id": "native-session",
        "tool_use_id": "call-a",
        "tool_name": "Read",
        "tool_input": {"path": "fixture.txt"},
    }
    try:
        result = subprocess.run(
            [sys.executable, "-m", "watcher_cursor.pre_tool"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "WATCHER_URL": f"http://127.0.0.1:{server.server_port}",
                "WATCHER_API_KEY": "fixture",
                "WATCHER_TIMEOUT_SECONDS": "5",
            },
            timeout=20,
            check=False,
        )
        assert result.returncode == (0 if decision == "allow" else 2)
        assert json.loads(result.stdout)["permission"] == ("allow" if decision == "allow" else "deny")
        assert requests[0]["messages"][0]["role"] == "user"
        assert requests[0]["messages"][-1]["tool_calls"][0]["id"] == "call-a"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)


def test_denied_call_is_recorded_when_stop_flushes(tmp_path, monkeypatch):
    """A denied pending call needs no fabricated result to survive completion flush."""
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            enforcement = body.get("mode") == "full"
            outcomes = [
                {
                    "tool_use_id": call["tool_use_id"],
                    "decision": "deny" if enforcement else "deferred",
                    "judged_decision": "deny",
                    "decision_source": "rule",
                    "enforcement_mode": "enforce" if enforcement else "observe",
                    "verdict": {},
                    "latency_ms": 1,
                }
                for call in body["input"]
            ]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(outcomes).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    monkeypatch.setenv("WATCHER_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("WATCHER_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("WATCHER_API_KEY", "fixture")
    monkeypatch.setenv("WATCHER_TIMEOUT_SECONDS", "5")
    asyncio.run(
        journal_event(
            {"hook_event_name": "beforeSubmitPrompt", "conversation_id": "native-session", "prompt": "Read the fixture"}
        )
    )
    payload = {
        "hook_event_name": "preToolUse",
        "conversation_id": "native-session",
        "tool_use_id": "denied-call",
        "tool_name": "Read",
        "tool_input": {"path": "fixture.txt"},
    }
    try:
        denied = subprocess.run(
            [sys.executable, "-m", "watcher_cursor.pre_tool"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert denied.returncode == 2
        assert json.loads(denied.stdout)["permission"] == "deny"
        asyncio.run(journal_event({"hook_event_name": "stop", "conversation_id": "native-session"}))
        assert len(requests) == 3
        assert requests[1]["mode"] == "triage_only"
        assert requests[2]["input"] == []
        recorded = requests[2]["messages"]
        assert recorded[0]["role"] == "user"
        assert recorded[-1]["tool_calls"] == [
            {"id": "denied-call", "type": "function", "function": "Read", "arguments": {"path": "fixture.txt"}}
        ]
        assert all(message["role"] != "tool" for message in recorded)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)
