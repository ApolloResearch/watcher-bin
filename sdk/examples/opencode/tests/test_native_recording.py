"""Preserve the actual pinned OpenCode session snapshot through the public SDK converter."""

import json
from pathlib import Path

from watcher_opencode_bridge.integration import convert


def test_recorded_native_tools_and_final_answer_survive_conversion():
    captured = json.loads((Path(__file__).parent / "fixtures" / "native-recording.json").read_text())
    messages = convert(captured["messages"])
    assert messages[0]["role"] == "user"
    assert "Read first.txt and second.txt" in json.dumps(messages[0]["content"])
    calls = [call for message in messages for call in message.get("tool_calls", [])]
    assert [call["id"] for call in calls] == ["call00001", "call00002"]
    results = [message for message in messages if message["role"] == "tool"]
    assert [message["tool_call_id"] for message in results] == [call["id"] for call in calls]
    assert "SDK50_OPENCODE_FIRST_FILE" in json.dumps(results[0]["content"])
    assert "SDK50_OPENCODE_SECOND_FILE" in json.dumps(results[1]["content"])
    assert "sdk50 opencode completed" in json.dumps(messages[-1]["content"])
