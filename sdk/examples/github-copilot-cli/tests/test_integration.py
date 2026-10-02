"""Preserve native event identity and reject unsupported conversation content."""

import asyncio
import json
import tempfile
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import JsonValue
from readback_fixture import login_configuration
from watcher_github_copilot_cli import integration
from watcher_github_copilot_cli.recording import RecordedSession
from watcher_github_copilot_cli.transcript import (
    SKIPPED_EVENT_NOTICE,
    ConvertedSession,
    SubagentHistory,
    TranscriptError,
    UnsupportedTranscriptError,
    convert_session,
    read_transcript,
)


def convert(events: list[dict[str, JsonValue]]) -> list[dict[str, JsonValue]]:
    return convert_session(events).messages


def events():
    return [
        {
            "type": "user.message",
            "data": {
                "content": "Visible request",
                "transformedContent": "Model-facing request",
                "parentAgentTaskId": "normal-root-task",
            },
        },
        {"type": "assistant.message_delta", "data": {"deltaContent": "ignored"}},
        {
            "type": "assistant.message",
            "data": {
                "content": "Working",
                "toolRequests": [
                    {"toolCallId": "one", "name": "bash", "arguments": {"command": "pwd"}},
                    {"toolCallId": "two", "name": "bash", "arguments": {"command": "pwd"}},
                ],
            },
        },
        {"type": "tool.execution_start", "data": {"toolCallId": "one"}},
        {
            "type": "tool.execution_complete",
            "data": {"toolCallId": "two", "success": False, "error": {"message": "Refused"}},
        },
        {
            "type": "tool.execution_complete",
            "data": {"toolCallId": "one", "success": True, "result": {"content": "/workspace"}},
        },
        {"type": "assistant.message", "data": {"content": "Complete"}},
    ]


def test_parallel_identity_order_and_final_text():
    original = events()
    before = deepcopy(original)
    messages = convert(original)
    assert original == before
    assert messages[0]["content"] == "Model-facing request"
    assert messages[1]["tool_calls"] == [
        {"id": "one", "function": "Bash", "arguments": {"command": "pwd"}},
        {"id": "two", "function": "Bash", "arguments": {"command": "pwd"}},
    ]
    assert [m["tool_call_id"] for m in messages if m["role"] == "tool"] == ["two", "one"]
    assert messages[2]["error"] == {"type": "unknown", "message": "Refused"}
    assert messages[-1] == {"role": "assistant", "content": "Complete"}
    assert len(messages) == 5


@pytest.mark.parametrize("index,field,value", [(0, "parentToolCallId", "parent"), (2, "attachments", [{}])])
def test_unidentified_subagent_content_and_non_user_attachments_refused(index: int, field, value):
    data = events()
    data[index]["data"][field] = value
    with pytest.raises(ValueError):
        convert(data)


@pytest.mark.parametrize(
    "event",
    [
        {"type": "assistant.message", "data": {"content": "", "serverTools": [{}]}},
        {"type": "assistant.message", "data": {"content": "", "providerContentBlocks": [{"type": "x"}]}},
    ],
)
def test_unsupported_content_is_explicit(event):
    with pytest.raises(UnsupportedTranscriptError):
        convert([event])


@pytest.mark.parametrize(
    "event",
    [
        {"type": "session.compaction_complete", "data": {}},
        {"type": "user.message", "data": {"content": [{"type": "image"}]}},
        {
            "type": "tool.execution_complete",
            "data": {"toolCallId": "unknown", "success": True, "result": {"content": ""}},
        },
    ],
)
def test_malformed_or_unmatched_events_are_skipped(event):
    session = convert_session([event])
    assert session.skipped_events == 1 and session.messages[0]["content"] == SKIPPED_EVENT_NOTICE


@pytest.mark.parametrize(
    "fault", ["duplicate-call", "duplicate-result", "nonobject-arguments", "blank-id", "bad-success", "binary-result"]
)
def test_ambiguous_or_incomplete_tools_are_skipped(fault):
    data = events()
    if fault == "duplicate-call":
        data[2]["data"]["toolRequests"][1]["toolCallId"] = "one"
    if fault == "duplicate-result":
        data.insert(6, deepcopy(data[5]))
    if fault == "nonobject-arguments":
        data[2]["data"]["toolRequests"][0]["arguments"] = []
    if fault == "blank-id":
        data[2]["data"]["toolRequests"][0]["toolCallId"] = ""
    if fault == "bad-success":
        data[5]["data"]["success"] = 1
    if fault == "binary-result":
        data[5]["data"]["result"]["binaryResultsForLlm"] = "not a list"
    session = convert_session(data)
    assert session.skipped_events >= 1
    assert any(message["content"] == SKIPPED_EVENT_NOTICE for message in session.messages)
    # The rest of the turn is still recorded.
    assert session.messages[-1] == {"role": "assistant", "content": "Complete"}


def test_only_matching_native_session_log_is_read(tmp_path, monkeypatch):
    identity = str(uuid4())
    path = tmp_path / "session-state" / identity / "events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(json.dumps(e) for e in events()))
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    payload = {"sessionId": identity, "transcriptPath": str(path)}
    assert read_transcript(payload) == convert(events())
    other = tmp_path / "unrelated.jsonl"
    other.write_text(path.read_text())
    payload["transcriptPath"] = str(other)
    with pytest.raises(ValueError):
        read_transcript(payload)


def test_invalid_or_oversized_transcript_is_refused(tmp_path, monkeypatch):
    identity = str(uuid4())
    path = tmp_path / "session-state" / identity / "events.jsonl"
    path.parent.mkdir(parents=True)
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    payload = {"sessionId": identity, "transcriptPath": str(path)}
    path.write_text("{broken")
    with pytest.raises(ValueError):
        read_transcript(payload)
    with path.open("wb") as stream:
        stream.truncate(32 * 1024 * 1024 + 1)
    with pytest.raises(ValueError):
        read_transcript(payload)


def test_native_system_context_is_preserved():
    event = {"type": "system.message", "data": {"role": "system", "content": "Native instructions"}}
    assert convert([event]) == [{"role": "system", "content": "Native instructions"}]


def test_initial_system_context_precedes_user_without_reordering_later_changes():
    records = [
        {"type": "user.message", "data": {"content": "task"}},
        {"type": "system.message", "data": {"role": "system", "content": "initial policy"}},
        {"type": "assistant.message", "data": {"content": "answer"}},
        {"type": "system.message", "data": {"role": "system", "content": "later policy"}},
    ]
    result = convert(records)
    assert [message["content"] for message in result] == ["initial policy", "task", "answer", "later policy"]


SESSION_ID = "4f3b0c9e-1c7d-4a47-9a0e-3a4e2f9b6c11"


def run_observe(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, JsonValue],
    *,
    grade: bool,
    parent: list[dict[str, JsonValue]] | None = None,
    record_error: Exception | None = None,
) -> list[tuple[str, object]]:
    """Run the observe callback with the transcript reader, recorder and assessor replaced."""
    events: list[tuple[str, object]] = []
    session = ConvertedSession(
        parent or [{"role": "user", "content": "task"}, {"role": "assistant", "content": "parent"}],
        [SubagentHistory("agent-1", [{"role": "assistant", "content": "child"}])],
        turn_start=1,
        replied=parent is None,
    )

    async def fake_session(payload: Mapping[str, JsonValue], timeout: float) -> ConvertedSession:
        return session

    async def fake_record(
        client: object, native_id: UUID, recorded: ConvertedSession, *, timeout_seconds: float
    ) -> RecordedSession:
        events.append(("record", (native_id, [history.agent_id for history in recorded.subagents])))
        if record_error is not None:
            raise record_error
        return RecordedSession(session=UUID(int=1), subagents={"agent-1": UUID(int=2)})

    async def fake_assess(client: object, identity: str, messages: list[dict[str, JsonValue]], *, start: int) -> None:
        events.append(("assess", (identity, start)))

    monkeypatch.setattr(integration, "wait_for_completed_session", fake_session)
    monkeypatch.setattr(integration, "read_ended_session", fake_session)
    monkeypatch.setattr(integration, "record_session", fake_record)
    monkeypatch.setattr(integration, "assess", fake_assess)
    monkeypatch.setattr(integration, "is_subagent_stop", lambda payload: False)
    with tempfile.TemporaryDirectory() as directory:
        config = login_configuration(Path(directory) / "config.json", Path(directory), "https://watcher.test/api")
        asyncio.run(integration.run_hook("observe", payload, config, grade=grade))
    return events


TURN: dict[str, JsonValue] = {"sessionId": SESSION_ID, "transcriptPath": "/unused/events.jsonl"}
ENDED: dict[str, JsonValue] = {"sessionId": SESSION_ID, "reason": "user_exit", "timestamp": 1}


def test_observe_records_parent_and_subagents_then_assesses_the_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    events = run_observe(monkeypatch, TURN, grade=True)
    assert events == [("record", (UUID(SESSION_ID), ["agent-1"])), ("assess", (f"github-copilot-cli:{SESSION_ID}", 1))]


def test_record_only_observation_never_assesses(monkeypatch: pytest.MonkeyPatch) -> None:
    assert run_observe(monkeypatch, TURN, grade=False) == [("record", (UUID(SESSION_ID), ["agent-1"]))]


def test_a_failed_recording_is_reported_before_any_assessment(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(TranscriptError, match="subagent"):
        run_observe(monkeypatch, TURN, grade=True, record_error=TranscriptError("1 subagent history failed"))


def test_observe_records_the_final_state_at_session_end_without_assessing(monkeypatch: pytest.MonkeyPatch) -> None:
    assert run_observe(monkeypatch, ENDED, grade=True) == [("record", (UUID(SESSION_ID), ["agent-1"]))]


def test_nothing_is_recorded_at_session_end_before_the_first_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    assert run_observe(monkeypatch, ENDED, grade=True, parent=[{"role": "user", "content": "task"}]) == []
