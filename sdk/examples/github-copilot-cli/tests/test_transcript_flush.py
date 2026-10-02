"""Wait for the current Copilot callback's final answer before submitting a snapshot."""

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import JsonValue
from watcher_github_copilot_cli.transcript import (
    SKIPPED_EVENT_NOTICE,
    IncompleteTranscriptError,
    UnsupportedTranscriptError,
    wait_for_completed_session,
)


async def messages(payload: dict[str, JsonValue], timeout: float) -> list[dict[str, JsonValue]]:
    return (await wait_for_completed_session(payload, timeout)).messages


SESSION_ID = "20b61067-e5e7-4432-b614-8a819df7a4c9"
EARLIER_TURN: list[dict[str, JsonValue]] = [
    {"type": "user.message", "data": {"content": "First request"}},
    {"type": "assistant.turn_start", "data": {"turnId": "0"}},
    {"type": "assistant.message", "data": {"content": "First answer"}},
    {"type": "assistant.turn_end", "data": {"turnId": "0"}},
]


@pytest.fixture
def transcript(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "session-state" / SESSION_ID / "events.jsonl"
    path.parent.mkdir(parents=True)
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    return path


def write_events(path: Path, events: list[dict[str, JsonValue]]) -> None:
    path.write_text("".join(json.dumps(event) + "\n" for event in events))


def stop_marker(path: Path, timestamp: int) -> dict[str, JsonValue]:
    return {
        "type": "hook.start",
        "data": {
            "hookType": "agentStop",
            "input": {"sessionId": SESSION_ID, "transcriptPath": str(path), "timestamp": timestamp},
        },
    }


def test_callback_waits_for_its_own_flushed_turn(transcript: Path) -> None:
    earlier = [*EARLIER_TURN, stop_marker(transcript, 100)]
    write_events(transcript, earlier)
    payload: dict[str, JsonValue] = {"sessionId": SESSION_ID, "transcriptPath": str(transcript), "timestamp": 200}

    async def run() -> list[dict[str, JsonValue]]:
        recording = asyncio.create_task(messages(payload, 1))
        await asyncio.sleep(0)
        assert not recording.done()
        write_events(
            transcript,
            [
                *earlier,
                {"type": "user.message", "data": {"content": "Second request"}},
                {"type": "assistant.turn_start", "data": {"turnId": "1"}},
                {"type": "assistant.message", "data": {"content": "Second answer"}},
                {"type": "assistant.turn_end", "data": {"turnId": "1"}},
                stop_marker(transcript, 200),
            ],
        )
        return await recording

    assert asyncio.run(run()) == [
        {"role": "user", "content": "First request"},
        {"role": "assistant", "content": "First answer"},
        {"role": "user", "content": "Second request"},
        {"role": "assistant", "content": "Second answer"},
    ]


def test_replay_refuses_an_old_answer_when_the_latest_turn_is_open(transcript: Path) -> None:
    write_events(transcript, [*EARLIER_TURN, {"type": "assistant.turn_start", "data": {"turnId": "1"}}])
    with pytest.raises(IncompleteTranscriptError, match="did not finish writing before the deadline"):
        asyncio.run(messages({"sessionId": SESSION_ID, "transcriptPath": str(transcript)}, 0.01))


def test_partial_event_is_retried_without_submitting_the_earlier_answer(transcript: Path) -> None:
    prefix: list[dict[str, JsonValue]] = [
        *EARLIER_TURN,
        {"type": "assistant.turn_start", "data": {"turnId": "1"}},
    ]
    write_events(transcript, prefix)
    with transcript.open("a") as stream:
        stream.write('{"type":"assistant.message",')
    payload: dict[str, JsonValue] = {"sessionId": SESSION_ID, "transcriptPath": str(transcript)}

    async def run() -> list[dict[str, JsonValue]]:
        recording = asyncio.create_task(messages(payload, 1))
        await asyncio.sleep(0)
        assert not recording.done()
        write_events(
            transcript,
            [
                *prefix,
                {"type": "assistant.message", "data": {"content": "Flushed answer"}},
                {"type": "assistant.turn_end", "data": {"turnId": "1"}},
            ],
        )
        return await recording

    assert asyncio.run(run()) == [
        {"role": "user", "content": "First request"},
        {"role": "assistant", "content": "First answer"},
        {"role": "assistant", "content": "Flushed answer"},
    ]


def test_complete_malformed_json_is_skipped_rather_than_awaited(transcript: Path) -> None:
    lines = [json.dumps(event) + "\n" for event in EARLIER_TURN]
    transcript.write_text("".join(lines[:2]) + "{PRIVATE bad JSON}\n" + "".join(lines[2:]))
    recorded = asyncio.run(messages({"sessionId": SESSION_ID, "transcriptPath": str(transcript)}, 1))
    assert [message["content"] for message in recorded] == ["First request", SKIPPED_EVENT_NOTICE, "First answer"]
    assert "PRIVATE" not in json.dumps(recorded)


def test_unsupported_content_is_not_retried_as_a_pending_write(transcript: Path) -> None:
    event: dict[str, JsonValue] = {
        "type": "assistant.message",
        "data": {"content": "", "providerContentBlocks": [{"type": "PRIVATE"}]},
    }
    write_events(transcript, [event])
    with pytest.raises(UnsupportedTranscriptError, match="^Unsupported Copilot content$"):
        asyncio.run(messages({"sessionId": SESSION_ID, "transcriptPath": str(transcript)}, 1))
