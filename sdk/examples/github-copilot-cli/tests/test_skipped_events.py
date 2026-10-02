"""Keep recording a session whose log has an unreadable or contradictory event in it."""

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from pydantic import JsonValue
from watcher_github_copilot_cli import integration
from watcher_github_copilot_cli.recording import RecordedSession
from watcher_github_copilot_cli.transcript import (
    SKIPPED_EVENT_NOTICE,
    ConvertedSession,
    convert_session,
    read_events,
    wait_for_completed_session,
)

from watcher_sdk import AsyncWatcherClient

SESSION_ID = "20b61067-e5e7-4432-b614-8a819df7a4c9"
SKIPPED: dict[str, JsonValue] = {
    "role": "system",
    "content": SKIPPED_EVENT_NOTICE,
    "metadata": {"github_copilot_cli": {"skipped_events": True}},
}


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "session-state" / SESSION_ID / "events.jsonl"
    path.parent.mkdir(parents=True)
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    return path


def line(event: dict[str, JsonValue]) -> str:
    return json.dumps(event) + "\n"


def call(call_id: str, command: str = "pwd") -> dict[str, JsonValue]:
    return {"toolCallId": call_id, "name": "bash", "arguments": {"command": command}}


def result(call_id: str, content: str = "/work") -> dict[str, JsonValue]:
    return {
        "type": "tool.execution_complete",
        "data": {"toolCallId": call_id, "success": True, "result": {"content": content}},
    }


def test_unreadable_lines_are_marked_and_the_rest_is_recorded(log: Path) -> None:
    # A crash or the agent itself can leave a line that is not an event. Refusing
    # the whole log would stop recording the session for good.
    log.write_text(
        line({"type": "user.message", "data": {"content": "Where am I"}})
        + "{PRIVATE bad JSON}\n"
        + '["PRIVATE", "not an object"]\n'
        + '{"data": {"content": "PRIVATE without a type"}}\n'
        + line({"type": "assistant.message", "data": {"content": "In /work"}})
    )
    session = convert_session(read_events(UUID(SESSION_ID), log))
    assert session.messages == [
        {"role": "user", "content": "Where am I"},
        SKIPPED,
        {"role": "assistant", "content": "In /work"},
    ]
    assert session.skipped_events == 3
    assert "PRIVATE" not in json.dumps(session.messages)


def test_a_repeated_tool_call_id_skips_that_whole_message() -> None:
    session = convert_session(
        [
            {"type": "user.message", "data": {"content": "Look around"}},
            {"type": "assistant.message", "data": {"content": "", "toolRequests": [call("c1")]}},
            # Reuses c1 alongside a new c2: neither call of this message is recorded.
            {
                "type": "assistant.message",
                "data": {"content": "", "toolRequests": [call("c2", "PRIVATE"), call("c1", "PRIVATE")]},
            },
            result("c1"),
            result("c2", "PRIVATE result"),
            {"type": "assistant.message", "data": {"content": "Done"}},
        ]
    )
    assert session.messages == [
        {"role": "user", "content": "Look around"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "function": "Bash", "arguments": {"command": "pwd"}}],
        },
        SKIPPED,
        {"role": "tool", "tool_call_id": "c1", "function": "Bash", "content": "/work"},
        SKIPPED,
        {"role": "assistant", "content": "Done"},
    ]
    assert session.skipped_events == 2
    assert "PRIVATE" not in json.dumps(session.messages)


def test_a_call_repeated_within_one_message_is_skipped() -> None:
    session = convert_session(
        [{"type": "assistant.message", "data": {"content": "", "toolRequests": [call("c1"), call("c1")]}}]
    )
    assert session.messages == [SKIPPED] and session.skipped_events == 1


def test_unmatched_repeated_and_incomplete_results_are_skipped() -> None:
    session = convert_session(
        [
            {"type": "assistant.message", "data": {"content": "", "toolRequests": [call("c1")]}},
            result("unknown", "PRIVATE"),
            {"type": "tool.execution_complete", "data": {"toolCallId": "c1", "success": True}},
            {"type": "tool.execution_complete", "data": {"toolCallId": "c1", "success": False}},
            result("c1"),
            result("c1", "PRIVATE again"),
        ]
    )
    assert session.messages[1:] == [
        SKIPPED,
        {"role": "tool", "tool_call_id": "c1", "function": "Bash", "content": "/work"},
        SKIPPED,
    ]
    assert session.skipped_events == 4


def test_a_skipped_subagent_event_is_marked_in_that_subagents_history() -> None:
    session = convert_session(
        [
            {"type": "user.message", "agentId": "agent-1", "data": {"content": ["PRIVATE malformed"]}},
            {"type": "assistant.message", "agentId": "agent-1", "data": {"content": "Subagent answer"}},
            {"type": "subagent.completed", "agentId": "agent-1", "data": {"toolCallId": "task-1"}},
        ]
    )
    assert session.messages == []
    [subagent] = session.subagents
    assert subagent.messages == [SKIPPED, {"role": "assistant", "content": "Subagent answer"}]


def test_malformed_and_mismatched_turn_boundaries_never_stall_recording(log: Path) -> None:
    log.write_text(
        line({"type": "assistant.turn_start", "data": {"PRIVATE": "no turn ID"}})
        + line({"type": "assistant.turn_end", "data": {"turnId": "never-started"}})
        + line({"type": "hook.start", "data": {"hookType": "agentStop", "input": {"PRIVATE": "malformed"}}})
        + line({"type": "user.message", "data": {"content": "Hello"}})
        + line({"type": "assistant.turn_start", "data": {"turnId": "1"}})
        + line({"type": "assistant.message", "data": {"content": "Hi"}})
        + line({"type": "assistant.turn_end", "data": {"turnId": "1"}})
    )
    payload: dict[str, JsonValue] = {"sessionId": SESSION_ID, "transcriptPath": str(log)}
    session = asyncio.run(wait_for_completed_session(payload, 1))
    assert session.messages == [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}]


@pytest.mark.parametrize(
    "payload",
    [{"sessionId": SESSION_ID, "reason": "complete"}, {"sessionId": SESSION_ID, "transcriptPath": "/unused"}],
)
def test_a_recording_with_skipped_events_logs_them_without_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, payload: dict[str, JsonValue]
) -> None:
    session = ConvertedSession(
        messages=[{"role": "user", "content": "task"}, SKIPPED, {"role": "assistant", "content": "done"}],
        subagents=[],
        replied=True,
        skipped_events=2,
    )

    async def converted(payload: Mapping[str, JsonValue], timeout: float) -> ConvertedSession:
        return session

    async def recorded(client: object, native: UUID, converted: ConvertedSession, **_: object) -> RecordedSession:
        return RecordedSession(session=UUID(int=1), subagents={})

    monkeypatch.setattr(integration, "read_ended_session", converted)
    monkeypatch.setattr(integration, "wait_for_completed_session", converted)
    monkeypatch.setattr(integration, "is_subagent_stop", lambda payload: False)
    monkeypatch.setattr(integration, "record_session", recorded)
    config = tmp_path / "config.json"
    client = AsyncWatcherClient(httpx_client=httpx.AsyncClient(base_url="http://unused"))
    assert asyncio.run(integration.observe_callback(client, payload, grade=False, config=config)) is not None
    log = config.with_name("events.jsonl").read_text()
    assert [json.loads(entry)["kind"] for entry in log.splitlines()] == [
        "skipped_events",
        "recorded",
        "reviews_checked",
    ]
