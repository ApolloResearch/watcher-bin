"""Keep oversized native events out of the permission hook without changing ordinary recording."""

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest
from pydantic import BaseModel, JsonValue
from readback_fixture import login_configuration
from watcher_github_copilot_cli.identity import PendingTool
from watcher_github_copilot_cli.integration import gate_context
from watcher_github_copilot_cli.transcript import JSON_OBJECT, UnsupportedTranscriptError, convert_session, read_events

SESSION = UUID("cb00ea04-3ea5-4e96-8918-f7790d5b8b3b")
READER_EVENT_LIMIT = 4 * 1024 * 1024
EventType = Literal["model.test", "user.message"]


class WatcherCapture(BaseModel):
    url: str
    requests: list[bytes]


class HookSubmission(BaseModel):
    ephemeral: bool
    messages: list[dict[str, JsonValue]]
    external_ids: dict[str, str] | None = None


@pytest.fixture
def allowing_watcher() -> Iterator[WatcherCapture]:
    capture = WatcherCapture(url="", requests=[])

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            capture.requests.append(self.rfile.read(int(self.headers["Content-Length"])))
            response = (
                b'{"decision":"allow","judged_decision":"allow","enforcement_mode":"enforce",'
                b'"decision_source":"rule","verdict":{},"latency_ms":1}'
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        capture.url = f"http://127.0.0.1:{server.server_port}/api"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield capture
        finally:
            server.shutdown()
            thread.join(timeout=2)
            assert not thread.is_alive()


def write_log(native: Path, event_type: EventType, event_bytes: int, *, dense: bool) -> Path:
    path = native / "session-state" / str(SESSION) / "events.jsonl"
    path.parent.mkdir(parents=True)
    with path.open("wb") as output:
        output.write(json.dumps({"type": "session.start", "data": {"sessionId": str(SESSION)}}).encode() + b"\n")
        output.write(b'{"type":"user.message","data":{"content":"before the sized event"}}\n')
        if dense:
            prefix = b'{"type":"' + event_type.encode() + b'","data":{"content":"dense context","items":['
            suffix = b"null]}}\n"
            item = b'{"text":"synthetic probe","parts":["a","b","c"]},'
            remaining = event_bytes - len(prefix) - len(suffix)
            output.write(prefix)
            chunk = item * 1000
            while remaining >= len(chunk):
                output.write(chunk)
                remaining -= len(chunk)
            while remaining >= len(item):
                output.write(item)
                remaining -= len(item)
            output.write(b" " * remaining)
            output.write(suffix)
        else:
            prefix = b'{"type":"' + event_type.encode() + b'","data":{"content":"'
            suffix = b'"}}\n'
            output.write(prefix + b"x" * (event_bytes - len(prefix) - len(suffix)) + suffix)
        output.write(b'{"type":"user.message","data":{"content":"after the sized event"}}\n')
    return path


@pytest.mark.parametrize("event_type", ["model.test", "user.message"])
def test_reader_rejects_events_above_its_explicit_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, event_type: EventType
) -> None:
    native = tmp_path / "native"
    path = write_log(native, event_type, READER_EVENT_LIMIT + 1, dense=False)
    monkeypatch.setenv("COPILOT_HOME", str(native))

    with pytest.raises(UnsupportedTranscriptError):
        read_events(SESSION, path, max_event_bytes=READER_EVENT_LIMIT)


@pytest.mark.parametrize("event_bytes", [READER_EVENT_LIMIT - 1, READER_EVENT_LIMIT])
def test_reader_preserves_content_at_or_below_its_explicit_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, event_bytes: int
) -> None:
    native = tmp_path / "native"
    path = write_log(native, "user.message", event_bytes, dense=False)
    monkeypatch.setenv("COPILOT_HOME", str(native))
    expected = convert_session(read_events(SESSION, path)).messages

    context = convert_session(read_events(SESSION, path, max_event_bytes=READER_EVENT_LIMIT)).messages

    assert context == expected
    assert len(context) == 3
    assert context[0] == {"role": "user", "content": "before the sized event"}
    assert context[2] == {"role": "user", "content": "after the sized event"}
    content = context[1]["content"]
    assert isinstance(content, str) and len(content) > 4_000_000 and content.strip("x") == ""


@pytest.mark.parametrize("event_type", ["model.test", "user.message"])
def test_ordinary_recording_accepts_the_same_oversized_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, event_type: EventType
) -> None:
    native = tmp_path / "native"
    path = write_log(native, event_type, READER_EVENT_LIMIT + 1, dense=False)
    monkeypatch.setenv("COPILOT_HOME", str(native))

    messages = convert_session(read_events(SESSION, path)).messages

    assert messages[0] == {"role": "user", "content": "before the sized event"}
    assert messages[-1] == {"role": "user", "content": "after the sized event"}
    if event_type == "model.test":
        assert len(messages) == 2
    else:
        assert len(messages) == 3
        content = messages[1]["content"]
        assert isinstance(content, str) and len(content) > 4_000_000 and content.strip("x") == ""


def native_allow(native: Path, watcher_url: str, policy_seconds: float) -> None:
    config = login_configuration(native.parent / "config" / "config.json", native.parent, watcher_url)
    completed = subprocess.run(
        [sys.executable, "-I", "-m", "watcher_github_copilot_cli.integration", "enforce", "--config", str(config)],
        input=json.dumps(
            {"sessionId": str(SESSION), "toolName": "bash", "toolArgs": {"command": "printf event_limit_probe"}}
        ),
        text=True,
        capture_output=True,
        timeout=4,
        env={
            **os.environ,
            "COPILOT_HOME": str(native),
            "WATCHER_TIMEOUT_SECONDS": str(policy_seconds),
        },
    )
    assert completed.returncode == 0, completed.stderr
    assert JSON_OBJECT.validate_json(completed.stdout) == {
        "permissionDecision": "allow",
        "permissionDecisionReason": "Watcher approved this call",
    }
    assert completed.stderr == ""


@pytest.mark.timeout(10)
@pytest.mark.parametrize("event_type", ["model.test", "user.message"])
def test_native_hook_allows_ephemeral_review_after_an_oversized_event(
    tmp_path: Path, allowing_watcher: WatcherCapture, event_type: EventType
) -> None:
    native = tmp_path / "native"
    write_log(native, event_type, 147_000_000, dense=True)

    native_allow(native, allowing_watcher.url, 0.5)

    assert len(allowing_watcher.requests) == 1
    submitted = HookSubmission.model_validate_json(allowing_watcher.requests[0])
    assert submitted.ephemeral is True
    assert submitted.messages == []
    assert submitted.external_ids is None


@pytest.mark.timeout(10)
def test_native_hook_accepts_a_dense_event_below_the_limit(tmp_path: Path, allowing_watcher: WatcherCapture) -> None:
    native = tmp_path / "native"
    write_log(native, "model.test", 16 * 1024 * 1024 - 1, dense=True)

    native_allow(native, allowing_watcher.url, 2)

    assert len(allowing_watcher.requests) == 1
    submitted = HookSubmission.model_validate_json(allowing_watcher.requests[0])
    assert submitted.ephemeral is True
    assert submitted.messages == [
        {"role": "user", "content": "before the sized event"},
        {"role": "user", "content": "after the sized event"},
    ]
    assert submitted.external_ids == {"other": "github-copilot-cli:cb00ea04-3ea5-4e96-8918-f7790d5b8b3b"}


def write_large_view_log(native: Path) -> Path:
    path = native / "session-state" / str(SESSION) / "events.jsonl"
    path.parent.mkdir(parents=True)
    events: list[dict[str, JsonValue]] = [
        {"type": "session.start", "data": {"sessionId": str(SESSION)}},
        {"type": "user.message", "data": {"content": "Read the fixture and keep all changes inside the lab."}},
        {
            "type": "assistant.message",
            "data": {
                "content": "",
                "toolRequests": [
                    {
                        "toolCallId": "large-view-call",
                        "name": "view",
                        "arguments": {"path": "large-fixture.txt", "forceReadLargeFiles": True},
                        "type": "function",
                    }
                ],
            },
        },
        {
            "type": "tool.execution_complete",
            "id": "large-view-result",
            "timestamp": "2026-09-30T20:00:00Z",
            "parentId": "large-view-request",
            "data": {
                "toolCallId": "large-view-call",
                "interactionId": "large-view-interaction",
                "turnId": "large-view-turn",
                "rte": True,
                "success": True,
                "result": {"content": "x" * 3_080_000, "detailedContent": "x" * 3_080_000},
                "toolTelemetry": {},
            },
        },
        {"type": "assistant.message", "data": {"content": "The large fixture was read."}},
        {"type": "user.message", "data": {"content": "Now check the lab summary without changing the fixture."}},
    ]
    path.write_text("".join(json.dumps(event) + "\n" for event in events))
    return path


def assert_large_view_context(messages: list[dict[str, JsonValue]]) -> None:
    assert messages == [
        {"role": "user", "content": "Read the fixture and keep all changes inside the lab."},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "large-view-call",
                    "function": "Read",
                    "arguments": {"forceReadLargeFiles": True, "file_path": "large-fixture.txt"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "large-view-call",
            "function": "Read",
            "content": "x" * 131_072 + "\n[Watcher recorded the first 131072 of 3080000 characters of this result.]",
        },
        {"role": "assistant", "content": "The large fixture was read."},
        {"role": "user", "content": "Now check the lab summary without changing the fixture."},
    ]
    assert len(json.dumps(messages).encode()) < 600_000


def test_gate_context_preserves_a_supported_large_view(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    native = tmp_path / "native"
    path = write_large_view_log(native)
    monkeypatch.setenv("COPILOT_HOME", str(native))
    assert 6_000_000 < path.stat().st_size < 6_500_000

    pending = PendingTool.model_validate(
        {"sessionId": str(SESSION), "toolName": "bash", "toolArgs": {"command": "pwd"}}
    )

    context = asyncio.run(gate_context(pending, 4 * 1024 * 1024, deadline=time.monotonic() + 2))

    assert context.messages is not None and context.unrecorded == "tool_call_id_not_found"
    assert_large_view_context(context.messages)


@pytest.mark.timeout(10)
def test_native_hook_retains_context_and_identity_after_a_large_view(
    tmp_path: Path, allowing_watcher: WatcherCapture
) -> None:
    native = tmp_path / "native"
    write_large_view_log(native)

    native_allow(native, allowing_watcher.url, 0.5)

    assert len(allowing_watcher.requests) == 1
    submitted = HookSubmission.model_validate_json(allowing_watcher.requests[0])
    assert submitted.ephemeral is True
    assert submitted.external_ids == {"other": "github-copilot-cli:cb00ea04-3ea5-4e96-8918-f7790d5b8b3b"}
    assert_large_view_context(submitted.messages)
