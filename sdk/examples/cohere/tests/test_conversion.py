"""Protect native Cohere content and identity at the format-conversion boundary."""

from copy import deepcopy

import pytest
from watcher_cohere.conversion import convert_exchange


def native_pair():
    return {
        "request": {"messages": [{"role": "user", "content": "Use the tool."}]},
        "response": {
            "finish_reason": "TOOL_CALL",
            "message": {
                "role": "assistant",
                "tool_plan": "Inspect the requested values.",
                "tool_calls": [
                    {
                        "id": "native-1",
                        "type": "function",
                        "function": {
                            "name": "inspect",
                            "arguments": '{"enabled":false,"count":0,"ratio":1.0,"empty":null}',
                        },
                    }
                ],
            },
        },
    }


def test_tool_plan_and_exact_json_types_survive_without_mutating_native_input():
    pair = native_pair()
    original = deepcopy(pair)
    result = convert_exchange(pair["request"], pair["response"])
    assert pair == original
    assert result.messages[-1]["content"] == [{"type": "text", "text": "Inspect the requested values."}]
    arguments = result.inputs[0]["tool_input"]
    assert arguments == {"enabled": False, "count": 0, "ratio": 1.0, "empty": None}
    assert type(arguments["enabled"]) is bool and type(arguments["count"]) is int
    assert type(arguments["ratio"]) is float


@pytest.mark.parametrize("identity", [None, "", 17, False])
def test_native_tool_identity_cannot_be_coerced(identity):
    pair = native_pair()
    pair["response"]["message"]["tool_calls"][0]["id"] = identity
    with pytest.raises(ValueError, match="native tool ID"):
        convert_exchange(pair["request"], pair["response"])


def test_citations_are_not_silently_dropped():
    pair = native_pair()
    pair["response"]["message"]["citations"] = [{"start": 0, "end": 5, "text": "source"}]
    with pytest.raises(ValueError, match="Unsupported Cohere content"):
        convert_exchange(pair["request"], pair["response"])


def test_unmatched_tool_result_is_rejected_before_monitoring():
    pair = native_pair()
    pair["request"]["messages"].append({"role": "tool", "tool_call_id": "unknown", "content": "result"})
    with pytest.raises(ValueError, match="no matching"):
        convert_exchange(pair["request"], pair["response"])
