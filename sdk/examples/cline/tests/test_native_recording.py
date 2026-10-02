"""Preserve the initial prompt, native result and final text from a real Cline run."""

import json
from pathlib import Path

from watcher_cline_bridge.integration import convert


def test_public_native_history_includes_initial_prompt_and_result_tail():
    records = json.loads((Path(__file__).parent / "fixtures" / "native-recording.json").read_text())
    messages = convert(records)
    assert "Read fixture.txt with read_files" in messages[0]["content"][0]["text"]
    result = next(message for message in messages if message["role"] == "tool")
    assert result["tool_call_id"] == "sdk50-native-call"
    assert "SDK50_FILE_CONTENT_MARKER" in result["content"]
    assert messages[-1]["content"][0]["text"] == "sdk50 native completed"
