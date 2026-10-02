"""Native Gemini snapshots retain session context and replace prior message history."""

import json
from pathlib import Path

import pytest
from watcher_gemini_cli.integration import convert


def test_successful_native_read_preserves_context_result_and_final_tail():
    rows = [
        json.loads(line)
        for line in (Path(__file__).parent / "fixtures/native-recording.jsonl").read_text().splitlines()
    ]
    messages = convert(rows)
    assert messages[0]["role"] == "user"
    assert "<session_context>" in messages[0]["content"][0]["text"]
    assert "fixture.txt" in messages[0]["content"][0]["text"]
    calls = [call for message in messages for call in message.get("tool_calls", [])]
    assert [call["id"] for call in calls] == ["read_file__sdk50-native-call"]
    assert calls[0]["function"] == "read_file"
    assert calls[0]["arguments"] == {"file_path": "/tmp/native-workspace/fixture.txt"}
    results = [message for message in messages if message["role"] == "tool"]
    assert len(results) == 1
    assert results[0]["tool_call_id"] == "read_file__sdk50-native-call"
    assert json.loads(results[0]["content"]) == {"output": "SDK50_FILE_CONTENT_MARKER\n"}
    assert "error" not in results[0]
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["content"][0]["text"] == "sdk50 native completed"


def test_message_snapshot_replaces_history_and_updates_ids_in_place():
    rows = [
        {"id": "old", "type": "user", "content": "discarded history"},
        {
            "$set": {
                "messages": [
                    {"id": "context", "type": "user", "content": "initial context"},
                    {"id": "reply", "type": "gemini", "content": "response"},
                ]
            }
        },
        {"$set": {"lastUpdated": "metadata does not clear messages"}},
        {"id": "context", "type": "user", "content": "updated context"},
    ]
    messages = convert(rows)
    assert [{"role": message["role"], "text": message["content"][0]["text"]} for message in messages] == [
        {"role": "user", "text": "updated context"},
        {"role": "assistant", "text": "response"},
    ]


def test_empty_message_snapshot_clears_history():
    assert (
        convert(
            [
                {"id": "old", "type": "user", "content": "discarded history"},
                {"$set": {"messages": []}},
            ]
        )
        == []
    )


def test_malformed_message_snapshot_fails_explicitly():
    with pytest.raises(ValueError, match="message snapshot"):
        convert([{"$set": {"messages": "not a message list"}}])


def test_legacy_metadata_messages_fail_explicitly():
    with pytest.raises(ValueError, match="metadata record"):
        convert(
            [
                {
                    "sessionId": "native-session",
                    "projectHash": "fixture-project",
                    "messages": [{"id": "context", "type": "user", "content": "must not disappear"}],
                }
            ]
        )
