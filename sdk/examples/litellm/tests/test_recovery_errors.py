"""Verify recovery errors remain safe client responses instead of leaking provider exceptions."""

import json
from typing import Any

import pytest
from fastapi import HTTPException
from openai import ContentFilterFinishReasonError, LengthFinishReasonError
from openai.lib.streaming.chat import ChatCompletionStreamState
from openai.types.chat import ChatCompletionChunk
from test_delivery import attempt, official_response, response
from test_incremental_safety import USER, WatcherPeer, chat, chat_tool, collect, decoded, request_data
from watcher_litellm.callback import WatcherCallback
from watcher_litellm.delivery import StreamDelivery, compose_nonstream
from watcher_litellm.streams import API, IncompleteStream


@pytest.mark.parametrize("api", ["messages", "chat_completions", "responses"])
@pytest.mark.parametrize("failure", [RuntimeError("private provider diagnostics"), IncompleteStream("private detail")])
async def test_nonstream_replacement_failure_has_a_safe_gateway_status(
    api: API, failure: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    peer = WatcherPeer()
    peer.decide("denied", "deny")
    provider_requests: list[dict[str, Any]] = []

    async def fail(api: API, request: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        provider_requests.append(request)
        raise failure

    monkeypatch.setattr("watcher_litellm.callback.complete_replan", fail)
    with pytest.raises(HTTPException) as error:
        await WatcherCallback(peer.client).async_post_call_success_hook(
            request_data(api), USER, response(api, "original", ["denied"])
        )

    assert error.value.status_code == 502
    assert error.value.detail == "Model response could not be completed during gateway recovery"
    assert len(peer.requests) == len(provider_requests) == 1
    assert "private" not in str(error.value.detail)


@pytest.mark.parametrize("arguments", ["not JSON", "[]"])
async def test_nonstream_denial_with_invalid_arguments_is_not_a_retryable_server_error(arguments: str) -> None:
    peer = WatcherPeer()
    peer.decide("denied", "deny")
    body = response("chat_completions", "original", ["denied"])
    body["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = arguments
    with pytest.raises(HTTPException) as error:
        await WatcherCallback(peer.client).async_post_call_success_hook(request_data("chat_completions"), USER, body)
    assert error.value.status_code == 422
    assert error.value.detail == "Model response is not supported for gateway recovery"


async def test_nonstream_denied_chat_extension_maps_composition_failure_to_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    peer = WatcherPeer()
    peer.decide("denied", "deny")
    peer.decide("allowed", "allow")
    body = response("chat_completions", "original", ["denied"])
    body["choices"][0]["message"]["thinking_blocks"] = [
        {"type": "thinking", "thinking": "Private reasoning", "signature": "opaque"}
    ]

    async def generate(api: API, request: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        assert request["messages"][-2]["thinking_blocks"] == body["choices"][0]["message"]["thinking_blocks"]
        return response(api, "alternative", ["allowed"])

    monkeypatch.setattr("watcher_litellm.callback.complete_replan", generate)
    with pytest.raises(HTTPException) as error:
        await WatcherCallback(peer.client).async_post_call_success_hook(request_data("chat_completions"), USER, body)
    assert error.value.status_code == 422
    assert len(peer.requests) == 2
    assert "Private reasoning" not in error.value.detail


async def test_streaming_invalid_call_arguments_are_reported_as_unsupported() -> None:
    peer = WatcherPeer()
    output = await collect(
        WatcherCallback(peer.client),
        "chat_completions",
        [chat({"content": "before"}), chat({"tool_calls": [chat_tool(0, "[]", "bad")]}), chat({}, "tool_calls")],
    )
    events = decoded(output)
    assert events[-1]["error"]["message"] == "Model response stream is not supported"
    assert peer.requests == []
    assert not any(choice["delta"].get("tool_calls") for event in events for choice in event.get("choices", []))


@pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal", "pause_turn"])
def test_messages_retains_a_later_stop_reason_after_an_approved_call(stop_reason: str) -> None:
    delivery = StreamDelivery("messages")
    first = attempt(delivery, response("messages", "original", ["approved", "denied"]), {"approved"})
    output = first.output + delivery.notice("The later proposal was withheld.")
    alternative = response("messages", "alternative", [])
    alternative["stop_reason"] = stop_reason
    second = attempt(delivery, alternative, set())
    output += second.output + delivery.finish(second.state)

    final = official_response("messages", output)
    assert final["stop_reason"] == stop_reason
    assert [block["id"] for block in final["content"] if block["type"] == "tool_use"] == ["approved"]
    assert "denied" not in json.dumps(final)


@pytest.mark.parametrize("reason", ["length", "content_filter"])
def test_chat_retains_a_later_finish_reason_after_an_approved_call(reason: str) -> None:
    delivery = StreamDelivery("chat_completions")
    first = attempt(delivery, response("chat_completions", "original", ["approved", "denied"]), {"approved"})
    output = first.output + delivery.notice("The later proposal was withheld.")
    alternative = response("chat_completions", "alternative", [])
    alternative["choices"][0]["finish_reason"] = reason
    second = attempt(delivery, alternative, set())
    output += second.output + delivery.finish(second.state)
    client = ChatCompletionStreamState()
    for event in decoded(output):
        client.handle_chunk(ChatCompletionChunk.model_validate(event))
    snapshot = client.current_completion_snapshot
    assert snapshot.choices[0].finish_reason == reason
    assert [call.id for call in snapshot.choices[0].message.tool_calls or []] == ["approved"]
    with pytest.raises(LengthFinishReasonError if reason == "length" else ContentFilterFinishReasonError):
        client.get_final_completion()


@pytest.mark.parametrize(
    ("api", "reason"),
    [
        ("messages", "max_tokens"),
        ("messages", "refusal"),
        ("messages", "pause_turn"),
        ("chat_completions", "length"),
        ("chat_completions", "content_filter"),
    ],
)
def test_nonstream_recovery_keeps_provider_stop_reason_when_returning_an_allowed_call(api: API, reason: str) -> None:
    original = response(api, "original", ["denied"])
    alternative = response(api, "alternative", ["approved"])
    if api == "messages":
        alternative["stop_reason"] = reason
    else:
        alternative["choices"][0]["finish_reason"] = reason
    result = compose_nonstream(api, original, alternative, "The proposal was withheld.")
    actual = result["stop_reason"] if api == "messages" else result["choices"][0]["finish_reason"]
    assert actual == reason
    assert "denied" not in json.dumps(result)
    assert "approved" in json.dumps(result)
