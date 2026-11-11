"""Exercise Chat recovery with Copilot's Gemini reasoning fields."""

from pathlib import Path

import litellm
import pytest
from pydantic import JsonValue
from test_incremental_safety import USER, WatcherPeer, request_data
from watcher_litellm.callback import WatcherCallback
from watcher_litellm.delivery import compose_nonstream
from watcher_litellm.streams import API, UnsupportedStream, as_dict


@pytest.fixture
def gemini_response() -> litellm.ModelResponse:
    """A sanitized Gemini message captured through the native Copilot gateway."""
    path = Path(__file__).parent / "fixtures/gemini_chat_response.json"
    return litellm.ModelResponse.model_validate_json(path.read_text())


async def test_gemini_denial_preserves_replacement_reasoning_and_grades_its_call(
    gemini_response: litellm.ModelResponse, monkeypatch: pytest.MonkeyPatch
) -> None:
    peer = WatcherPeer()
    peer.decide("denied", "deny")
    peer.decide("recovered", "allow")
    original = as_dict(gemini_response)
    replacement = as_dict(gemini_response)
    replacement["choices"][0]["message"].update(
        content="I will create the remaining file.",
        tool_calls=[
            {
                "id": "recovered",
                "type": "function",
                "function": {"name": "bash", "arguments": '{"command":"touch recovered.txt"}'},
            }
        ],
        provider_specific_fields={"reasoning_text": "Replacement reasoning.", "reasoning_opaque": "opaque-replacement"},
    )
    replacement_before = as_dict(replacement)
    generated: list[dict[str, JsonValue]] = []

    async def generate(api: API, request: dict[str, JsonValue], data: dict[str, JsonValue]) -> dict[str, JsonValue]:
        generated.append(request)
        messages = request["messages"]
        assert isinstance(messages, list)
        assert messages[-2] == original["choices"][0]["message"]
        last_message = messages[-1]
        assert isinstance(last_message, dict)
        content = last_message["content"]
        assert isinstance(content, str) and "WATCHER NOTICE" in content
        return replacement

    monkeypatch.setattr("watcher_litellm.callback.complete_replan", generate)
    delivered = await WatcherCallback(peer.client).async_post_call_success_hook(
        request_data("chat_completions"), USER, gemini_response
    )
    message = as_dict(delivered)["choices"][0]["message"]
    assert message["provider_specific_fields"] == replacement["choices"][0]["message"]["provider_specific_fields"]
    assert [call["id"] for call in message["tool_calls"]] == ["recovered"]
    assert "WATCHER NOTICE" in message["content"]
    assert "orchid-lantern.txt" in message["content"]
    assert len(generated) == 1
    assert [body["response_body"]["choices"][0]["message"]["tool_calls"][0]["id"] for body in peer.requests] == [
        "denied",
        "recovered",
    ]
    assert as_dict(gemini_response) == original
    assert replacement == replacement_before


@pytest.mark.parametrize(
    ("include_fields", "replacement_fields"),
    [(False, None), (True, None), (True, {}), (True, {"reasoning_text": None, "reasoning_opaque": None})],
)
def test_gemini_replacement_does_not_inherit_rejected_reasoning(
    gemini_response: litellm.ModelResponse, include_fields: bool, replacement_fields: dict[str, JsonValue] | None
) -> None:
    original = as_dict(gemini_response)
    replacement = as_dict(gemini_response)
    message = replacement["choices"][0]["message"]
    message["tool_calls"] = []
    if include_fields:
        message["provider_specific_fields"] = replacement_fields
    else:
        message.pop("provider_specific_fields")
    replacement_before = as_dict(replacement)
    delivered = compose_nonstream("chat_completions", original, replacement, "Denied.")
    if include_fields:
        assert delivered["choices"][0]["message"]["provider_specific_fields"] == replacement_fields
    else:
        assert "provider_specific_fields" not in delivered["choices"][0]["message"]
    assert original == as_dict(gemini_response)
    assert replacement == replacement_before


def test_gemini_fallback_does_not_reuse_rejected_reasoning(gemini_response: litellm.ModelResponse) -> None:
    delivered = compose_nonstream("chat_completions", as_dict(gemini_response), None, "Denied.")
    message = delivered["choices"][0]["message"]
    assert "provider_specific_fields" not in message
    assert not message.get("tool_calls")


@pytest.mark.parametrize(
    "fields",
    [
        {"reasoning_text": {"tool_calls": []}},
        {"reasoning_opaque": ["opaque"]},
        {"reasoning_text": 1},
        {"reasoning_opaque": False},
        {"unknown_execution": {"name": "bash"}},
        {"refusal": "not supported"},
        [],
        "opaque",
    ],
)
@pytest.mark.parametrize("target", ["original", "replacement"])
def test_gemini_recovery_keeps_unknown_provider_fields_closed(
    gemini_response: litellm.ModelResponse, fields: JsonValue, target: str
) -> None:
    original = as_dict(gemini_response)
    replacement = as_dict(gemini_response)
    body = original if target == "original" else replacement
    body["choices"][0]["message"]["provider_specific_fields"] = fields
    with pytest.raises(UnsupportedStream):
        compose_nonstream("chat_completions", original, replacement, "Denied.")
