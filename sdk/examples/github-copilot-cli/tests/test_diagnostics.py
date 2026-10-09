"""Check delivery evidence and sanitized failures from installed hook processes."""

import asyncio
import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from pydantic import JsonValue
from readback_fixture import SESSION_ID, login_configuration, serve_readback
from typer.testing import CliRunner
from watcher_github_copilot_cli import integration
from watcher_github_copilot_cli.diagnostics import read_status, record_event
from watcher_github_copilot_cli.transcript import JSON_OBJECT

from watcher_sdk import AsyncWatcherClient


@pytest.fixture
def configuration(tmp_path: Path) -> Path:
    return login_configuration(
        tmp_path / "config" / "config.json", tmp_path / "project", "https://watcher.test/api", token="PRIVATE_KEY"
    )


@pytest.mark.parametrize("has_partial_tail", [False, True])
@pytest.mark.parametrize("record_only", [False, True])
def test_unfinished_turn_is_quiet_but_keeps_recording_failure(
    configuration: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    has_partial_tail: bool,
    record_only: bool,
) -> None:
    native_id = "20b61067-e5e7-4432-b614-8a819df7a4c9"
    transcript = tmp_path / "session-state" / native_id / "events.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        '{"type":"user.message","data":{"content":"PRIVATE_TRANSCRIPT"}}\n'
        '{"type":"assistant.message","data":{"content":"Finished"}}\n' + ('{"type":' if has_partial_tail else "")
    )
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    result = CliRunner().invoke(
        integration.app,
        ["observe", "--config", str(configuration), *(["--record-only"] if record_only else [])],
        input=json.dumps({"sessionId": native_id, "transcriptPath": str(transcript), "timestamp": 200}),
    )
    assert result.exit_code == 0
    assert result.stdout == "{}\n"
    assert result.stderr == ""
    status = read_status(configuration)
    assert status.last_delivery is None
    assert status.last_error is not None
    assert status.last_error.failure == "recording"
    assert status.last_error.hook == "observe"
    log = configuration.with_name("events.jsonl").read_text()
    assert [json.loads(line)["kind"] for line in log.splitlines()] == ["started", "failed"]
    assert "PRIVATE_TRANSCRIPT" not in log


@pytest.mark.parametrize("mode", ["enforce"])
def test_unreadable_login_is_a_persisted_failure(configuration: Path, mode: str) -> None:
    key = next((configuration.parent / "watcher" / "credentials").glob("*.json"))
    key.chmod(0)
    try:
        with pytest.raises(PermissionError):
            key.read_bytes()
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-m",
                "watcher_github_copilot_cli.cli",
                mode,
                "--config",
                str(configuration),
                *(["--in-background", "--record-only"] if mode == "observe" else []),
            ],
            input=json.dumps(
                {"sessionId": "20b61067-e5e7-4432-b614-8a819df7a4c9", "reason": "user_exit"}
                if mode == "observe"
                else {"toolName": "bash", "toolArgs": {"command": "pwd"}}
            ),
            text=True,
            capture_output=True,
            timeout=15,
        )
    finally:
        key.chmod(0o600)
    assert result.returncode == (2 if mode == "observe" else 0)
    status = read_status(configuration)
    assert status.last_error is not None
    assert status.last_error.failure == "authentication"
    assert status.last_error.hook == mode
    assert status.last_delivery is None
    if mode == "enforce":
        assert json.loads(result.stdout) == {
            "permissionDecision": "deny",
            "permissionDecisionReason": "Watcher rejected the credential. Sign in again before retrying this tool call",
        }
    log = configuration.with_name("events.jsonl").read_text()
    assert [json.loads(line)["kind"] for line in log.splitlines()] == ["started", "unrecorded_review", "failed"]
    assert "PRIVATE_KEY" not in result.stdout + result.stderr + log + configuration.with_name("status.json").read_text()


def test_unreadable_transcript_is_a_persisted_recording_failure(
    configuration: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native_id = "20b61067-e5e7-4432-b614-8a819df7a4c9"
    transcript = tmp_path / "session-state" / native_id / "events.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        '{"type":"user.message","data":{"content":"PRIVATE_TRANSCRIPT"}}\n'
        '{"type":"assistant.message","data":{"content":"Finished"}}\n'
    )
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    transcript.chmod(0)
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-m",
                "watcher_github_copilot_cli.cli",
                "observe",
                "--config",
                str(configuration),
                "--in-background",
                "--record-only",
            ],
            input=json.dumps({"sessionId": native_id, "reason": "user_exit"}),
            text=True,
            capture_output=True,
            timeout=15,
        )
    finally:
        transcript.chmod(0o600)
    assert result.returncode == 2
    status = read_status(configuration)
    assert status.last_error is not None and status.last_error.failure == "recording"
    assert status.last_delivery is None
    assert "could not be read" in result.stderr
    log = configuration.with_name("events.jsonl").read_text()
    assert [json.loads(line)["kind"] for line in log.splitlines()] == ["started", "failed"]
    assert (
        "PRIVATE_TRANSCRIPT"
        not in result.stdout + result.stderr + log + configuration.with_name("status.json").read_text()
    )


@pytest.mark.parametrize("outcome", ["deny", "batch", "inconsistent", "malformed"])
def test_policy_denial_is_distinct_from_invalid_response(
    configuration: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    async def respond(transport: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        response: dict[str, JsonValue] = {
            "decision": "deny",
            "judged_decision": "allow" if outcome == "inconsistent" else "deny",
            "enforcement_mode": "enforce",
            "decision_source": "rule",
            "verdict": {},
            "latency_ms": 1,
        }
        if outcome == "malformed":
            del response["latency_ms"]
        return httpx.Response(200, json=[response] if outcome == "batch" else response)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", respond)
    result = CliRunner().invoke(
        integration.app,
        ["enforce", "--config", str(configuration)],
        input='{"toolName":"bash","toolArgs":{"command":"pwd"}}',
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            "Watcher withheld this tool call"
            if outcome == "deny"
            else "Watcher could not evaluate this tool call, so it was withheld"
        ),
    }
    status = read_status(configuration)
    events = [
        JSON_OBJECT.validate_json(line) for line in configuration.with_name("events.jsonl").read_text().splitlines()
    ]
    if outcome == "deny":
        assert status.last_error is None
        assert events[-1]["kind"] == "denied"
    else:
        assert status.last_error is not None and status.last_error.failure == "evaluation"
        assert events[-1]["kind"] == "failed"


@pytest.mark.parametrize("failure", ["http", "timeout", "invalid-outcome"])
def test_assessment_failure_keeps_confirmed_delivery(
    configuration: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    native_id = "20b61067-e5e7-4432-b614-8a819df7a4c9"
    transcript = tmp_path / "session-state" / native_id / "events.jsonl"
    transcript.parent.mkdir(parents=True)
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    payload = {"sessionId": native_id, "transcriptPath": str(transcript), "timestamp": 200}
    events = [
        {"type": "user.message", "data": {"content": "PRIVATE_TRANSCRIPT"}},
        {"type": "assistant.turn_start", "data": {"turnId": "0"}},
        {
            "type": "assistant.message",
            "data": {
                "content": "",
                "toolRequests": [{"toolCallId": "call", "name": "bash", "arguments": {"command": "pwd"}}],
            },
        },
        {
            "type": "tool.execution_complete",
            "data": {"toolCallId": "call", "success": True, "result": {"content": "done"}},
        },
        {"type": "assistant.message", "data": {"content": "Finished"}},
        {"type": "assistant.turn_end", "data": {"turnId": "0"}},
        {"type": "hook.start", "data": {"hookType": "agentStop", "input": payload}},
    ]
    transcript.write_text("".join(json.dumps(event) + "\n" for event in events))

    def watcher(request: httpx.Request) -> httpx.Response:
        body = JSON_OBJECT.validate_json(request.content)
        if body["input"] == []:
            return httpx.Response(200, json=[])
        if failure == "timeout":
            raise httpx.ReadTimeout("PRIVATE_SERVICE_ERROR")
        return (
            httpx.Response(503, json={"detail": "PRIVATE_SERVICE_ERROR"})
            if failure == "http"
            else httpx.Response(200, json=[])
        )

    readback = serve_readback(watcher)

    async def respond(transport: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        return await readback(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", respond)
    result = CliRunner().invoke(integration.app, ["observe", "--config", str(configuration)], input=json.dumps(payload))
    assert result.exit_code == 2
    status = read_status(configuration)
    assert status.last_delivery is not None and status.last_session == UUID(SESSION_ID)
    assert status.last_error is not None and status.last_error.failure == "evaluation"
    assert "recorded" in result.stderr and "assessment" in result.stderr
    assert "did not confirm this recording" not in result.stderr
    log = configuration.with_name("events.jsonl").read_text()
    assert [json.loads(line)["kind"] for line in log.splitlines()] == [
        "started",
        "recorded",
        "reviews_checked",
        "failed",
    ]
    for secret in ("PRIVATE_TRANSCRIPT", "PRIVATE_SERVICE_ERROR", "PRIVATE_KEY"):
        assert secret not in result.stdout + result.stderr + log + configuration.with_name("status.json").read_text()


def test_callback_is_not_delivery_and_success_clears_failure(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    record_event(config, "started")
    assert read_status(config).last_callback is not None
    assert read_status(config).last_delivery is None
    record_event(config, "failed", failure="authentication")
    assert read_status(config).last_error is not None
    record_event(config, "recorded", session=UUID(int=1))
    status = read_status(config)
    assert status.last_delivery is not None
    assert status.last_session == UUID(int=1)
    assert status.last_error is None
    assert config.with_name("status.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("assessment_fails", [False, True])
def test_a_failed_subagent_keeps_parent_delivery_and_assessment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, assessment_fails: bool
) -> None:
    config = tmp_path / "config.json"
    native_id = UUID("20b61067-e5e7-4432-b614-8a819df7a4c9")
    session = integration.ConvertedSession([{"role": "user", "content": "hi"}], [], turn_start=0, replied=True)
    assessed: list[str] = []

    async def completed(payload: object, timeout: float) -> integration.ConvertedSession:
        return session

    async def partial(*args: object, **kwargs: object) -> None:
        raise integration.PartialRecordingError(integration.RecordedSession(session=UUID(int=7), subagents={}), 1)

    async def assess(client: object, identity: str, messages: object, *, start: int) -> None:
        assessed.append(identity)
        if assessment_fails:
            raise RuntimeError("PRIVATE_SERVICE_ERROR")

    monkeypatch.setattr(integration, "is_subagent_stop", lambda payload: False)
    monkeypatch.setattr(integration, "wait_for_completed_session", completed)
    monkeypatch.setattr(integration, "record_session", partial)
    monkeypatch.setattr(integration, "assess", assess)
    payload = {"sessionId": str(native_id), "transcriptPath": str(tmp_path / "events.jsonl"), "timestamp": 1}

    async def run() -> None:
        async with AsyncWatcherClient("http://unused.test/api", max_retries=0) as client:
            await integration.observe_callback(client, payload, grade=True, config=config)

    with pytest.raises(integration.PartialRecordingError):
        asyncio.run(run())
    assert assessed == [f"github-copilot-cli:{native_id}"]
    status = read_status(config)
    assert status.last_delivery is not None and status.last_session == UUID(int=7)
    kinds = [json.loads(line)["kind"] for line in config.with_name("events.jsonl").read_text().splitlines()]
    # Judgments are read back once the parent is confirmed, before assessment.
    assert kinds == ["recorded", "reviews_checked", *(["failed"] if assessment_fails else [])]


def test_a_recording_does_not_hide_a_gate_failure(tmp_path: Path) -> None:
    # The gate withheld a tool because Watcher was unreachable; the turn's recording
    # then succeeds. The withheld tool must stay visible in the status.
    config = tmp_path / "config.json"
    record_event(config, "failed", failure="connection", hook="enforce")
    record_event(config, "recorded", session=UUID(int=1))
    status = read_status(config)
    assert status.last_delivery is not None
    assert status.last_error is not None and status.last_error.failure == "connection"
    # The gate's next decision clears it, and a recording failure is cleared by a recording.
    record_event(config, "allowed")
    assert read_status(config).last_error is None
    record_event(config, "failed", failure="recording", hook="observe")
    record_event(config, "allowed")
    assert read_status(config).last_error is not None
    record_event(config, "recorded", session=UUID(int=1))
    assert read_status(config).last_error is None


def test_background_worker_persists_failure_without_payload(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "watcher_github_copilot_cli.cli",
            "observe",
            "--config",
            str(config),
            "--in-background",
        ],
        input="PRIVATE_TRANSCRIPT invalid JSON",
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 2
    status = read_status(config)
    assert status.last_error is not None and status.last_error.failure == "recording"
    assert status.last_delivery is None
    assert "PRIVATE_TRANSCRIPT" not in (
        result.stdout
        + result.stderr
        + config.with_name("events.jsonl").read_text()
        + config.with_name("status.json").read_text()
    )


def test_events_rotate_without_losing_latest_status(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    log = config.with_name("events.jsonl")
    log.write_text(" " * (512 * 1024))
    record_event(config, "failed", failure="connection")
    assert log.with_suffix(".previous.jsonl").exists()
    assert json.loads(log.read_text())["failure"] == "connection"
    assert read_status(config).last_error is not None


def finishes_promptly(action: Callable[[], object], *fifos: Path) -> bool:
    """Run ``action`` in a thread; release any FIFO it blocked on so the thread can end."""
    worker = threading.Thread(target=action, daemon=True)
    worker.start()
    worker.join(2)
    blocked = worker.is_alive()
    for fifo in fifos:
        # Opening for reading and writing gives a blocked open its missing peer.
        os.close(os.open(fifo, os.O_RDWR | os.O_NONBLOCK))
    worker.join(2)
    return not blocked


@pytest.mark.parametrize("name", ["status.json", "events.jsonl"])
def test_a_fifo_in_place_of_a_diagnostics_file_never_blocks_a_hook(
    tmp_path: Path, name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "config.json"
    fifo = config.with_name(name)
    os.mkfifo(fifo)
    assert finishes_promptly(lambda: record_event(config, "started"), fifo)
    assert "could not save hook diagnostics" in capsys.readouterr().err


def test_status_refuses_a_fifo_instead_of_waiting(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    fifo = config.with_name("status.json")
    os.mkfifo(fifo)
    errors: list[Exception] = []

    def read() -> None:
        try:
            read_status(config)
        except ValueError as error:
            errors.append(error)

    assert finishes_promptly(read, fifo)
    assert len(errors) == 1


def test_diagnostics_are_never_written_through_a_symlink(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    target = tmp_path / "elsewhere.txt"
    target.write_text("unchanged")
    target.chmod(0o644)
    config.with_name("events.jsonl").symlink_to(target)
    record_event(config, "started")
    assert target.read_text() == "unchanged"
    assert target.stat().st_mode & 0o777 == 0o644


def test_an_oversized_status_file_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = tmp_path / "config.json"
    config.with_name("status.json").write_text(" " * (64 * 1024 + 1))
    with pytest.raises(ValueError, match="size limit"):
        read_status(config)
    record_event(config, "started")
    assert "could not save hook diagnostics" in capsys.readouterr().err
