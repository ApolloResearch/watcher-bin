"""Pinned native message metadata is distinct from assistant compaction."""

import json

import pytest
from watcher_opencode_bridge.integration import convert


def test_user_diff_summary_preserves_conversation():
    records = [
        {"info": {"role": "user", "summary": {"diffs": []}}, "parts": [{"type": "text", "text": "Initial request"}]},
        {"info": {"role": "assistant"}, "parts": [{"type": "text", "text": "Final answer"}]},
    ]
    messages = convert(records)
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert "Initial request" in json.dumps(messages[0]["content"])
    assert "Final answer" in json.dumps(messages[1]["content"])


def test_assistant_compaction_is_still_rejected():
    with pytest.raises(ValueError, match="Compacted histories"):
        convert([{"info": {"role": "assistant", "summary": True}, "parts": [{"type": "text", "text": "Compacted"}]}])
