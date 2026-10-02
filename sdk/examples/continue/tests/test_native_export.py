"""Verify the public JSON envelope captured through the real terminal export command."""

import json
from pathlib import Path

from watcher_continue.integration import convert


def test_native_export_retains_prompt_tool_result_and_final_answer():
    exported = json.loads((Path(__file__).parent / "fixtures/native-export.json").read_text())
    assert exported["version"] == 1
    messages = convert(exported["session"]["history"])
    assert messages[0]["content"][0]["text"] == "Read fixture.txt with Read then say sdk50 native completed"
    result = next(message for message in messages if message["role"] == "tool")
    assert result["tool_call_id"] == "sdk50-native-call"
    assert "SDK50_FILE_CONTENT_MARKER" in result["content"]
    assert messages[-1]["content"][0]["text"] == "sdk50 native completed"
