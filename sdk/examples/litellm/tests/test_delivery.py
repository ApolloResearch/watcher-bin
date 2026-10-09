"""Cross-check resampled client streams with official provider SDK accumulators.

These tests exercise serialization independently of gateway retry/grading I/O.
They retain an approved first call while dropping a later denied one, then
append a replacement under the same client response and verify exact content.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import litellm
import openai
import pytest
from anthropic.lib.streaming._messages import accumulate_event
from anthropic.types import ErrorResponse, RawMessageStreamEvent
from litellm.proxy import proxy_server
from litellm.proxy._types import UserAPIKeyAuth
from openai._streaming import SSEDecoder
from openai.lib.streaming.chat import ChatCompletionStreamState
from openai.lib.streaming.responses._responses import ResponseStreamState
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.responses import ResponseStreamEvent
from pydantic import BaseModel, Field, TypeAdapter
from watcher_litellm.callback import WatcherCallback
from watcher_litellm.delivery import StreamDelivery, compose_nonstream
from watcher_litellm.incremental import IncrementalStream, PendingEvent
from watcher_litellm.streams import API, IncompleteStream, UnsupportedStream, encode

from watcher_sdk import AsyncWatcherClient


class Attempt(BaseModel):
    """Parsed provider state and the events that were actually delivered."""

    model_config = {"arbitrary_types_allowed": True}
    state: IncrementalStream
    output: list[bytes] = Field(default_factory=list)


def response(api: API, prefix: str, calls: list[str]) -> dict[str, Any]:
    """One distinct provider response, with stable literal text and tool identities."""
    if api == "messages":
        return {
            "id": f"msg_{prefix}",
            "type": "message",
            "role": "assistant",
            "model": f"model_{prefix}",
            "content": [
                {"type": "text", "text": f"{prefix} text"},
                *({"type": "tool_use", "id": call, "name": "read", "input": {"path": call}} for call in calls),
            ],
            "stop_reason": "tool_use" if calls else "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 11, "output_tokens": 7},
        }
    if api == "chat_completions":
        return {
            "id": f"chatcmpl_{prefix}",
            "object": "chat.completion",
            "model": f"model_{prefix}",
            "created": 1,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls" if calls else "stop",
                    "message": {
                        "role": "assistant",
                        "content": f"{prefix} text",
                        "tool_calls": [
                            {
                                "id": call,
                                "type": "function",
                                "function": {"name": "read", "arguments": json.dumps({"path": call})},
                            }
                            for call in calls
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        }
    return {
        "id": f"resp_{prefix}",
        "object": "response",
        "created_at": 1,
        "status": "completed",
        "model": f"model_{prefix}",
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "output": [
            {
                "type": "message",
                "id": f"text_{prefix}",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {"type": "output_text", "text": f"{prefix} text", "annotations": [], "logprobs": []},
                ],
            },
            *(
                {
                    "type": "function_call",
                    "id": f"fc_{call}",
                    "call_id": call,
                    "name": "read",
                    "arguments": json.dumps({"path": call}),
                    "status": "completed",
                }
                for call in calls
            ),
        ],
        "usage": {
            "input_tokens": 11,
            "output_tokens": 7,
            "total_tokens": 18,
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


def decoded(chunks: list[bytes]) -> list[dict[str, Any]]:
    return [json.loads(event.data) for event in SSEDecoder().iter_bytes(iter(chunks))]


def attempt(delivery: StreamDelivery, body: dict[str, Any], allowed: set[str]) -> Attempt:
    """Use real parsing, then reproduce the callback's safe-prefix and denied-drain contract."""
    events = decoded(list(encode(delivery.api, body)))
    return event_attempt(delivery, events, allowed)


def event_attempt(delivery: StreamDelivery, events: list[dict[str, Any]], allowed: set[str]) -> Attempt:
    delivery.begin_attempt()
    state = IncrementalStream(delivery.api)
    frames: list[PendingEvent] = []
    for event in events:
        value = litellm.ModelResponseStream(**event) if delivery.api == "chat_completions" else event
        frames.extend(state.add(value))
    for index in state.calls:
        if delivery.api == "messages":
            call_id = state.body["content"][index]["id"]
        elif delivery.api == "responses":
            call_id = state.items[index]["call_id"]
        else:
            call_id = state.chat_calls[index]["id"]
        if call_id in allowed:
            state.allowed.add(index)
    result = Attempt(state=state)
    blocked = False
    for frame in frames:
        if frame.requires - state.allowed:
            blocked = True
        if not blocked or delivery.retains(frame):
            result.output.extend(delivery.emit(frame, state))
    delivery.checkpoint(state)
    return result


def official_response(api: API, chunks: list[bytes]) -> dict[str, Any]:
    """Parse the exact emitted SSE with the client libraries used by real consumers."""
    events = decoded(chunks)
    if api == "messages":
        snapshot = None
        for event in events:
            snapshot = accumulate_event(
                event=TypeAdapter(RawMessageStreamEvent).validate_python(event), current_snapshot=snapshot
            )
        assert snapshot is not None
        return snapshot.model_dump(mode="json")
    if api == "chat_completions":
        chat = ChatCompletionStreamState()
        for event in events:
            chat.handle_chunk(ChatCompletionChunk.model_validate(event))
        return chat.get_final_completion().model_dump(mode="json")
    stream = ResponseStreamState(input_tools=[], text_format=openai.omit)
    final = None
    for event in events:
        for parsed in stream.handle_event(TypeAdapter(ResponseStreamEvent).validate_python(event)):
            if parsed.type == "response.completed" or parsed.type == "response.incomplete":
                final = parsed.response
    assert final is not None
    return final.model_dump(mode="json")


@pytest.mark.parametrize("stream", [False, True], ids=["json", "stream"])
@pytest.mark.parametrize(
    ("prefix", "suffix", "expected"),
    [
        ("Original.", "Retry.", "Original.\n\nDenied.\n\nRetry."),
        ("", "Retry.", "Denied.\n\nRetry."),
        ("Original.", "", "Original.\n\nDenied."),
        ("", "", "Denied."),
        ("Original.", None, "Original.\n\nDenied."),
    ],
)
def test_chat_notice_separates_only_nonempty_content(
    stream: bool, prefix: str, suffix: str | None, expected: str
) -> None:
    original = response("chat_completions", "original", ["denied"])
    original["choices"][0]["message"]["content"] = prefix
    replacement = response("chat_completions", "retry", []) if suffix is not None else None
    if replacement is not None:
        replacement["choices"][0]["message"]["content"] = suffix

    if stream:
        delivery = StreamDelivery("chat_completions")
        first = attempt(delivery, original, set())
        output = first.output + delivery.notice("Denied.")
        final_state = first.state
        if replacement is not None:
            second = attempt(delivery, replacement, set())
            output.extend(second.output)
            final_state = second.state
        output.extend(delivery.finish(final_state))
        final = official_response("chat_completions", output)
        assert delivery.response["choices"][0]["message"]["content"] == expected
    else:
        final = compose_nonstream("chat_completions", original, replacement, "Denied.")

    assert final["choices"][0]["message"]["content"] == expected


@pytest.mark.parametrize("api", ["messages", "chat_completions", "responses"])
def test_replacement_preserves_first_approved_call_and_original_envelope(api: API) -> None:
    delivery = StreamDelivery(api)
    first = attempt(delivery, response(api, "original", ["allowed", "denied"]), {"allowed"})
    output = first.output + delivery.notice(" Denied; trying again. ")
    second = attempt(delivery, response(api, "retry", ["alternative"]), {"alternative"})
    output += second.output + delivery.finish(second.state)

    body = official_response(api, output)
    assert body["model"] == "model_original"
    assert body["id"] == response(api, "original", [])["id"]
    if api == "messages":
        assert [block["id"] for block in body["content"] if block["type"] == "tool_use"] == ["allowed", "alternative"]
        assert [block["text"] for block in body["content"] if block["type"] == "text"] == [
            "original text",
            " Denied; trying again. ",
            "retry text",
        ]
        assert body["stop_reason"] == "tool_use"
        assert body["usage"]["input_tokens"] == 11
        assert [event["index"] for event in decoded(output) if event["type"] == "content_block_start"] == [
            0,
            1,
            2,
            3,
            4,
        ]
        assert sum(event["type"] == "message_stop" for event in decoded(output)) == 1
    elif api == "chat_completions":
        choice = body["choices"][0]
        assert [call["id"] for call in choice["message"]["tool_calls"]] == ["allowed", "alternative"]
        assert choice["message"]["content"] == "original text\n\n Denied; trying again. \n\nretry text"
        assert choice["finish_reason"] == "tool_calls"
        assert body["usage"]["total_tokens"] == 18
        assert sum(bool(event["choices"] and event["choices"][0]["finish_reason"]) for event in decoded(output)) == 1
    else:
        assert [item["call_id"] for item in body["output"] if item["type"] == "function_call"] == [
            "allowed",
            "alternative",
        ]
        assert [item["content"][0]["text"] for item in body["output"] if item["type"] == "message"] == [
            "original text",
            " Denied; trying again. ",
            "retry text",
        ]
        assert body["usage"]["total_tokens"] == 18
        events = decoded(output)
        assert [event["sequence_number"] for event in events] == list(range(len(events)))
        assert sum(event["type"] == "response.completed" for event in events) == 1
        assert delivery.response["output"] == [
            event["item"] for event in events if event["type"] == "response.output_item.done"
        ]


@pytest.mark.parametrize("api", ["messages", "chat_completions", "responses"])
def test_retry_exhaustion_keeps_previously_approved_calls(api: API) -> None:
    delivery = StreamDelivery(api)
    first = attempt(delivery, response(api, "original", ["allowed", "denied"]), {"allowed"})
    output = first.output + delivery.notice(" Denied. ")
    second = attempt(delivery, response(api, "retry", ["denied_again"]), set())
    output += second.output + delivery.notice(" No safe alternative. ") + delivery.finish(second.state)

    body = official_response(api, output)
    if api == "messages":
        assert body["stop_reason"] == "tool_use"
        assert [block["id"] for block in body["content"] if block["type"] == "tool_use"] == ["allowed"]
    elif api == "chat_completions":
        assert body["choices"][0]["finish_reason"] == "tool_calls"
        assert [call["id"] for call in body["choices"][0]["message"]["tool_calls"]] == ["allowed"]
    else:
        assert [item["call_id"] for item in body["output"] if item["type"] == "function_call"] == ["allowed"]


@pytest.mark.parametrize("api", ["messages", "chat_completions", "responses"])
def test_text_is_delivered_before_the_provider_finishes(api: API) -> None:
    delivery = StreamDelivery(api)
    delivery.begin_attempt()
    state = IncrementalStream(api)
    events = decoded(list(encode(api, response(api, "original", ["later"]))))
    output: list[bytes] = []
    for event in events:
        value = litellm.ModelResponseStream(**event) if api == "chat_completions" else event
        frames = state.add(value)
        if any(frame.requires for frame in frames):
            break
        for frame in frames:
            output.extend(delivery.emit(frame, state))

    assert not state.terminal
    assert "original text" in b"".join(output).decode()
    assert delivery.response == {}


@pytest.mark.parametrize("api", ["messages", "chat_completions", "responses"])
def test_duplicate_replacement_call_id_fails_closed(api: API) -> None:
    delivery = StreamDelivery(api)
    attempt(delivery, response(api, "original", ["allowed", "denied"]), {"allowed"})
    delivery.notice(" Denied. ")
    with pytest.raises(UnsupportedStream, match="duplicate"):
        attempt(delivery, response(api, "retry", ["allowed"]), {"allowed"})


def test_interleaved_chat_closes_the_allowed_call_behind_a_denied_call() -> None:
    delivery = StreamDelivery("chat_completions")
    template = decoded(list(encode("chat_completions", response("chat_completions", "original", []))))[0]

    def chunk(delta: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
        return {**template, "choices": [{"index": 0, "delta": delta, "finish_reason": reason}]}

    events = [
        chunk({"role": "assistant", "content": "Before."}),
        chunk(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "allowed",
                        "type": "function",
                        "function": {"name": "read", "arguments": '{"path":'},
                    }
                ]
            }
        ),
        chunk(
            {
                "tool_calls": [
                    {
                        "index": 1,
                        "id": "denied",
                        "type": "function",
                        "function": {"name": "read", "arguments": '{"path":"secret"}'},
                    }
                ]
            }
        ),
        chunk({"content": "Withheld tail."}),
        chunk({"tool_calls": [{"index": 0, "function": {"arguments": '"public"}'}}]}),
        chunk({}, "tool_calls"),
        {**template, "choices": [], "usage": {"prompt_tokens": 17, "completion_tokens": 4, "total_tokens": 21}},
    ]
    first = event_attempt(delivery, events, {"allowed"})
    output = first.output + delivery.notice(" Denied. ") + delivery.finish(first.state)

    body = official_response("chat_completions", output)
    assert body["choices"][0]["message"]["content"] == "Before.\n\n Denied. "
    assert body["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] == '{"path":"public"}'
    assert len(body["choices"][0]["message"]["tool_calls"]) == 1
    usage = [event for event in decoded(output) if event.get("usage")]
    assert len(usage) == 1 and usage[0]["choices"] == [] and usage[0]["usage"]["total_tokens"] == 21


def test_interleaved_responses_retains_late_reasoning_completion_and_opaque_payload() -> None:
    delivery = StreamDelivery("responses")
    body = response("responses", "original", ["denied"])
    reasoning = {"id": "rs_original", "type": "reasoning", "summary": [], "encrypted_content": "item-done-ciphertext"}
    call = body["output"][1]
    events = [
        {"type": "response.created", "response": {**body, "status": "in_progress", "output": []}},
        {"type": "response.output_item.added", "output_index": 0, "item": {**reasoning, "encrypted_content": None}},
        {"type": "response.output_item.added", "output_index": 1, "item": call},
        {"type": "response.output_item.done", "output_index": 1, "item": call},
        {"type": "response.output_item.done", "output_index": 0, "item": reasoning},
        {
            "type": "response.completed",
            "response": {**body, "output": [{**reasoning, "encrypted_content": "terminal-ciphertext"}, call]},
        },
    ]
    first = event_attempt(delivery, events, set())
    output = first.output + delivery.notice(" Denied. ") + delivery.finish(first.state)

    final = official_response("responses", output)
    assert [item["type"] for item in final["output"]] == ["reasoning", "message"]
    assert final["output"][0]["encrypted_content"] == "item-done-ciphertext"
    assert delivery.response["output"][0] == reasoning


def test_an_unclosed_visible_item_cannot_be_replaced_or_finished() -> None:
    delivery = StreamDelivery("responses")
    delivery.begin_attempt()
    state = IncrementalStream("responses")
    body = response("responses", "original", [])
    for event in [
        {"type": "response.created", "response": {**body, "status": "in_progress", "output": []}},
        {"type": "response.output_item.added", "output_index": 0, "item": body["output"][0]},
    ]:
        for frame in state.add(event):
            delivery.emit(frame, state)
    with pytest.raises(IncompleteStream, match="still incomplete"):
        delivery.begin_attempt()
    with pytest.raises(IncompleteStream, match="still incomplete"):
        delivery.notice(" Denied. ")
    with pytest.raises(IncompleteStream, match="still incomplete"):
        delivery.finish(state)


@pytest.mark.parametrize("api", ["messages", "chat_completions", "responses"])
def test_nonstream_replaces_all_original_calls_without_mutating_inputs(api: API) -> None:
    original = response(api, "original", ["first", "denied"])
    replacement = response(api, "retry", ["alternative"])
    before = json.dumps([original, replacement])

    composed = compose_nonstream(api, original, replacement, " Denied. ")

    assert json.dumps([original, replacement]) == before
    assert composed["usage"] == original["usage"]
    body = official_response(api, list(encode(api, composed)))
    assert body["model"] == "model_original"
    if api == "messages":
        assert [block["id"] for block in body["content"] if block["type"] == "tool_use"] == ["alternative"]
        assert [block["text"] for block in body["content"] if block["type"] == "text"] == [
            "original text",
            " Denied. ",
            "retry text",
        ]
    elif api == "chat_completions":
        assert [call["id"] for call in body["choices"][0]["message"]["tool_calls"]] == ["alternative"]
        assert body["choices"][0]["message"]["content"] == "original text\n\n Denied. \n\nretry text"
    else:
        assert [item["call_id"] for item in body["output"] if item["type"] == "function_call"] == ["alternative"]
        assert [item["content"][0]["text"] for item in body["output"] if item["type"] == "message"] == [
            "original text",
            " Denied. ",
            "retry text",
        ]


@pytest.mark.parametrize("api", ["messages", "chat_completions", "responses"])
def test_nonstream_exhaustion_has_no_executable_calls(api: API) -> None:
    composed = compose_nonstream(api, response(api, "original", ["denied"]), None, " Denied. ")
    body = official_response(api, list(encode(api, composed)))
    if api == "messages":
        assert body["stop_reason"] == "end_turn"
        assert [block["type"] for block in body["content"]] == ["text", "text"]
    elif api == "chat_completions":
        assert body["choices"][0]["finish_reason"] == "stop"
        assert body["choices"][0]["message"]["tool_calls"] is None
    else:
        assert [item["type"] for item in body["output"]] == ["message", "message"]


def test_nonstream_chat_rejects_uncomposable_populated_fields() -> None:
    original = response("chat_completions", "original", ["denied"])
    original["choices"][0]["message"]["audio"] = {"id": "audio-original", "data": "YQ=="}
    with pytest.raises(UnsupportedStream, match="Unsupported Chat message fields"):
        compose_nonstream("chat_completions", original, None, " Denied. ")


def test_messages_preserves_signed_thinking_and_terminal_stop_details() -> None:
    delivery = StreamDelivery("messages")
    body = response("messages", "original", [])
    body["content"] = [{"type": "thinking", "thinking": "Reasoning.", "signature": "opaque-signature"}]
    body.update(stop_reason="refusal", stop_details={"type": "refusal", "category": "cyber", "explanation": "declined"})

    first = attempt(delivery, body, set())
    final = official_response("messages", first.output + delivery.finish(first.state))

    assert final["content"] == [{"type": "thinking", "thinking": "Reasoning.", "signature": "opaque-signature"}]
    assert final["stop_reason"] == "refusal"
    assert final["stop_details"]["explanation"] == "declined"
    assert final["usage"]["output_tokens"] == 7


@pytest.mark.parametrize("api", ["messages", "chat_completions", "responses"])
def test_delivery_rejects_a_call_before_evaluation(api: API) -> None:
    delivery = StreamDelivery(api)
    delivery.begin_attempt()
    state = IncrementalStream(api)
    events = decoded(list(encode(api, response(api, "original", ["unapproved"]))))
    for event in events:
        value = litellm.ModelResponseStream(**event) if api == "chat_completions" else event
        frames = state.add(value)
        for frame in frames:
            if frame.requires:
                with pytest.raises(UnsupportedStream, match="unevaluated"):
                    delivery.emit(frame, state)
                return
            delivery.emit(frame, state)
    pytest.fail("The fixture must contain an executable call")


def test_responses_cannot_change_identity_in_the_final_envelope() -> None:
    delivery = StreamDelivery("responses")
    events = decoded(list(encode("responses", response("responses", "original", []))))
    events[-1]["response"]["id"] = "resp_changed"
    with pytest.raises(UnsupportedStream, match="identity changed"):
        event_attempt(delivery, events, set())


@pytest.mark.parametrize("api", ["messages", "chat_completions", "responses"])
def test_streaming_exhaustion_without_an_approved_call_finishes_as_text(api: API) -> None:
    delivery = StreamDelivery(api)
    first = attempt(delivery, response(api, "original", ["denied"]), set())
    final = official_response(
        api, first.output + delivery.notice(" No safe alternative. ") + delivery.finish(first.state)
    )
    if api == "messages":
        assert final["stop_reason"] == "end_turn"
        assert [block["type"] for block in final["content"]] == ["text", "text"]
    elif api == "chat_completions":
        assert final["choices"][0]["finish_reason"] == "stop"
        assert final["choices"][0]["message"]["tool_calls"] is None
    else:
        assert [item["type"] for item in final["output"]] == ["message", "message"]


def test_missing_late_approved_chat_arguments_prevents_checkpoint() -> None:
    delivery = StreamDelivery("chat_completions")
    delivery.begin_attempt()
    state = IncrementalStream("chat_completions")
    events = decoded(list(encode("chat_completions", response("chat_completions", "original", ["allowed"]))))
    original_call = events[1]["choices"][0]["delta"]["tool_calls"][0]
    original_call["function"]["arguments"] = '{"path":'
    late: dict[str, Any] = {
        **events[1],
        "choices": [
            {
                "index": 0,
                "delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"allowed"}'}}]},
                "finish_reason": None,
            }
        ],
    }
    frames: list[PendingEvent] = []
    for event in [events[0], events[1], late, events[2]]:
        frames.extend(state.add(litellm.ModelResponseStream(**event)))
    state.allowed.add(0)
    for frame in frames[:2]:
        delivery.emit(frame, state)

    with pytest.raises(IncompleteStream, match="Chat call is still incomplete"):
        delivery.checkpoint(state)


def test_legacy_chat_call_retains_its_complete_arguments_and_finish_reason() -> None:
    delivery = StreamDelivery("chat_completions")
    delivery.begin_attempt()
    state = IncrementalStream("chat_completions")
    template = decoded(list(encode("chat_completions", response("chat_completions", "original", []))))[0]
    frames: list[PendingEvent] = []
    for delta, reason in [
        ({"role": "assistant", "content": "Checking."}, None),
        ({"function_call": {"name": "read", "arguments": '{"path":'}}, None),
        ({"function_call": {"arguments": '"public"}'}}, None),
        ({}, "function_call"),
    ]:
        event: dict[str, Any] = {**template, "choices": [{"index": 0, "delta": delta, "finish_reason": reason}]}
        frames.extend(state.add(litellm.ModelResponseStream(**event)))
    state.allowed.add(0)
    output = [chunk for frame in frames for chunk in delivery.emit(frame, state)]

    final = official_response("chat_completions", output + delivery.finish(state))

    assert final["choices"][0]["finish_reason"] == "function_call"
    assert final["choices"][0]["message"]["function_call"] == {"name": "read", "arguments": '{"path":"public"}'}


@pytest.mark.parametrize("empty_choices", [True, False])
def test_chat_usage_after_immediate_finish_is_preserved_once(empty_choices: bool) -> None:
    delivery = StreamDelivery("chat_completions")
    body = response("chat_completions", "original", [])
    body.pop("usage")
    first = attempt(delivery, body, set())
    output = first.output + delivery.finish(first.state)
    late: dict[str, Any] = {
        "id": "chatcmpl_original",
        "object": "chat.completion.chunk",
        "model": "model_original",
        "created": 1,
        "choices": [] if empty_choices else [{"index": 0, "delta": {}, "finish_reason": None}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 9, "total_tokens": 21},
    }
    for frame in first.state.add(litellm.ModelResponseStream(**late)):
        output.extend(delivery.emit(frame, first.state))

    final = official_response("chat_completions", output)
    assert final["choices"][0]["message"]["content"] == "original text"
    assert final["usage"]["total_tokens"] == 21
    assert delivery.response["usage"]["total_tokens"] == 21
    assert len([event for event in decoded(output) if event.get("usage")]) == 1
    assert sum(bool(event["choices"] and event["choices"][0]["finish_reason"]) for event in decoded(output)) == 1


def test_messages_container_from_final_delta_reaches_the_sdk_snapshot() -> None:
    delivery = StreamDelivery("messages")
    events = decoded(list(encode("messages", response("messages", "original", []))))
    events[0]["message"]["container"] = None
    events[-2]["delta"]["container"] = {"id": "container_final", "expires_at": "2026-10-07T00:00:00Z"}
    first = event_attempt(delivery, events, set())
    final = official_response("messages", first.output + delivery.finish(first.state))
    assert final["container"]["id"] == "container_final"
    assert delivery.response["container"] == events[-2]["delta"]["container"]


@pytest.mark.parametrize("kind", ["local_shell_call", "tool_search_call"])
def test_native_responses_call_can_replace_a_denied_nonstream_call(kind: str) -> None:
    original = response("responses", "original", ["denied"])
    replacement = response("responses", "retry", [])
    item: dict[str, Any] = {"type": kind, "id": "native_item", "call_id": "allowed", "status": "completed"}
    if kind == "local_shell_call":
        item["action"] = {"type": "exec", "command": ["pwd"], "env": {}}
    else:
        item.update(execution="client", arguments={"query": "lookup"})
    replacement["output"].append(item)

    composed = compose_nonstream("responses", original, replacement, " Denied. ")
    final = official_response("responses", list(encode("responses", composed)))

    assert [entry["type"] for entry in final["output"]] == ["message", "message", "message", kind]
    assert final["output"][-1]["call_id"] == "allowed"
    assert composed["output"][-1] == item


@pytest.mark.parametrize(
    ("api", "body", "notice", "error"),
    [
        ("messages", {"content": []}, "", "notice must not be empty"),
        ("messages", {"content": [{"type": "future_executable_block"}]}, " Denied. ", "Unsupported content"),
        ("responses", {"output": [{"type": "future_client_call"}]}, " Denied. ", "Unsupported content"),
        (
            "responses",
            {"output": [{"type": "tool_search_call", "execution": "server"}]},
            " Denied. ",
            "client-executed",
        ),
        ("responses", {}, " Denied. ", "Malformed resampled response"),
        ("chat_completions", {"choices": []}, " Denied. ", "Only one Chat choice"),
        ("chat_completions", {"choices": [{"index": 1, "message": {}}]}, " Denied. ", "Only one Chat choice"),
        (
            "chat_completions",
            {"choices": [{"index": 0, "message": {"role": "tool"}}]},
            " Denied. ",
            "Unsupported Chat message",
        ),
        (
            "chat_completions",
            {"choices": [{"index": 0, "message": {"role": "assistant", "content": [{"type": "audio"}]}}]},
            " Denied. ",
            "scalar content",
        ),
    ],
)
def test_nonstream_refuses_shapes_that_cannot_be_safely_composed(
    api: API, body: dict[str, Any], notice: str, error: str
) -> None:
    """Unknown actions, multimodal content and missing envelopes must never become partial successful replies."""
    before = json.dumps(body)
    with pytest.raises(UnsupportedStream, match=error):
        compose_nonstream(api, body, None, notice)
    assert json.dumps(body) == before


def test_nonstream_chat_preserves_refusal_and_reasoning_while_replacing_calls() -> None:
    original = response("chat_completions", "original", ["denied"])
    original["choices"][0]["message"].update(refusal="First refusal. ", reasoning_content="First reasoning. ")
    original["choices"][0]["logprobs"] = {"content": [{"token": "original", "logprob": -1}]}
    replacement = response("chat_completions", "retry", ["allowed"])
    replacement["choices"][0]["message"].update(refusal="Second refusal.", reasoning_content="Second reasoning.")

    composed = compose_nonstream("chat_completions", original, replacement, " Denied. ")
    final = official_response("chat_completions", list(encode("chat_completions", composed)))

    assert final["choices"][0]["message"]["refusal"] == "First refusal. Second refusal."
    assert composed["choices"][0]["message"]["reasoning_content"] == "First reasoning. Second reasoning."
    assert final["choices"][0]["message"]["content"] == "original text\n\n Denied. \n\nretry text"
    assert final["choices"][0]["message"]["tool_calls"][0]["id"] == "allowed"
    assert final["choices"][0]["logprobs"] is None


def test_nonstream_legacy_chat_replacement_retains_one_complete_function_call() -> None:
    original = response("chat_completions", "original", ["denied"])
    replacement = response("chat_completions", "retry", [])
    replacement["choices"][0]["message"]["function_call"] = {"name": "read", "arguments": '{"path":"safe"}'}
    composed = compose_nonstream("chat_completions", original, replacement, " Denied. ")
    final = ChatCompletion.model_validate(composed)
    assert final.choices[0].finish_reason == "function_call"
    assert final.choices[0].message.function_call is not None
    assert final.choices[0].message.function_call.arguments == '{"path":"safe"}'
    assert final.choices[0].message.tool_calls is None


def test_nonstream_messages_uses_replacement_refusal_and_container_metadata() -> None:
    original = response("messages", "original", ["denied"])
    original["stop_details"] = {"type": "refusal", "category": "old", "explanation": "Old refusal"}
    replacement = response("messages", "retry", [])
    replacement.update(
        stop_reason="refusal",
        stop_details={"type": "refusal", "category": "cyber", "explanation": "Cannot continue"},
        container={"id": "container_retry", "expires_at": "2026-10-07T00:00:00Z"},
    )
    composed = compose_nonstream("messages", original, replacement, " Denied. ")
    final = official_response("messages", list(encode("messages", composed)))
    assert final["stop_reason"] == "refusal"
    assert final["stop_details"]["explanation"] == "Cannot continue"
    assert final["container"]["id"] == "container_retry"
    assert final["usage"]["input_tokens"] == 11


def test_messages_custom_stop_sequence_survives_delivery() -> None:
    delivery = StreamDelivery("messages")
    body = response("messages", "original", [])
    body.update(stop_reason="stop_sequence", stop_sequence="END_CUSTOM")
    first = attempt(delivery, body, set())
    final = official_response("messages", first.output + delivery.finish(first.state))
    assert final["stop_reason"] == "stop_sequence" and final["stop_sequence"] == "END_CUSTOM"
    assert [block["text"] for block in final["content"]] == ["original text"]


@pytest.mark.parametrize("action", ["begin", "notice", "finish", "emit"])
def test_finished_messages_cannot_be_reopened_or_completed_twice(action: str) -> None:
    """A caller retrying cleanup cannot append a second response or duplicate the terminal event."""
    delivery = StreamDelivery("messages")
    first = attempt(delivery, response("messages", "original", []), set())
    output = first.output + delivery.finish(first.state)
    with pytest.raises(UnsupportedStream, match="finish"):
        if action == "begin":
            delivery.begin_attempt()
        elif action == "notice":
            delivery.notice("Late notice")
        elif action == "finish":
            delivery.finish(first.state)
        else:
            delivery.emit(PendingEvent(data={"type": "ping"}), first.state)
    assert sum(event["type"] == "message_stop" for event in decoded(output)) == 1


def test_unstarted_delivery_cannot_publish_frames_from_another_request() -> None:
    delivery = StreamDelivery("messages")
    state = IncrementalStream("messages")
    first_event = decoded(list(encode("messages", response("messages", "original", []))))[0]
    frame = state.add(first_event)[0]
    with pytest.raises(UnsupportedStream, match="Invalid delivery lifecycle"):
        delivery.emit(frame, state)
    delivery.begin_attempt()
    with pytest.raises(UnsupportedStream, match="Invalid delivery lifecycle"):
        delivery.emit(frame, IncrementalStream("responses"))
    with pytest.raises(UnsupportedStream, match="unstarted"):
        delivery.finish(state)


def test_delivery_cannot_checkpoint_a_truncated_visible_response() -> None:
    delivery = StreamDelivery("messages")
    delivery.begin_attempt()
    state = IncrementalStream("messages")
    first_event = decoded(list(encode("messages", response("messages", "original", []))))[0]
    for frame in state.add(first_event):
        delivery.emit(frame, state)
    with pytest.raises(IncompleteStream, match="unfinished provider"):
        delivery.checkpoint(state)


@pytest.mark.parametrize("api", ["responses", "chat_completions"])
def test_provider_identity_changes_cannot_be_hidden_by_the_original_envelope(api: API) -> None:
    delivery = StreamDelivery(api)
    delivery.begin_attempt()
    state = IncrementalStream(api)
    events = decoded(list(encode(api, response(api, "original", []))))
    first = litellm.ModelResponseStream(**events[0]) if api == "chat_completions" else events[0]
    for frame in state.add(first):
        delivery.emit(frame, state)
    if api == "responses":
        changed = {"type": "response.in_progress", "response": {**events[0]["response"], "id": "different"}}
    else:
        changed_payload: dict[str, Any] = {**events[0], "id": "different"}
        changed = litellm.ModelResponseStream(**changed_payload)
    with pytest.raises(UnsupportedStream, match="identity changed"):
        for frame in state.add(changed):
            delivery.emit(frame, state)


@pytest.mark.parametrize("changed", ["content", "identity"])
def test_post_finish_chat_frames_cannot_smuggle_content_or_another_request(changed: str) -> None:
    delivery = StreamDelivery("chat_completions")
    first = attempt(delivery, response("chat_completions", "original", []), set())
    output = first.output + delivery.finish(first.state)
    event: dict[str, Any] = {
        "id": "chatcmpl_original",
        "model": "model_original",
        "created": 1,
        "choices": [{"index": 0, "delta": {}, "finish_reason": None}],
    }
    if changed == "content":
        event["choices"][0]["delta"] = {
            "tool_calls": [{"index": 0, "id": "unevaluated", "function": {"name": "execute", "arguments": "{}"}}]
        }
    else:
        event["id"] = "different"
    with pytest.raises(UnsupportedStream, match="continued|identity changed"):
        delivery.emit(PendingEvent(data=event), first.state)
    assert official_response("chat_completions", output)["choices"][0]["message"]["tool_calls"] is None


def test_late_replacement_usage_does_not_overwrite_original_accounting() -> None:
    delivery = StreamDelivery("chat_completions")
    first = attempt(delivery, response("chat_completions", "original", ["denied"]), set())
    output = first.output + delivery.notice(" Denied. ")
    second = attempt(delivery, response("chat_completions", "retry", []), set())
    output += second.output + delivery.finish(second.state)
    late = litellm.ModelResponseStream(
        id="chatcmpl_retry",
        model="model_retry",
        created=1,
        choices=[],
        usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    )
    for frame in second.state.add(late):
        output.extend(delivery.emit(frame, second.state))
    final = official_response("chat_completions", output)
    assert final["usage"]["total_tokens"] == 18
    assert len([event for event in decoded(output) if event.get("usage")]) == 1
    assert delivery.response["usage"]["total_tokens"] == 18


def test_chat_without_initial_text_still_exposes_a_valid_assistant_notice() -> None:
    delivery = StreamDelivery("chat_completions")
    events = decoded(list(encode("chat_completions", response("chat_completions", "original", ["denied"]))))
    first = event_attempt(delivery, events[1:], set())
    assert first.output == []
    output = delivery.notice("Denied before any content.") + delivery.finish(first.state)
    final = official_response("chat_completions", output)
    assert final["choices"][0]["message"]["role"] == "assistant"
    assert final["choices"][0]["message"]["content"] == "Denied before any content."
    assert final["choices"][0]["message"]["tool_calls"] is None


class DeliveryRouter(BaseModel):
    """A provider boundary returning one approved alternative through the normal callback retry path."""

    requests: list[dict[str, Any]] = Field(default_factory=list)

    async def acompletion(self, **kwargs: Any) -> AsyncIterator[Any]:
        self.requests.append(kwargs)

        async def chunks() -> AsyncIterator[Any]:
            for event in decoded(list(encode("chat_completions", response("chat_completions", "retry", ["allowed"])))):
                yield litellm.ModelResponseStream(**event)

        return chunks()


@pytest.mark.parametrize("coalesced_finish", [False, True])
async def test_callback_resamples_a_denied_tool_only_chat_stream_without_a_role_chunk(
    monkeypatch: pytest.MonkeyPatch, coalesced_finish: bool
) -> None:
    """The first safe frame may be the finish marker; denial must still become a valid assistant notice and retry."""
    router = DeliveryRouter()
    monkeypatch.setattr(proxy_server, "llm_router", router)
    judged: list[list[str]] = []
    recorded = asyncio.Event()

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)["response_body"]
        calls = body["choices"][0]["message"].get("tool_calls") or []
        if not calls:
            recorded.set()
            return httpx.Response(200, json=[])
        judged.append([call["id"] for call in calls])
        return httpx.Response(
            200,
            json=[
                {
                    "decision": "deny" if call["id"] == "denied" else "allow",
                    "judged_decision": "deny" if call["id"] == "denied" else "allow",
                    "decision_source": "rule",
                    "enforcement_mode": "enforce",
                    "tool_use_id": call["id"],
                    "verdict": {"explanation": "Read the allowed path instead."},
                    "latency_ms": 1,
                }
                for call in calls
            ],
        )

    def client() -> AsyncWatcherClient:
        return AsyncWatcherClient(
            "http://watcher.test",
            api_key="fixture",
            httpx_client=httpx.AsyncClient(base_url="http://watcher.test", transport=httpx.MockTransport(handle)),
        )

    original = response("chat_completions", "original", ["denied"])
    events = decoded(list(encode("chat_completions", original)))[1:]
    if coalesced_finish:
        events[0]["choices"][0]["finish_reason"] = "tool_calls"
        events[0]["usage"] = original["usage"]
        events = events[:1]
    assert "role" not in events[0]["choices"][0]["delta"]
    assert "content" not in events[0]["choices"][0]["delta"]

    async def source() -> AsyncIterator[Any]:
        for event in events:
            yield litellm.ModelResponseStream(**event)

    request = {"model": "fixture", "stream": True, "messages": [{"role": "user", "content": "Read a file."}]}
    data = {
        "model": "fixture",
        "proxy_server_request": {
            "url": "http://proxy/v1/chat/completions",
            "body": request,
            "headers": {"x-watcher-session-id": "12345678-1234-4234-8234-123456789abc"},
        },
    }
    callback = WatcherCallback(client)
    async with asyncio.timeout(3):
        output = [
            chunk
            async for chunk in callback.async_post_call_streaming_iterator_hook(
                UserAPIKeyAuth(user_email="delivery@example.test"), source(), data
            )
        ]
        await recorded.wait()

    final = official_response("chat_completions", output)
    message = final["choices"][0]["message"]
    assert message["role"] == "assistant" and final["choices"][0]["finish_reason"] == "tool_calls"
    assert [call["id"] for call in message["tool_calls"]] == ["allowed"]
    assert "Read the allowed path instead." in message["content"] and "retry text" in message["content"]
    assert judged == [["denied"], ["allowed"]]
    assert len(router.requests) == 1 and router.requests[0]["stream"] is True
    assert "Read the allowed path instead." in json.dumps(router.requests[0]["messages"])


def test_incomplete_responses_retry_preserves_limit_reason_and_original_usage() -> None:
    delivery = StreamDelivery("responses")
    first = attempt(delivery, response("responses", "original", ["denied"]), set())
    output = first.output + delivery.notice(" Denied. ")
    replacement = response("responses", "retry", [])
    replacement.update(status="incomplete", incomplete_details={"reason": "max_output_tokens"}, error=None)
    replacement["usage"]["total_tokens"] = 99
    events = decoded(list(encode("responses", replacement)))
    events.insert(1, {"type": "response.in_progress", "response": events[0]["response"]})
    second = event_attempt(delivery, events, set())
    output += second.output + delivery.finish(second.state)

    final = official_response("responses", output)

    assert final["status"] == "incomplete"
    assert final["incomplete_details"] == {"reason": "max_output_tokens"}
    assert final["error"] is None
    assert final["usage"]["total_tokens"] == 18
    assert [item["content"][0]["text"] for item in final["output"]] == ["original text", " Denied. ", "retry text"]


def test_responses_in_progress_metadata_preserves_original_envelope_and_output() -> None:
    delivery = StreamDelivery("responses")
    events = decoded(list(encode("responses", response("responses", "original", []))))
    events.insert(1, {"type": "response.in_progress", "response": events[0]["response"]})
    first = event_attempt(delivery, events, set())
    output = first.output + delivery.finish(first.state)
    final = official_response("responses", output)
    assert [event["type"] for event in decoded(output)[:2]] == ["response.created", "response.in_progress"]
    assert final["id"] == "resp_original" and final["output"][0]["content"][0]["text"] == "original text"


def test_invalid_responses_completion_status_cannot_claim_success() -> None:
    delivery = StreamDelivery("responses")
    events = decoded(list(encode("responses", response("responses", "original", []))))
    events[-1]["response"]["status"] = "failed"
    first = event_attempt(delivery, events, set())
    with pytest.raises(UnsupportedStream, match="Invalid final Responses status"):
        delivery.finish(first.state)
    assert "original text" in b"".join(first.output).decode()
    assert all(event["type"] != "response.completed" for event in decoded(first.output))


@pytest.mark.parametrize(
    ("api", "status"), [("messages", 400), ("messages", 504), ("chat_completions", 503), ("responses", 504)]
)
def test_stream_error_preserves_visible_prefix_and_uses_the_native_error_shape(api: API, status: int) -> None:
    delivery = StreamDelivery(api)
    first = attempt(delivery, response(api, "original", ["denied"]), set())
    output = first.output + [delivery.error("watcher_timeout", "Watcher timed out.", status)]
    events = decoded(output)
    error = events[-1]
    assert "original text" in b"".join(first.output).decode()
    assert "Watcher timed out." in b"".join(output).decode()
    if api == "messages":
        validated = ErrorResponse.model_validate(error)
        assert validated.error.type == ("overloaded_error" if status >= 500 else "invalid_request_error")
        assert all(
            event["type"] != "content_block_start" or event["content_block"]["type"] != "tool_use" for event in events
        )
    elif api == "responses":
        validated = TypeAdapter(ResponseStreamEvent).validate_python(error)
        assert validated.type == "error" and validated.code == "watcher_timeout"
        assert [event["sequence_number"] for event in events] == list(range(len(events)))
        assert all(
            event["type"] != "response.output_item.added" or event["item"]["type"] != "function_call"
            for event in events
        )
    else:
        assert error == {
            "error": {"type": "watcher_timeout", "code": "watcher_timeout", "message": "Watcher timed out."}
        }
        assert all(not event.get("choices") or not event["choices"][0]["delta"].get("tool_calls") for event in events)
