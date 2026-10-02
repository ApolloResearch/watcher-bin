"""Exercise a native runtime and the installed SDK together over loopback HTTP only."""

import json
import os
import subprocess
import sys
import threading
import time
from contextlib import suppress
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from tests.test_integration import CALLS, response


def _audit_trajectory(
    calls: list[dict[str, Any]], records: dict[str, dict[str, Any]], session_id: str
) -> dict[str, Any]:
    """Model public stored decision detail independently of display categories."""
    decisions = {}
    for call in calls:
        report = records.get(call["tool_use_id"], {})
        decisions[call["tool_use_id"]] = {
            "tool_use_id": call["tool_use_id"],
            "tool_name": call["tool_name"],
            "raw_tool_call": {"tool_name": call["tool_name"], "tool_input": deepcopy(call["tool_input"])},
            "policy_decision": "escalate",
            "applied_decision": "escalate",
            "judged_decision": "escalate",
            "decision_source": "policy_gateway",
            "grades": [],
            "tool_status": report.get("tool_status", "pending"),
            "human_decision": report.get("human_decision"),
            "human_decided_at": report.get("human_decided_at"),
            "tool_call_id": "8a53c1d7-c1c6-4cfe-a7c7-2a3c6d6a26e4",
            "tool_call_decision_id": "3a64323f-e85b-45b7-a356-1847b8d0ee63",
            "tool_call_created_at": "2026-09-25T00:00:00Z",
            "created_at": "2026-09-25T00:00:00Z",
            "updated_at": "2026-09-25T00:00:00Z",
        }
    return {
        "session_id": session_id,
        "trajectory_id": "trajectory",
        "grades": [],
        "metadata": {},
        "source": "fixture",
        "created_at": "2026-09-25T00:00:00Z",
        "tool_call_decisions": decisions,
        "messages": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": call["tool_use_id"],
                        "type": "function",
                        "function": call["tool_name"],
                        "arguments": deepcopy(call["tool_input"]),
                    }
                    for call in calls
                ],
            }
        ],
    }


class Fixture:
    """Keep deterministic model and Watcher services in the test's network namespace."""

    def __init__(
        self,
        tmp_path,
        outcome="allow",
        repeat="",
        pending=False,
        tool_id="call-a",
        tool_name="weather",
        approval_classpath=None,
        report_noop=False,
    ):
        self.path = tmp_path
        self.outcome = outcome
        self.requests = []
        self.reports = []
        self.human_choices = {}
        self.human_records = {}
        self.report_noop = report_noop
        self.started = threading.Event()
        self.release = threading.Event()
        if not pending:
            self.release.set()
        calls = deepcopy(CALLS)
        calls[0]["id"] = tool_id
        calls[0]["function"]["name"] = tool_name
        replies = [response({"role": "assistant", "content": None, "tool_calls": calls}, "tool_calls")]
        if repeat:
            calls = deepcopy(CALLS)
            if repeat == "fresh":
                for call, key in zip(calls, ["call-c", "call-d"], strict=True):
                    call["id"] = key
            replies.append(response({"role": "assistant", "content": None, "tool_calls": calls}, "tool_calls"))
        replies.append(response({"role": "assistant", "content": "Finished."}, "stop"))
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = owner.audit_http(self.path.partition("?")[0], {})
                encoded = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                status, headers = 200, {}
                if self.path not in ("/v1/hooks/pre-tool-use", "/v1/chat/completions"):
                    body = owner.audit_http(self.path, payload)
                    encoded = json.dumps(body).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)
                    return
                if payload.get("format") != "watcher":
                    body = replies.pop(0)
                else:
                    owner.requests.append(payload)
                    if payload["input"]:
                        owner.started.set()
                        if not owner.release.wait(30):
                            raise TimeoutError("Fixture release not received")
                    body = [
                        {
                            "decision": "allow",
                            "judged_decision": "allow",
                            "decision_source": "rule",
                            "enforcement_mode": "enforce",
                            "verdict": {},
                            "latency_ms": 1,
                            "tool_use_id": item["tool_use_id"],
                        }
                        for item in payload["input"]
                    ]
                    if body:
                        if outcome == "timeout":
                            threading.Event().wait(1)
                        if outcome in ("deny", "escalate", "deferred"):
                            body[0].update(
                                decision=outcome, judged_decision="deny" if outcome == "deferred" else outcome
                            )
                        elif outcome == "observe_deferred":
                            body[0].update(decision="deferred", judged_decision="deny", enforcement_mode="observe")
                        elif outcome == "paused_deferred":
                            body[0].update(
                                decision="deferred",
                                judged_decision=None,
                                enforcement_mode="paused",
                                decision_source="bypass",
                            )
                        elif outcome == "grading_fail_open":
                            body[0].update(
                                decision_source="grading_error",
                                grading_error={"code": "timeout", "message": "Fixture timeout"},
                            )
                        elif outcome == "observe":
                            body[0]["enforcement_mode"] = "observe"
                        elif outcome == "paused":
                            body[0].update(
                                decision="deferred",
                                enforcement_mode="paused",
                                decision_source="not_evaluated",
                                judged_decision=None,
                            )
                        elif outcome == "wrong_id":
                            body[0]["tool_use_id"] = "unrelated-call"
                        elif outcome == "missing_id":
                            del body[0]["tool_use_id"]
                        elif outcome == "missing_judgment":
                            del body[0]["judged_decision"]
                        elif outcome == "grading_error":
                            body[0]["grading_error"] = {"code": "grader_failed", "message": "fixture failure"}
                        elif outcome == "incomplete":
                            body = []
                        elif outcome in ("recording_failure", "locked_override"):
                            status = 503 if outcome == "recording_failure" else 422
                            body = {"detail": "fixture refusal"}
                        elif outcome == "transport":
                            self.connection.close()
                            return
                encoded = json.dumps(body).encode()
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                with suppress(BrokenPipeError):
                    self.wfile.write(encoded)

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        folder = Path(__file__).parent
        url = f"http://127.0.0.1:{self.server.server_port}"
        env = {
            **os.environ,
            "WATCHER_PYTHON": sys.executable,
            "WATCHER_BASE_URL": url,
            "WATCHER_API_KEY": "fixture-key",
            "WATCHER_SESSION_ID": "native-enforce-session",
            "WATCHER_TIMEOUT": "0.1" if outcome == "timeout" else "20",
            "EFFECT_FILE": str(tmp_path / "effects"),
            "FINAL_FILE": str(tmp_path / "final.json"),
            "REPEATED_CALLS": repeat,
            "PROVIDER_API_KEY": "fixture-key",
            "PROVIDER_MODEL": "fixture-model",
        }
        command = [
            os.environ["JAVA_BIN"],
            "-cp",
            os.environ["WATCHER_JAVA_CLASSPATH"] + (os.pathsep + str(approval_classpath) if approval_classpath else ""),
            "HumanApprovalProbe"
            if approval_classpath
            else "com.example.watcher.examples.langchain4j.WatcherMonitoredExample",
            url + "/v1",
            str(tmp_path / "effects"),
            str(tmp_path),
        ]
        self.process = subprocess.Popen(
            command, cwd=folder, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

    def audit_http(self, path, body):
        """Model the public lookup/upload/readback API, independently of native dispatch."""
        session_id = "c1f7b8be-166e-4b12-81e9-d1f3d87e4725"
        if path == "/v1/sessions/search":
            return {
                "sessions": [
                    {
                        "session_id": session_id,
                        "agent_platform": "other",
                        "trajectory_count": 1,
                        "latest_trajectory_id": "trajectory",
                        "message_count": 2,
                        "started_at": "2026-09-25T00:00:00Z",
                        "ended_at": "2026-09-25T00:00:00Z",
                    }
                ],
                "total": 1,
                "limit": 2,
                "offset": 0,
            }
        if path == f"/v1/sessions/{session_id}/trajectories/trajectory":
            calls = [call for request in self.requests for call in request["input"]]
            return _audit_trajectory(calls, self.human_records, session_id)
        if path == "/v1/tool-calls/search":
            calls = [call for request in self.requests for call in request["input"]]
            return {
                "tool_calls": [
                    {
                        "tool_call_id": "8a53c1d7-c1c6-4cfe-a7c7-2a3c6d6a26e4",
                        "session_id": session_id,
                        "occurred_at": "2026-09-25T00:00:00Z",
                        "tool_use_id": call["tool_use_id"],
                        "message_ref": "m1",
                        "tool_name": call["tool_name"],
                        "applied_decision": "escalate",
                        "decision_category": self.human_choices.get(call["tool_use_id"]),
                    }
                    for call in calls
                ],
                "total": len(calls),
                "limit": 100,
                "offset": 0,
            }
        assert path == "/v1/tool-call-decisions/batch"
        record = body["decisions"][0]
        assert record["policy_decision"] == record["applied_decision"] == record["decision_source"] == "not_evaluated"
        assert record["human_decided_at"] and record["human_decision"] in ("allow", "deny")
        assert record["tool_status"] == ("pending" if record["human_decision"] == "allow" else "blocked")
        effects_path = self.path / "effects"
        effects = effects_path.read_text().splitlines() if effects_path.exists() else []
        assert record["raw_tool_call"]["tool_input"]["city"] not in effects, "Pending tool ran before its human report"
        self.reports.append(record)
        if not self.report_noop:
            self.human_records[record["tool_use_id"]] = deepcopy(record)
            self.human_choices[record["tool_use_id"]] = (
                "human_allowed" if record["human_decision"] == "allow" else "human_denied"
            )
        return {
            "synced_count": 1,
            "synced_tool_use_ids": [record["tool_use_id"]],
            "failed_tool_use_ids": [],
            "failed_tool_call_grade_ids": [],
        }

    def finish(self):
        """Join only this fixture's process/server, retaining native output on failure."""
        try:
            output = self.process.communicate(timeout=180)
        finally:
            self.release.set()
            if self.process.poll() is None:
                self.process.kill()
                self.process.communicate()
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)
        (self.path / "watcher-requests.json").write_text(json.dumps(self.requests, indent=2))
        (self.path / "native-output.log").write_text("".join(output))
        return self.process.returncode, "".join(output)


@pytest.mark.parametrize("repeat,expected", [("", ["Paris", "Tokyo"]), ("fresh", ["Paris", "Paris", "Tokyo", "Tokyo"])])
def test_native_allow_retains_ids_results_and_complete_final_history(tmp_path, repeat, expected):
    fixture = Fixture(tmp_path, repeat=repeat)
    code, output = fixture.finish()
    assert code == 0, output
    assert sorted((tmp_path / "effects").read_text().splitlines()) == expected
    final = json.loads((tmp_path / "final.json").read_text())
    assert "Finished." in str(final[-1]["content"])
    assert {message["tool_call_id"] for message in final if message["role"] == "tool"} == (
        {"call-a", "call-b", "call-c", "call-d"} if repeat else {"call-a", "call-b"}
    )
    for request in fixture.requests:
        if request["input"]:
            assert request["mode"] == "full"
            assert "settings_overrides" not in request
            for item in request["input"]:
                assert not any(row.get("tool_call_id") == item["tool_use_id"] for row in request["messages"])
                assert any(
                    call["id"] == item["tool_use_id"]
                    for row in request["messages"]
                    for call in row.get("tool_calls", [])
                )
        assert request["messages"] == final[: len(request["messages"])], output
    assert fixture.requests[-1]["input"] == []
    assert fixture.requests[-1]["messages"] == final


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
        "recording_failure",
        "locked_override",
        "transport",
        "timeout",
    ],
)
def test_native_refusal_or_failure_prevents_tool_side_effects(tmp_path, outcome):
    fixture = Fixture(tmp_path, outcome)
    code, output = fixture.finish()
    assert code != 0, output
    assert fixture.started.is_set(), "Native execution must reach the actual SDK gate"
    assert not (tmp_path / "effects").exists()


def test_native_tool_remains_unexecuted_while_decision_is_pending(tmp_path):
    fixture = Fixture(tmp_path, pending=True)
    try:
        assert fixture.started.wait(60), "Native execution did not reach the SDK gate"
        assert fixture.process.poll() is None
        assert not (tmp_path / "effects").exists()
    finally:
        fixture.release.set()
        code, output = fixture.finish()
    assert code == 0, output
    assert sorted((tmp_path / "effects").read_text().splitlines()) == ["Paris", "Tokyo"]


@pytest.mark.parametrize("tool_id", ["call-a", "--help", "--"])
@pytest.mark.parametrize("outcome", ["allow", "deny"])
def test_native_caller_treats_tool_id_as_literal_cli_data(tmp_path, tool_id, outcome):
    fixture = Fixture(tmp_path, outcome, tool_id=tool_id)
    code, output = fixture.finish()
    assert any(item["tool_use_id"] == tool_id for request in fixture.requests for item in request["input"]), output
    if outcome == "allow":
        assert code == 0, output
        assert sorted((tmp_path / "effects").read_text().splitlines()) == ["Paris", "Tokyo"]
        assert fixture.requests[-1]["input"] == []
        assert "Finished." in str(fixture.requests[-1]["messages"][-1]["content"])
    else:
        assert not (tmp_path / "effects").exists()


def test_gate_cli_rejects_extra_ids_before_reading_stdin():
    result = subprocess.run(
        [sys.executable, "-m", "watcher_langchain4j_bridge.gate", "first-id", "extra-id"],
        cwd=Path(__file__).parent,
        input="synthetic-private-payload",
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        env={key: value for key, value in os.environ.items() if not key.startswith("WATCHER_")},
    )
    assert result.returncode == 2
    assert "synthetic-private-payload" not in result.stderr
    assert "Traceback" not in result.stderr


def test_gate_cli_reports_payload_errors_without_echoing_stdin():
    result = subprocess.run(
        [sys.executable, "-m", "watcher_langchain4j_bridge.gate", "--", "call-a"],
        cwd=Path(__file__).parent,
        input="synthetic-private-payload",
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 1
    assert result.stderr.strip() == "JSONDecodeError"


def test_unknown_native_tool_is_refused_before_execution(tmp_path):
    fixture = Fixture(tmp_path, tool_name="unregistered_tool")
    code, output = fixture.finish()
    assert code != 0, output
    assert not (tmp_path / "effects").exists()
    assert all(
        not request["input"] or request["input"][0]["tool_name"] == "unregistered_tool" for request in fixture.requests
    )


def test_repeated_native_ids_surface_failure_without_repeating_effects(tmp_path):
    fixture = Fixture(tmp_path, repeat="same")
    code, output = fixture.finish()
    assert code != 0, output
    assert sorted((tmp_path / "effects").read_text().splitlines()) == ["Paris", "Tokyo"]


@pytest.mark.parametrize("outcome", ["observe_deferred", "paused_deferred", "grading_fail_open"])
def test_native_runner_inherits_applied_server_policy(tmp_path, outcome):
    fixture = Fixture(tmp_path, outcome)
    code, output = fixture.finish()
    assert code == 0, output
    assert sorted((tmp_path / "effects").read_text().splitlines()) == ["Paris", "Tokyo"]
    assert all("settings_overrides" not in request for request in fixture.requests)


@pytest.fixture(scope="session")
def approval_classpath(tmp_path_factory):
    destination = tmp_path_factory.mktemp("approval-classes")
    subprocess.run(
        [
            str(Path(os.environ["JAVA_BIN"]).with_name("javac")),
            "-cp",
            os.environ["WATCHER_JAVA_CLASSPATH"],
            "-d",
            str(destination),
            str(Path(__file__).parent / "native/HumanApprovalProbe.java"),
        ],
        check=True,
    )
    return destination


@pytest.mark.parametrize("choice,noop", [("allow", False), ("deny", False), ("allow", True)])
def test_native_human_choice_is_reported_before_release(tmp_path, approval_classpath, choice, noop):
    fixture = Fixture(tmp_path, "escalate", approval_classpath=approval_classpath, report_noop=noop)
    try:
        deadline = time.monotonic() + 30
        while not (tmp_path / "approval-entered.txt").exists():
            assert fixture.process.poll() is None, "Native runner exited before human approval"
            assert time.monotonic() < deadline, "Native runner did not reach human approval"
            time.sleep(0.02)
        assert not (tmp_path / "effects").exists()
        (tmp_path / "human-choice.txt").write_text(choice)
    finally:
        code, output = fixture.finish()
    assert fixture.reports
    assert fixture.reports[0]["human_decision"] == choice
    if choice == "allow" and not noop:
        assert code == 0, output
        assert sorted((tmp_path / "effects").read_text().splitlines()) == ["Paris", "Tokyo"]
    else:
        assert code != 0, output
        assert not (tmp_path / "effects").exists()
