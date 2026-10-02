"""Native pre-tool and completion snapshots retain the same converted prefix."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from watcher_openclaw_bridge.enforcement import pending_messages
from watcher_openclaw_bridge.integration import convert

FIXTURE = json.loads((Path(__file__).parent / "fixtures/native-snapshots.json").read_text())


def test_native_before_tool_and_completion_preserve_exact_history_prefix():
    original = deepcopy(FIXTURE)
    pending = convert(FIXTURE["pending"])
    completed = convert(FIXTURE["completed"])
    assert pending == completed[: len(pending)]
    assert completed[len(pending)]["tool_call_id"] == FIXTURE["call"]["id"]
    assert pending[-1]["tool_calls"][0]["arguments"] == FIXTURE["call"]["arguments"]
    assert original == FIXTURE


@pytest.mark.parametrize("role", ["user", "assistant", "toolResult"])
def test_equivalent_native_text_shapes_preserve_blocks_and_identity(role):
    records = deepcopy(FIXTURE["completed"])
    row = next(
        message
        for message in records
        if message["role"] == role and message["content"] and message["content"][0]["type"] == "text"
    )
    expected = convert(records)
    row["content"] = row["content"][0]["text"]
    assert convert(records) == expected


def test_reasoning_parallel_calls_and_error_result_content_are_not_collapsed():
    records = [
        {"role": "user", "content": [{"type": "text", "text": "one"}, {"type": "text", "text": "two"}]},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "consider both"},
                {"type": "toolCall", "id": "first", "name": "read", "arguments": {"path": "one"}},
                {"type": "toolCall", "id": "second", "name": "read", "arguments": {"path": "two"}},
            ],
        },
        {
            "role": "toolResult",
            "toolCallId": "second",
            "toolName": "read",
            "isError": True,
            "content": [{"type": "text", "text": "failed"}],
        },
        {
            "role": "toolResult",
            "toolCallId": "first",
            "toolName": "read",
            "isError": False,
            "content": [{"type": "text", "text": "done"}],
        },
    ]
    original = deepcopy(records)
    messages = convert(records)
    assert messages[0]["content"] == records[0]["content"]
    assert messages[1]["content"] == [{"type": "reasoning", "reasoning": "consider both"}]
    assert [call["id"] for call in messages[1]["tool_calls"]] == ["first", "second"]
    assert [message["tool_call_id"] for message in messages[2:]] == ["second", "first"]
    assert messages[2]["content"] == [{"type": "text", "text": "failed"}] and messages[2]["error"]
    assert messages[3]["content"] == [{"type": "text", "text": "done"}] and "error" not in messages[3]
    assert records == original


@pytest.mark.parametrize("call_already_recorded", [False, True])
def test_pending_call_uses_the_same_representation_before_native_persistence(call_already_recorded):
    prefix = FIXTURE["pending"] if call_already_recorded else FIXTURE["pending"][:-1]
    messages = convert(prefix)
    original = deepcopy(messages)
    pending = pending_messages(messages, FIXTURE["call"])
    assert pending == convert(FIXTURE["completed"])[: len(pending)]
    assert messages == original
