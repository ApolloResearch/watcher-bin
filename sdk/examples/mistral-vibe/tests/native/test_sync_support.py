"""Validate detection of actual tool results while a native pre-tool decision waits."""

import pytest
from sync_support import native_results_seen


@pytest.mark.parametrize(
    "provider_request, expected",
    [
        (
            {
                "body": {
                    "contents": [
                        {"parts": [{"functionResponse": {"name": "read_file", "response": {"content": "file"}}}]}
                    ]
                }
            },
            True,
        ),
        (
            {
                "contents": [{"parts": [{"text": "functionResponse appears in text"}]}],
                "tools": [{"description": "functionResponse"}],
            },
            False,
        ),
        ({"messages": [{"role": "tool", "content": "file"}]}, True),
        ({"input": [{"type": "function_call_output", "output": "file"}]}, True),
        ({"messages": [{"role": "user", "content": "Read a file"}]}, False),
    ],
)
def test_native_result_detection_uses_conversation_structure(provider_request, expected):
    assert native_results_seen([provider_request]) is expected
