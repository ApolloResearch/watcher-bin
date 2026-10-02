"""Exercise a native runtime and the installed SDK together over loopback HTTP only."""

import json
import os
import subprocess
import sys
import threading
from contextlib import suppress
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest


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
        self, tmp_path, outcome="allow", repeat="", pending=False, tool_id="call-a", schema_case="", human=False
    ):
        self.path = tmp_path
        self.outcome = outcome
        self.requests = []
        self.audit_reports = []
        self.human_choices = {}
        self.human_records = {}
        self.started = threading.Event()
        self.release = threading.Event()
        if not pending:
            self.release.set()
        replies = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = owner.audit(self.path.partition("?")[0], {}, outcome)
                assert body is not None
                encoded = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                status, headers = 200, {}
                audit = owner.audit(self.path, payload, outcome)
                if audit is not None:
                    body = audit
                elif payload.get("format") != "watcher":
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
                        if outcome == "observe_deferred":
                            for item in body:
                                item.update(decision="deferred", judged_decision="deny", enforcement_mode="observe")
                        elif outcome == "paused_deferred":
                            for item in body:
                                item.update(
                                    decision="deferred",
                                    judged_decision=None,
                                    enforcement_mode="paused",
                                    decision_source="bypass",
                                )
                        elif outcome == "human" or outcome.startswith("human_"):
                            for item in body:
                                item.update(decision="escalate", judged_decision="escalate")
                        if outcome == "timeout":
                            threading.Event().wait(1)
                        if outcome in ("deny", "escalate", "deferred"):
                            body[0].update(decision=outcome, judged_decision="deny")
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
                            body = {"detail": [{"loc": ["body"], "msg": "fixture refusal", "type": "value_error"}]}
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

            def log_message(self, format, *args):
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
            "FIXTURE_FIRST_TOOL_ID": tool_id,
            "FIXTURE_SCHEMA_CASE": schema_case,
            "FIXTURE_HUMAN_APPROVAL": "1" if human else "",
            "APPROVAL_ENTERED_FILE": str(tmp_path / "approval-entered.jsonl"),
            "APPROVAL_RELEASE_FILE": str(tmp_path / "approval-release.json"),
            "PROVIDER_API_KEY": "fixture-key",
            "PROVIDER_MODEL": "fixture-model",
        }
        command = ["node", str(folder / "fixtures" / "monitoring.mjs")]
        self.process = subprocess.Popen(
            command, cwd=folder, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

    def audit(self, path, payload, outcome):
        """Serve public audit operations with explicit upload/readback failure cases."""
        session = "c1f7b8be-166e-4b12-81e9-d1f3d87e4725"
        if path == "/v1/sessions/search":
            return {
                "sessions": [
                    {
                        "session_id": session,
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
        if path == f"/v1/sessions/{session}/trajectories/trajectory":
            calls = [call for request in self.requests for call in request["input"]]
            return _audit_trajectory(calls, self.human_records, session)
        if path == "/v1/tool-calls/search":
            calls = [call for request in self.requests for call in request["input"]]
            return {
                "tool_calls": [
                    {
                        "tool_call_id": "8a53c1d7-c1c6-4cfe-a7c7-2a3c6d6a26e4",
                        "session_id": session,
                        "occurred_at": "2026-09-25T00:00:00Z",
                        "message_ref": "m1",
                        "tool_use_id": call["tool_use_id"],
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
        if path == "/v1/tool-call-decisions/batch":
            record = payload["decisions"][0]
            assert (
                record["policy_decision"] == record["applied_decision"] == record["decision_source"] == "not_evaluated"
            )
            assert record["human_decided_at"]
            self.audit_reports.append(record)
            failed = outcome == "human_report_rejected"
            if not failed and outcome != "human_report_noop":
                self.human_records[record["tool_use_id"]] = deepcopy(record)
                self.human_choices[record["tool_use_id"]] = (
                    "human_allowed" if record["human_decision"] == "allow" else "human_denied"
                )
            return {
                "synced_count": 0 if failed else 1,
                "synced_tool_use_ids": [] if failed else [record["tool_use_id"]],
                "failed_tool_use_ids": [record["tool_use_id"]] if failed else [],
                "failed_tool_call_grade_ids": [],
            }
        return None

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
        [sys.executable, "-m", "watcher_mastra_bridge.gate", "first-id", "extra-id"],
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
        [sys.executable, "-m", "watcher_mastra_bridge.gate", "--", "call-a"],
        cwd=Path(__file__).parent,
        input="synthetic-private-payload",
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 1
    assert result.stderr.strip() == "JSONDecodeError"


def test_repeated_native_ids_surface_failure_without_repeating_effects(tmp_path):
    fixture = Fixture(tmp_path, repeat="same")
    code, output = fixture.finish()
    assert code != 0, output
    assert sorted((tmp_path / "effects").read_text().splitlines()) == ["Paris", "Tokyo"]


def test_native_schema_key_order_does_not_change_approved_arguments(tmp_path):
    fixture = Fixture(tmp_path, schema_case="reverse")
    code, output = fixture.finish()
    assert code == 0, output
    assert sorted((tmp_path / "effects").read_text().splitlines()) == ["Paris", "Tokyo"]
    grades = [request for request in fixture.requests if request["input"]]
    assert grades[0]["input"][0]["tool_input"] == {"units": "c", "city": "Paris"}
    final = json.loads((tmp_path / "final.json").read_text())
    results = [json.loads(row["content"]) for row in final if row["role"] == "tool"]
    assert results == [
        {"city": "Paris", "units": "c", "weather": "fixture"},
        {"city": "Tokyo", "units": "c", "weather": "fixture"},
    ]


@pytest.mark.parametrize("schema_case", ["default", "transform"])
def test_native_schema_value_changes_are_recorded_and_withheld(tmp_path, schema_case):
    fixture = Fixture(tmp_path, schema_case=schema_case)
    code, output = fixture.finish()
    assert code != 0, output
    assert not (tmp_path / "effects").exists()
    assert fixture.requests
    assert all(request["input"] == [] for request in fixture.requests)
    assert fixture.requests[0]["messages"][-1]["tool_calls"][0]["arguments"] == {"city": "Paris"}


def test_final_tool_step_records_its_actual_results(tmp_path):
    fixture = Fixture(tmp_path, repeat="budget")
    code, output = fixture.finish()
    assert code == 0, output
    assert sorted((tmp_path / "effects").read_text().splitlines()) == [
        "Paris",
        "Paris",
        "Paris",
        "Tokyo",
        "Tokyo",
        "Tokyo",
    ]
    final = json.loads((tmp_path / "final.json").read_text())
    assert final[-1]["role"] == "tool"
    assert {row["tool_call_id"] for row in final if row["role"] == "tool"} == {
        "call-a",
        "call-b",
        "call-c",
        "call-d",
        "call-e",
        "call-f",
    }
    assert fixture.requests[-1]["input"] == []
    assert fixture.requests[-1]["messages"] == final


def test_unknown_native_tool_is_recorded_before_refusal(tmp_path):
    fixture = Fixture(tmp_path, schema_case="unknown")
    code, output = fixture.finish()
    assert code != 0, output
    assert not (tmp_path / "effects").exists()
    assert len(fixture.requests) == 1
    assert fixture.requests[0]["input"] == []
    assert fixture.requests[0]["messages"][-1]["tool_calls"][0]["function"] == "unregistered_tool"


@pytest.mark.parametrize("mode", ["observe_deferred", "paused_deferred"])
def test_configured_mode_preserves_native_tool_dispatch(tmp_path, mode):
    fixture = Fixture(tmp_path, mode)
    code, output = fixture.finish()
    assert code == 0, output
    assert sorted((tmp_path / "effects").read_text().splitlines()) == ["Paris", "Tokyo"]
    assert all("settings_overrides" not in request for request in fixture.requests)


@pytest.mark.parametrize("choice", [True, False, "yes"])
def test_native_approval_waits_for_parent_and_records_choice_before_execution(tmp_path, choice):
    fixture = Fixture(tmp_path, "human", human=True)
    try:
        for _ in range(1500):
            if (tmp_path / "approval-entered.jsonl").exists():
                break
            assert fixture.process.poll() is None, "The native agent exited before requesting approval"
            threading.Event().wait(0.02)
        assert (tmp_path / "approval-entered.jsonl").exists()
        assert not (tmp_path / "effects").exists()
        assert fixture.process.poll() is None
    finally:
        (tmp_path / "approval-release.json").write_text(json.dumps({"approved": choice}))
        code, output = fixture.finish()
    if choice is True:
        assert code == 0, output
        assert sorted((tmp_path / "effects").read_text().splitlines()) == ["Paris", "Tokyo"]
        assert len(fixture.audit_reports) == 2
        assert all(record["human_decision"] == "allow" for record in fixture.audit_reports)
    else:
        assert code != 0
        assert not (tmp_path / "effects").exists()
        if choice is False:
            assert fixture.audit_reports and fixture.audit_reports[0]["human_decision"] == "deny"
        else:
            assert fixture.audit_reports == []


@pytest.mark.parametrize("outcome", ["human_report_rejected", "human_report_noop"])
def test_native_human_approval_does_not_bypass_failed_audit(tmp_path, outcome):
    (tmp_path / "approval-release.json").write_text('{"approved": true}')
    fixture = Fixture(tmp_path, outcome, human=True)
    code, output = fixture.finish()
    assert code != 0, output
    assert fixture.audit_reports
    assert not (tmp_path / "effects").exists()
