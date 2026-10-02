"""A captured write distinguishes completion, IO failure and withheld execution."""

import pytest
from watcher_aider.observation import write_messages


@pytest.mark.parametrize(
    ("status", "content"),
    [
        ("completed", "File write completed"),
        ("error", "File write failed"),
        ("withheld", "File write withheld before execution"),
    ],
)
def test_write_outcome_distinguishes_execution(status, content):
    operation = {
        "id": "native-write",
        "arguments": {"path": "target", "content": "new text"},
        "status": status,
        "error": "Watcher did not confirm approval" if status == "withheld" else "IsADirectoryError",
    }
    call, result = write_messages(operation)
    assert result["content"] == content
    assert call["tool_calls"][0]["id"] == result["tool_call_id"] == operation["id"]
    assert call["tool_calls"][0]["arguments"] == operation["arguments"]
    assert ("error" in result) == (status != "completed")
    if status != "completed":
        assert result["error"]["message"] == operation["error"]
