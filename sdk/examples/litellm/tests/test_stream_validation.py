"""Check provider protocol validation through the public streaming callback.

Malformed events must fail before an incomplete tool reaches either Watcher or
the client. Supported variants use real SDK accumulation or assembled wire
content, so accepting them also checks the client-visible protocol.
"""

import asyncio
import json
from typing import Any

import litellm
import pytest
from litellm.types.utils import Delta, StreamingChoices
from test_delivery import official_response
from test_incremental_safety import (
    USER,
    WatcherPeer,
    chat,
    chat_tool,
    collect,
    decoded,
    message_start,
    message_tool,
    rejected,
    request_data,
    response_added,
    response_delta,
    response_done,
    response_end,
    response_item,
    response_start,
    source,
    sse,
)
from test_stream_compatibility import responses_body, responses_start
from watcher_litellm.callback import WatcherCallback
from watcher_litellm.streams import UnsupportedStream, assemble, encode


@pytest.mark.parametrize(
    "invalid_event",
    [
        message_start([]),
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}},
        {"type": "message_stop"},
        {"type": "content_block_stop", "index": 1},
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": {"unexpected": "object"}},
        },
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {"type": "fallback", "content": "replacement"},
        },
    ],
    ids=["duplicate-start", "interrupted-block", "premature-stop", "wrong-index", "malformed-json", "fallback"],
)
async def test_messages_invalid_boundary_withholds_incomplete_call(invalid_event: dict[str, Any]) -> None:
    peer = WatcherPeer()
    events = [message_start([]), *message_tool(0, "held_call", "held.txt")[:2], invalid_event]

    output = await rejected(WatcherCallback(peer.client), "messages", [sse(event) for event in events])

    assert peer.requests == []
    assert [event["type"] for event in output] == ["message_start", "error"]
    assert "held_call" not in json.dumps(output)


async def test_messages_final_metadata_cannot_introduce_content() -> None:
    peer = WatcherPeer()
    events = [
        message_start([]),
        {
            "type": "message_delta",
            "delta": {"content": [{"type": "tool_use", "id": "hidden", "name": "run", "input": {}}]},
        },
    ]

    output = await rejected(WatcherCallback(peer.client), "messages", [sse(event) for event in events])

    assert peer.requests == []
    assert "hidden" not in json.dumps(output)
    assert output[-1]["type"] == "error"


@pytest.mark.parametrize("bad_text", [{"command": "hidden"}, ["hidden"], 17])
async def test_messages_text_delta_rejects_non_string_value(bad_text: Any) -> None:
    peer = WatcherPeer()
    events = [
        message_start([]),
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": bad_text}},
    ]

    output = await rejected(WatcherCallback(peer.client), "messages", [sse(event) for event in events])

    assert peer.requests == []
    assert not any(event["type"] == "content_block_delta" for event in output)
    assert output[-1]["type"] == "error"


@pytest.mark.parametrize(
    "choices",
    [
        [{"index": 1, "delta": {"content": "hidden"}, "finish_reason": None}],
        [
            {"index": 0, "delta": {"content": "hidden"}, "finish_reason": None},
            {"index": 1, "delta": {"content": "alternative"}, "finish_reason": None},
        ],
    ],
    ids=["nonzero-choice", "multiple-choices"],
)
async def test_chat_rejects_ambiguous_choice_without_forwarding_it(choices: list[dict[str, Any]]) -> None:
    peer = WatcherPeer()
    invalid = litellm.ModelResponseStream(
        id="chatcmpl_invalid", model="fixture", created=1, choices=[StreamingChoices(**choice) for choice in choices]
    )

    output = await rejected(WatcherCallback(peer.client), "chat_completions", [chat({"content": "before"}), invalid])

    assert peer.requests == []
    assert "before" in json.dumps(output)
    assert "hidden" not in json.dumps(output)


@pytest.mark.parametrize(
    "deltas",
    [
        [{"tool_calls": [chat_tool(1, "{}", "held_call")]}],
        [
            {
                "tool_calls": [
                    {"index": 0, "id": "held_call", "type": "custom", "custom": {"name": "shell", "input": "pwd"}}
                ]
            }
        ],
        [
            {"function_call": {"name": "read_file", "arguments": "{"}},
            {"tool_calls": [chat_tool(0, "{}", "held_call")]},
        ],
        [
            {"tool_calls": [chat_tool(0, "{", "held_call")]},
            {"function_call": {"name": "read_file", "arguments": "{}"}},
        ],
    ],
    ids=["nonsequential-index", "unsupported-type", "legacy-then-modern", "modern-then-legacy"],
)
async def test_chat_rejects_inconsistent_call_shape_before_grading(deltas: list[dict[str, Any]]) -> None:
    peer = WatcherPeer()
    chunks = [chat({"content": "before"}), *(chat(delta) for delta in deltas), chat({}, "tool_calls")]

    output = await rejected(WatcherCallback(peer.client), "chat_completions", chunks)

    assert peer.requests == []
    assert "before" in json.dumps(output)
    assert "held_call" not in json.dumps(output)
    assert not any(choice["delta"].get("function_call") for event in output for choice in event.get("choices", []))


async def test_chat_provider_error_drops_unfinished_call_and_buffered_text() -> None:
    peer = WatcherPeer()
    chunks = [
        chat({"content": "before"}),
        chat({"tool_calls": [chat_tool(0, '{"path":', "held_call")]}),
        chat({"content": "withheld"}),
        {"error": {"message": "Provider failed"}},
    ]

    output = await rejected(WatcherCallback(peer.client), "chat_completions", chunks)

    assert peer.requests == []
    assert "before" in json.dumps(output)
    assert "held_call" not in json.dumps(output)
    assert "withheld" not in json.dumps(output)
    assert output[-1]["error"]["code"] == "stream_error"


@pytest.mark.parametrize(
    "invalid_event",
    [
        response_start(),
        {"type": "error", "message": "Provider failed"},
        {"type": "response.failed", "response": {"status": "failed"}},
        {**response_delta(0, "held_call", "hidden"), "item_id": "another_item"},
        response_done(0, {**response_item("held_call", ""), "id": "another_item"}),
        response_done(0, {**response_item("held_call", ""), "type": "custom_tool_call"}),
        {
            "type": "response.function_call_arguments.done",
            "output_index": 0,
            "item_id": "fc_held_call",
            "arguments": "hidden",
        },
        {
            "type": "response.function_call_arguments.done",
            "output_index": 0,
            "item_id": "fc_held_call",
            "arguments": "",
            "name": "other_function",
        },
        {
            "type": "response.custom_tool_call_input.delta",
            "output_index": 0,
            "item_id": "fc_held_call",
            "delta": "hidden",
        },
        response_end([response_item("held_call", "")]),
    ],
    ids=[
        "duplicate-start",
        "provider-error",
        "provider-failed",
        "delta-identity",
        "done-identity",
        "done-type",
        "done-arguments",
        "done-name",
        "wrong-event-family",
        "unfinished-item",
    ],
)
async def test_responses_invalid_boundary_withholds_incomplete_call(invalid_event: dict[str, Any]) -> None:
    peer = WatcherPeer()
    events = [response_start(), response_added(0, response_item("held_call", "")), invalid_event]

    output = await rejected(WatcherCallback(peer.client), "responses", events)

    assert peer.requests == []
    assert [event["type"] for event in output] == ["response.created", "error"]
    assert "held_call" not in json.dumps(output)
    assert output[-1]["sequence_number"] == output[-2]["sequence_number"] + 1


@pytest.mark.parametrize(
    "invalid_event",
    [
        response_added(1, response_item("hidden", "{}")),
        response_added(0, {**response_item("hidden", "{}"), "type": "computer_call"}),
    ],
    ids=["nonsequential-index", "unsupported-client-call"],
)
async def test_responses_invalid_item_start_is_never_released(invalid_event: dict[str, Any]) -> None:
    peer = WatcherPeer()

    output = await rejected(WatcherCallback(peer.client), "responses", [response_start(), invalid_event])

    assert peer.requests == []
    assert "hidden" not in json.dumps(output)
    assert [event["type"] for event in output] == ["response.created", "error"]


async def test_responses_completed_approved_call_cannot_receive_late_arguments() -> None:
    peer = WatcherPeer()
    peer.decide("allowed", "allow")
    item = response_item("allowed", '{"path":"allowed.txt"}')
    events = [response_start(), response_added(0, item), response_done(0, item), response_delta(0, "allowed", "late")]

    output = await rejected(WatcherCallback(peer.client), "responses", events)

    assert len(peer.requests) == 1
    assert [event["item"] for event in output if event["type"] == "response.output_item.done"] == [item]
    assert "late" not in json.dumps(output)
    assert output[-1]["type"] == "error"


async def test_responses_content_part_indices_must_be_sequential() -> None:
    peer = WatcherPeer()
    item = {"type": "message", "id": "msg", "role": "assistant", "status": "in_progress", "content": []}
    events = [
        response_start(),
        response_added(0, item),
        {
            "type": "response.content_part.added",
            "output_index": 0,
            "item_id": "msg",
            "content_index": 1,
            "part": {"type": "output_text", "text": "hidden", "annotations": []},
        },
    ]

    output = await rejected(WatcherCallback(peer.client), "responses", events)

    assert peer.requests == []
    assert "hidden" not in json.dumps(output)
    assert output[-1]["type"] == "error"


async def test_responses_fragmented_custom_input_and_existing_input_history_survive() -> None:
    peer = WatcherPeer()
    peer.decide("custom", "allow")
    peer.decide("second", "allow")
    custom = {
        "type": "custom_tool_call",
        "id": "custom_item",
        "call_id": "custom",
        "name": "shell",
        "input": "printf café",
        "status": "completed",
    }
    second = response_item("second", '{"path":"second.txt"}')
    events = [
        responses_start(),
        response_added(0, {**custom, "input": "", "status": "in_progress"}),
        *(
            {
                "type": "response.custom_tool_call_input.delta",
                "output_index": 0,
                "item_id": "custom_item",
                "delta": part,
            }
            for part in ["printf ", "café"]
        ),
        {
            "type": "response.custom_tool_call_input.done",
            "output_index": 0,
            "item_id": "custom_item",
            "input": custom["input"],
            "name": "shell",
        },
        response_done(0, custom),
        response_added(1, second),
        response_done(1, second),
        {"type": "response.completed", "response": responses_body([custom, second])},
    ]
    data = request_data("responses")
    prior = [{"role": "user", "content": "Use the available tools."}]
    data["proxy_server_request"]["body"]["input"] = prior
    callback = WatcherCallback(peer.client)
    async with asyncio.timeout(3):
        output = [chunk async for chunk in callback.async_post_call_streaming_iterator_hook(USER, source(events), data)]

    final = official_response("responses", output)
    assert final["output"][0]["input"] == "printf café"
    assert [item["call_id"] for item in final["output"]] == ["custom", "second"]
    assert [request["response_body"]["output"][0]["call_id"] for request in peer.requests] == ["custom", "second"]
    assert peer.requests[1]["request_body"]["input"] == [*prior, custom]
    assert data["proxy_server_request"]["body"]["input"] == prior


async def test_responses_refusal_and_reasoning_streams_reach_official_client() -> None:
    peer = WatcherPeer()
    reasoning = {
        "type": "reasoning",
        "id": "reasoning_item",
        "summary": [{"type": "summary_text", "text": "Considered request."}],
        "encrypted_content": "opaque_signature",
        "status": "completed",
    }
    refusal = {"type": "refusal", "refusal": "I cannot comply."}
    message = {
        "type": "message",
        "id": "refusal_item",
        "role": "assistant",
        "status": "completed",
        "content": [refusal],
    }
    reasoning_location = {"output_index": 0, "item_id": "reasoning_item", "summary_index": 0}
    message_location = {"output_index": 1, "item_id": "refusal_item", "content_index": 0}
    events = [
        responses_start(),
        response_added(0, {**reasoning, "summary": [], "status": "in_progress"}),
        {
            "type": "response.reasoning_summary_part.added",
            **reasoning_location,
            "part": {"type": "summary_text", "text": ""},
        },
        {"type": "response.reasoning_summary_text.delta", **reasoning_location, "delta": "Considered request."},
        {"type": "response.reasoning_summary_text.done", **reasoning_location, "text": "Considered request."},
        {"type": "response.reasoning_summary_part.done", **reasoning_location, "part": reasoning["summary"][0]},
        response_done(0, reasoning),
        response_added(1, {**message, "content": [], "status": "in_progress"}),
        {"type": "response.content_part.added", **message_location, "part": {"type": "refusal", "refusal": ""}},
        {"type": "response.refusal.delta", **message_location, "delta": "I cannot "},
        {"type": "response.refusal.delta", **message_location, "delta": "comply."},
        {"type": "response.refusal.done", **message_location, "refusal": refusal["refusal"]},
        {"type": "response.content_part.done", **message_location, "part": refusal},
        response_done(1, message),
        {"type": "response.completed", "response": responses_body([reasoning, message])},
    ]

    output = await collect(WatcherCallback(peer.client), "responses", events)

    final = official_response("responses", output)
    assert peer.requests == []
    assert final["output"][0]["summary"] == reasoning["summary"]
    assert final["output"][0]["encrypted_content"] == "opaque_signature"
    assert final["output"][1]["content"] == [refusal]
    assert [event["delta"] for event in decoded(output) if event["type"] == "response.refusal.delta"] == [
        "I cannot ",
        "comply.",
    ]


async def test_messages_citations_and_unsigned_thinking_survive_callback_and_encoding() -> None:
    peer = WatcherPeer()
    citation = {
        "type": "char_location",
        "cited_text": "Source",
        "document_index": 0,
        "document_title": "Fixture",
        "file_id": None,
        "start_char_index": 0,
        "end_char_index": 6,
    }
    events = [
        message_start([]),
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "thinking", "thinking": "", "signature": ""},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "Considered request."},
        },
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": "", "citations": None}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Source says."}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "citations_delta", "citation": citation}},
        {"type": "content_block_stop", "index": 1},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": 8},
        },
        {"type": "message_stop"},
    ]

    output = await collect(WatcherCallback(peer.client), "messages", [sse(event) for event in events])

    final = official_response("messages", output)
    assert peer.requests == []
    assert final["content"][0]["thinking"] == "Considered request."
    assert final["content"][1]["citations"] == [citation]
    encoded = list(encode("messages", assemble("messages", output)))
    assert official_response("messages", encoded)["content"] == final["content"]
    assert not any(event.get("delta", {}).get("type") == "signature_delta" for event in decoded(encoded))


async def test_chat_coalesced_tools_emit_usage_logprobs_and_finish_once() -> None:
    peer = WatcherPeer()
    peer.decide("first", "allow")
    peer.decide("second", "allow")
    usage = {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}
    logprobs = {"content": [{"token": "before", "logprob": -0.1, "bytes": [98], "top_logprobs": []}]}
    chunk = litellm.ModelResponseStream(
        id="chatcmpl_coalesced",
        model="fixture",
        created=1,
        usage=usage,
        choices=[
            StreamingChoices(
                index=0,
                delta=Delta(
                    role="assistant",
                    content="before",
                    tool_calls=[chat_tool(0, "{}", "first"), chat_tool(1, "{}", "second")],
                ),
                finish_reason="tool_calls",
                logprobs=logprobs,
            )
        ],
    )

    output = await collect(WatcherCallback(peer.client), "chat_completions", [chunk])

    final = official_response("chat_completions", output)
    choice = final["choices"][0]
    assert choice["message"]["content"] == "before"
    assert [call["id"] for call in choice["message"]["tool_calls"]] == ["first", "second"]
    assert final["usage"]["total_tokens"] == 5
    events = decoded(output)
    assert len([event for event in events if event.get("usage")]) == 1
    assert len([choice for event in events for choice in event["choices"] if choice.get("finish_reason")]) == 1
    assert [choice["logprobs"] for event in events for choice in event["choices"] if choice.get("logprobs")] == [
        logprobs
    ]
    assert len(peer.requests) == 2


async def test_chat_fragmented_legacy_name_fails_closed_before_evaluation() -> None:
    """Legacy Chat function calls lack the backend's supported call-identity contract."""
    peer = WatcherPeer()
    chunks = [
        chat({"role": "assistant", "content": "before"}),
        chat({"function_call": {"name": "read_", "arguments": '{"path":'}}),
        chat({"function_call": {"name": "file", "arguments": '"fixture.txt"}'}}),
        chat({}, "function_call"),
    ]

    output = await rejected(WatcherCallback(peer.client), "chat_completions", chunks)

    assert peer.requests == []
    assert not any(choice["delta"].get("function_call") for event in output for choice in event.get("choices", []))
    assert output[-1]["error"]["code"] == "stream_error"


@pytest.mark.parametrize("id_fragments", [("modern", None), ("call_", "modern")])
async def test_chat_modern_call_preserves_fragmented_names_arguments_and_ids(
    id_fragments: tuple[str, str | None],
) -> None:
    peer = WatcherPeer()
    call_id = "".join(part for part in id_fragments if part is not None)
    peer.decide(call_id, "allow")
    peer.decide("second_call", "allow")
    chunks = [
        chat({"role": "assistant", "content": "before"}),
        chat(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": id_fragments[0],
                        "type": "function",
                        "function": {"name": "read_", "arguments": '{"path":'},
                    }
                ]
            }
        ),
        chat(
            {
                "tool_calls": [
                    {
                        "index": 1,
                        "id": "second_",
                        "type": "function",
                        "function": {"name": "inspect_", "arguments": '{"path":"sec'},
                    },
                    {
                        "index": 0,
                        "id": id_fragments[1],
                        "function": {"name": "file", "arguments": '"fixture.txt"}'},
                    },
                ]
            }
        ),
        chat(
            {
                "tool_calls": [
                    {
                        "index": 1,
                        "id": "call",
                        "function": {"name": "path", "arguments": 'ond.txt"}'},
                    }
                ]
            }
        ),
        chat({}, "tool_calls"),
    ]

    output = await collect(WatcherCallback(peer.client), "chat_completions", chunks)

    final = official_response("chat_completions", output)
    expected = [
        {
            "id": call_id,
            "type": "function",
            "function": {"name": "read_file", "arguments": '{"path":"fixture.txt"}'},
        },
        {
            "id": "second_call",
            "type": "function",
            "function": {"name": "inspect_path", "arguments": '{"path":"second.txt"}'},
        },
    ]
    actual = [
        {
            "id": call["id"],
            "type": call["type"],
            "function": {key: call["function"][key] for key in ("name", "arguments")},
        }
        for call in final["choices"][0]["message"]["tool_calls"]
    ]
    assert actual == expected
    assert len(peer.requests) == 2
    assert [request["response_body"]["choices"][0]["message"]["tool_calls"] for request in peer.requests] == [
        [call] for call in expected
    ]


def test_complete_response_assembly_maps_malformed_terminal_to_protocol_error() -> None:
    with pytest.raises(UnsupportedStream, match="Malformed provider stream"):
        assemble("responses", [{"type": "response.completed"}])
