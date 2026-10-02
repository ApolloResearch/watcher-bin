"""Bound native permission-hook completion while reading and converting prior conversations."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest
from pydantic import BaseModel
from readback_fixture import login_configuration

SESSION = UUID("039a1ab5-331b-4073-bb4d-b62dc012987c")


class ToolArguments(BaseModel):
    command: str


class NativeCallback(BaseModel):
    sessionId: UUID
    timestamp: int | None
    cwd: str
    toolName: Literal["bash"]
    toolArgs: ToolArguments


class PermissionAnswer(BaseModel):
    permissionDecision: Literal["deny"]
    permissionDecisionReason: str


def write_telemetry_log(native: Path, session: UUID) -> Path:
    path = native / "session-state" / str(session) / "events.jsonl"
    path.parent.mkdir(parents=True)
    telemetry = b'{"type":"model.test","data":{"probe":"private synthetic telemetry"}}\n' * 4096
    with path.open("wb") as output:
        output.write(json.dumps({"type": "session.start", "data": {"sessionId": str(session)}}).encode() + b"\n")
        while output.tell() < 224 * 1024 * 1024:
            output.write(telemetry)
    return path


def native_timeout_answer(
    native: Path, callback: str, policy_seconds: float, process_seconds: float
) -> PermissionAnswer:
    config = login_configuration(native.parent / "config" / "config.json", native.parent, "http://127.0.0.1:9/api")
    completed = subprocess.run(
        [sys.executable, "-I", "-m", "watcher_github_copilot_cli.integration", "enforce", "--config", str(config)],
        input=callback,
        text=True,
        capture_output=True,
        timeout=process_seconds,
        env={
            **os.environ,
            "COPILOT_HOME": str(native),
            "WATCHER_TIMEOUT_SECONDS": str(policy_seconds),
        },
    )
    assert completed.returncode == 0, completed.stderr
    return PermissionAnswer.model_validate_json(completed.stdout)


@pytest.mark.timeout(10)
@pytest.mark.parametrize("has_timestamp", [True, False], ids=["root", "legacy-root"])
def test_native_hook_deadline_includes_prior_log_read(tmp_path: Path, has_timestamp: bool) -> None:
    native = tmp_path / "native"
    write_telemetry_log(native, SESSION)
    callback = NativeCallback(
        sessionId=SESSION,
        timestamp=1790769600000 if has_timestamp else None,
        cwd=str(tmp_path),
        toolName="bash",
        toolArgs=ToolArguments(command="printf deadline_probe"),
    )

    answer = native_timeout_answer(native, callback.model_dump_json(), 0.05, 2)

    assert answer.permissionDecision == "deny"
    assert answer.permissionDecisionReason == "Watcher could not be reached in time, so the tool call was withheld"


@pytest.mark.timeout(12)
def test_native_hook_deadline_includes_prior_conversation_conversion(tmp_path: Path) -> None:
    native = tmp_path / "native"
    path = native / "session-state" / str(SESSION) / "events.jsonl"
    path.parent.mkdir(parents=True)
    messages = b'{"type":"user.message","data":{"content":"readable synthetic line"}}\n' * 5_000
    with path.open("wb") as output:
        output.write(json.dumps({"type": "session.start", "data": {"sessionId": str(SESSION)}}).encode() + b"\n")
        for _ in range(150):
            output.write(messages)
    callback = NativeCallback(
        sessionId=SESSION,
        timestamp=None,
        cwd=str(tmp_path),
        toolName="bash",
        toolArgs=ToolArguments(command="printf deadline_probe"),
    )

    answer = native_timeout_answer(native, callback.model_dump_json(), 2, 4)

    assert answer.permissionDecision == "deny"
    assert answer.permissionDecisionReason == "Watcher could not be reached in time, so the tool call was withheld"
