"""Native format edge cases that must not silently lose or mislink context."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from watcher_gemini_cli.integration import convert

FIXTURE = json.loads((Path(__file__).parent / "fixtures/fixture.json").read_text())


def test_repeated_message_id_is_an_update():
    assert convert(FIXTURE + [deepcopy(FIXTURE[1])]) == convert(FIXTURE)


def test_rewind_and_nontext_attachments_fail():
    with pytest.raises(ValueError):
        convert(FIXTURE + [{"$rewindTo": "m1"}])
    rows = deepcopy(FIXTURE)
    rows[0]["content"] = [{"inlineData": {"data": "AA=="}}]
    with pytest.raises(ValueError):
        convert(rows)


def test_standalone_results_replace_inline_duplicates_and_preserve_delivery_order():
    rows = deepcopy(FIXTURE)
    rows.insert(
        2,
        {
            "id": "native-results",
            "type": "user",
            "content": [
                {"functionResponse": {"id": "call-b", "name": "run_shell_command", "response": {"output": "second"}}},
                {
                    "functionResponse": {
                        "id": "call-a",
                        "name": "run_shell_command",
                        "response": {"error": "first failed"},
                    }
                },
            ],
        },
    )
    results = [message for message in convert(rows) if message["role"] == "tool"]
    assert [message["tool_call_id"] for message in results] == ["call-b", "call-a"]
    assert "second" in results[0]["content"]
    assert results[1]["error"]["message"] == "Tool reported an error"


def test_actual_failed_tool_recording_with_standalone_results():
    path = Path(__file__).parent / "fixtures/native-tool-error-recording.jsonl"
    messages = convert([json.loads(line) for line in path.read_text().splitlines()])
    assert messages[0]["role"] == "user"
    assert "<session_context>" in messages[0]["content"][0]["text"]
    results = [message for message in messages if message["role"] == "tool"]
    assert len(results) == 1
    assert results[0]["tool_call_id"] == "run_shell_command__sdk50-native-call"
    assert results[0]["error"]["message"] == "Tool reported an error"
    assert "sdk50 native completed" in str(messages[-1]["content"])
