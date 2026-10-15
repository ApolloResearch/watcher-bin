"""Split, hold and assemble streamed Chat Completions events."""

import json

import pytest
from watcher_agent_router.exchange import UnsupportedExchange
from watcher_agent_router.streaming import StreamGate, error_event


def event(payload: dict | str) -> bytes:
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return f"data: {data}\n\n".encode()


def chunk(delta: dict, finish_reason: str | None = None, **extra) -> dict:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "m",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        **extra,
    }


TEXT = [event(chunk({"role": "assistant", "content": "Hel"})), event(chunk({"content": "lo"}))]
TOOL = [
    event(
        chunk(
            {
                "tool_calls": [
                    {"index": 0, "id": "call-1", "type": "function", "function": {"name": "rm", "arguments": ""}}
                ]
            }
        )
    ),
    event(chunk({"tool_calls": [{"index": 0, "function": {"arguments": '{"path": '}}]})),
    event(chunk({"tool_calls": [{"index": 0, "function": {"arguments": '"x"}'}}]})),
    event(chunk({}, "tool_calls")),
    event(chunk({}, usage={"total_tokens": 3}) | {"choices": []}),
    event("[DONE]"),
]


def test_text_streams_at_once_and_tool_events_are_held():
    gate = StreamGate(1 << 20)
    assert gate.feed(b"".join(TEXT)) == b"".join(TEXT)
    assert gate.feed(b"".join(TOOL)) == b""
    assert gate.holding
    assert gate.release_held() == b"".join(TOOL)
    completion = gate.completion()
    message = completion["choices"][0]["message"]
    assert message["content"] == "Hello"
    assert message["tool_calls"] == [
        {"id": "call-1", "type": "function", "function": {"name": "rm", "arguments": '{"path": "x"}'}}
    ]
    assert completion["choices"][0]["finish_reason"] == "tool_calls"
    assert completion["usage"] == {"total_tokens": 3} and completion["object"] == "chat.completion"


def test_events_split_across_chunks_are_released_only_when_complete():
    gate = StreamGate(1 << 20)
    data = b"".join(TEXT)
    assert gate.feed(data[:7]) == b""
    assert gate.feed(data[7:]) == data
    assert gate.completion()["choices"][0]["message"]["content"] == "Hello"
    assert not gate.holding


def test_text_only_stream_has_no_tool_calls():
    gate = StreamGate(1 << 20)
    released = gate.feed(b"".join(TEXT) + event(chunk({}, "stop")) + event("[DONE]"))
    message = gate.completion()["choices"][0]["message"]
    assert "tool_calls" not in message and not gate.holding
    # Clients stop at the terminator, so it waits until the exchange has been submitted.
    assert released == b"".join(TEXT) + event(chunk({}, "stop")) and gate.release_held() == event("[DONE]")


def test_legacy_function_call_delta_is_held_and_kept_for_rejection():
    gate = StreamGate(1 << 20)
    assert gate.feed(event(chunk({"function_call": {"name": "rm", "arguments": "{}"}}))) == b""
    assert gate.completion()["choices"][0]["message"]["function_call"] == {"name": "rm", "arguments": "{}"}


def test_comments_and_empty_events_pass_through():
    gate = StreamGate(1 << 20)
    assert gate.feed(b": keepalive\n\n") == b": keepalive\n\n"
    assert gate.chunks == []
    usage_only = event({"usage": {"total_tokens": 1}})
    assert gate.feed(usage_only) == usage_only and not gate.holding


@pytest.mark.parametrize(
    "data",
    [
        event("not json"),
        event("[1, 2]"),
        event({"error": {"message": "provider failed"}}),
        event({"choices": {}}),
    ],
)
def test_malformed_or_error_events_are_refused(data):
    with pytest.raises(UnsupportedExchange):
        StreamGate(1 << 20).feed(data)


@pytest.mark.parametrize(
    "chunks",
    [
        [chunk({"content": "x"}) | {"choices": [{"index": 1, "delta": {}}]}],
        [chunk({"content": "x"}) | {"choices": ["text"]}],
        [chunk({"content": "x"}) | {"choices": [{"index": 0, "delta": "text"}]}],
        [chunk({"tool_calls": [{"function": {"name": "rm"}}]})],
        [chunk({"tool_calls": ["call"]})],
        [chunk({"tool_calls": [{"index": 0, "function": "rm"}]})],
        [chunk({"tool_calls": [{"index": 0, "function": {"name": 1}}]})],
        [
            chunk({"tool_calls": [{"index": 0, "id": "a", "type": "function"}]}),
            chunk({"tool_calls": [{"index": 0, "id": "b"}]}),
        ],
    ],
)
def test_ambiguous_streams_cannot_be_assembled(chunks):
    gate = StreamGate(1 << 20)
    with pytest.raises(UnsupportedExchange):
        gate.feed(b"".join(event(item) for item in chunks))
        gate.completion()


def test_stream_ending_inside_an_event_is_refused():
    gate = StreamGate(1 << 20)
    gate.feed(b'data: {"choices": [')
    with pytest.raises(UnsupportedExchange):
        gate.completion()


def test_oversized_stream_is_refused():
    gate = StreamGate(10)
    with pytest.raises(UnsupportedExchange):
        gate.feed(b"x" * 11)


def test_error_event_is_an_sse_error_without_content():
    data = error_event("Watcher is unavailable", "agent-router:x", 503)
    assert data.startswith(b"data: ") and data.endswith(b"\n\n")
    error = json.loads(data[6:])["error"]
    assert error["conversation_id"] == "agent-router:x" and error["code"] == 503


TOOL_CHUNK = chunk(
    {"tool_calls": [{"index": 0, "id": "call-1", "type": "function", "function": {"name": "rm", "arguments": "{}"}}]}
)


@pytest.mark.parametrize(
    "data",
    [
        b": ping\rdata: " + json.dumps(TOOL_CHUNK).encode() + b"\n\n",
        b"data: " + json.dumps(TOOL_CHUNK).encode() + b"\r\n\r\n",
        b"data: " + json.dumps(TOOL_CHUNK).encode() + b"\r\r",
        b": ping\r\ndata: " + json.dumps(TOOL_CHUNK).encode() + b"\n\r\n",
    ],
)
def test_tool_events_are_held_whatever_their_line_endings(data):
    """Clients accept CR, LF and CRLF, so a tool event hidden behind a CR must still be held."""
    gate = StreamGate(1 << 20)
    # A final CR stays undecided until the next byte shows whether it starts a CRLF.
    released = gate.feed(data) + gate.feed(b": next\n\n")
    assert b"call-1" not in released and gate.holding
    assert b"\r" not in gate.release_held()


def test_crlf_split_across_chunks_is_one_line_ending():
    gate = StreamGate(1 << 20)
    text = b"data: " + json.dumps(chunk({"content": "Hi"})).encode()
    assert gate.feed(text + b"\r") == b""
    assert gate.feed(b"\n\r") == b""
    assert gate.feed(b"\n") == text + b"\n\n"


def test_trailing_cr_is_released_as_a_line_ending():
    gate = StreamGate(1 << 20)
    gate.feed(b": comment\r")
    assert gate.release_held() == b": comment\n"


@pytest.mark.parametrize(
    "after",
    [
        event(chunk({"tool_calls": [{"index": 0, "function": {"name": "_preview"}}]})),
        event(chunk({"content": "more"})),
        event("[DONE]"),
    ],
)
def test_data_after_the_terminator_is_refused(after):
    """Clients stop at [DONE], so later data could change what Watcher grades but not what is delivered."""
    gate = StreamGate(1 << 20)
    with pytest.raises(UnsupportedExchange):
        gate.feed(event(TOOL_CHUNK) + event(chunk({}, "tool_calls")) + event("[DONE]") + after)


def test_data_after_the_terminator_in_a_later_chunk_is_refused():
    gate = StreamGate(1 << 20)
    gate.feed(event(TOOL_CHUNK) + event(chunk({}, "tool_calls")) + event("[DONE]"))
    with pytest.raises(UnsupportedExchange):
        gate.feed(event(chunk({"tool_calls": [{"index": 0, "function": {"name": "_preview"}}]})))


def test_choice_data_after_finish_is_refused_but_usage_is_accepted():
    gate = StreamGate(1 << 20)
    gate.feed(event(TOOL_CHUNK) + event(chunk({}, "tool_calls")) + event({"choices": [], "usage": {"total_tokens": 1}}))
    with pytest.raises(UnsupportedExchange):
        gate.feed(event(chunk({"tool_calls": [{"index": 0, "function": {"arguments": "x"}}]})))


def test_a_second_choice_in_one_event_is_refused():
    """Clients read choices[0]; a duplicate index-0 entry would change only what Watcher grades."""
    duplicate = TOOL_CHUNK | {
        "choices": [
            TOOL_CHUNK["choices"][0] | {"finish_reason": "tool_calls"},
            {"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"name": "_preview"}}]}},
        ]
    }
    with pytest.raises(UnsupportedExchange):
        StreamGate(1 << 20).feed(event(duplicate))


@pytest.mark.parametrize("split", [False, True])
def test_stream_ending_in_a_lone_cr_completes(split):
    gate = StreamGate(1 << 20)
    stream = (
        b"data: " + json.dumps(TOOL_CHUNK).encode() + b"\r\r"
        b"data: " + json.dumps(chunk({}, "tool_calls")).encode() + b"\r\r"
        b"data: [DONE]\r\r"
    )
    if split:
        gate.feed(stream)
        gate.feed(b"", final=True)
    else:
        gate.feed(stream, final=True)
    assert gate.completion()["choices"][0]["message"]["tool_calls"][0]["id"] == "call-1"
    assert gate.release_held().endswith(b"data: [DONE]\n\n")


def test_refusal_and_reasoning_fragments_are_kept_for_watcher():
    """These reach the client in the stream, so Watcher must see them as in a buffered message."""
    gate = StreamGate(1 << 20)
    gate.feed(
        event(chunk({"reasoning_content": "Think", "reasoning": "R1", "reasoning_details": [TEXT_DETAIL]}))
        + event(chunk({"reasoning_content": "ing.", "reasoning": "R2", "reasoning_details": [TEXT_DETAIL_END]}))
        + event(chunk({"refusal": "I cannot "}))
        + event(chunk({"refusal": "help."}))
        + event(chunk({}, "stop"))
    )
    message = gate.completion()["choices"][0]["message"]
    assert message["reasoning_content"] == "Thinking." and message["reasoning"] == "R1R2"
    assert message["refusal"] == "I cannot help."
    assert message["reasoning_details"] == [
        {"type": "reasoning.text", "index": 0, "text": "Thinking.", "format": "unknown", "signature": "sig"}
    ]


TEXT_DETAIL = {"type": "reasoning.text", "index": 0, "text": "Think", "format": "unknown", "signature": None}
TEXT_DETAIL_END = {"type": "reasoning.text", "index": 0, "text": "ing.", "signature": "sig"}


def test_reasoning_detail_fragments_merge_by_index_and_keep_separate_blocks():
    gate = StreamGate(1 << 20)
    summary = {"type": "reasoning.summary", "index": 1, "summary": "Sum"}
    gate.feed(
        event(chunk({"reasoning_details": [TEXT_DETAIL, summary]}))
        + event(chunk({"reasoning_details": [TEXT_DETAIL_END, summary | {"summary": "mary"}]}))
        + event(chunk({"reasoning_details": [{"type": "reasoning.encrypted", "data": "x"}]}))
        + event(chunk({}, "stop"))
    )
    details = gate.completion()["choices"][0]["message"]["reasoning_details"]
    assert [detail.get("text") or detail.get("summary") or detail.get("data") for detail in details] == [
        "Thinking.",
        "Summary",
        "x",
    ]


def test_malformed_reasoning_detail_is_refused():
    gate = StreamGate(1 << 20)
    gate.feed(event(chunk({"reasoning_details": ["text"]})) + event(chunk({}, "stop")))
    with pytest.raises(UnsupportedExchange):
        gate.completion()


def test_denial_events_keep_requested_usage_and_no_calls():
    gate = StreamGate(1 << 20)
    gate.feed(b"".join(TOOL))
    events = [json.loads(line[6:]) for line in gate.denial_events("withheld").split(b"\n\n")[:-2]]
    notice, finish, usage = events
    assert notice["choices"][0]["delta"] == {"role": "assistant", "content": "withheld"}
    assert finish["choices"][0]["finish_reason"] == "stop"
    assert usage == {**usage, "choices": [], "usage": {"total_tokens": 3}}
    assert all("tool_calls" not in event["choices"][0]["delta"] for event in (notice, finish))


def test_denial_events_without_usage_end_after_stop():
    gate = StreamGate(1 << 20)
    gate.feed(b"".join(TEXT))
    data = gate.denial_events("withheld")
    assert data.count(b"data: ") == 3 and data.endswith(b"data: [DONE]\n\n")
    assert json.loads(data.split(b"\n\n")[0][6:])["choices"][0]["delta"]["content"] == "\n\nwithheld"


def test_denial_after_an_empty_role_chunk_does_not_repeat_the_role():
    """OpenAI's accumulator would join a second role into "assistantassistant"."""
    gate = StreamGate(1 << 20)
    gate.feed(event(chunk({"role": "assistant", "content": ""})) + event(TOOL_CHUNK))
    delta = json.loads(gate.denial_events("withheld").split(b"\n\n")[0][6:])["choices"][0]["delta"]
    assert delta == {"content": "withheld"}


def test_denial_events_shorten_echoed_provider_identifiers():
    gate = StreamGate(1 << 22)
    gate.feed(event(chunk({"content": "x"}) | {"id": "i" * 10_000, "model": "m" * 10_000}))
    first = json.loads(gate.denial_events("withheld").split(b"\n\n")[0][6:])
    assert len(first["id"]) == 256 and len(first["model"]) == 256
