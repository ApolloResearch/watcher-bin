"""Assemble LiteLLM proxy streams into complete responses, and encode responses as streams.

Watcher evaluates complete provider responses, so a streamed reply is buffered
and assembled into the equivalent non-streaming body first. The callback then
streams a fresh encoding of the evaluated body rather than the original
chunks, so a client can only execute the exact calls Watcher saw. Each encoder emits the standard event sequence for its API.

The three client-facing APIs arrive differently from LiteLLM:

- Chat Completions: ``ModelResponseStream`` objects, assembled with LiteLLM's
  own ``stream_chunk_builder``.
- Responses: typed event objects; the terminal ``response.completed`` or
  ``response.incomplete`` (for example at the output-token limit) carries the
  full body.
- Anthropic Messages: raw SSE bytes with arbitrary boundaries.
"""

import json
from collections.abc import Iterator
from typing import Any, Literal

import litellm
from openai._streaming import SSEDecoder
from pydantic import BaseModel

API = Literal["chat_completions", "responses", "messages"]


class IncompleteStream(ValueError):
    """The provider stream stopped early or reported an error; another attempt may succeed."""


class UnsupportedStream(ValueError):
    """The provider stream has a shape this example does not interpret; another attempt would too."""


def as_dict(value: Any) -> dict[str, Any]:
    """A detached JSON-compatible copy of a LiteLLM object or mapping."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=False)
    return json.loads(json.dumps(value))


def assemble(api: API, chunks: list[Any]) -> dict[str, Any]:
    """Build the complete response a non-streaming call would have returned."""
    if not chunks:
        raise IncompleteStream("Empty provider stream")
    if api == "chat_completions":
        return _chat(chunks)
    if api == "responses":
        return _responses(chunks)
    return _messages(chunks)


def _chat(chunks: list[Any]) -> dict[str, Any]:
    finished = any(choice.get("finish_reason") for chunk in chunks for choice in as_dict(chunk).get("choices") or [])
    if not finished:
        raise IncompleteStream("Chat Completions stream has no finish reason")
    built = litellm.stream_chunk_builder(chunks)
    if built is None:
        raise UnsupportedStream("Chat Completions stream could not be assembled")
    response = as_dict(built)
    # LiteLLM's builder keeps content, reasoning, tools, audio and annotations
    # but not streamed refusal text.
    refusal = "".join(
        choice.get("delta", {}).get("refusal") or ""
        for chunk in chunks
        for choice in as_dict(chunk).get("choices") or []
    )
    if refusal and response["choices"] and not response["choices"][0]["message"].get("refusal"):
        response["choices"][0]["message"]["refusal"] = refusal
    return response


def _responses(chunks: list[Any]) -> dict[str, Any]:
    # An incomplete response is still a finished one: a non-streaming call
    # would return it, with its partial output, as a normal reply.
    for chunk in reversed(chunks):
        event = as_dict(chunk)
        if event.get("type") in ("response.completed", "response.incomplete"):
            return event["response"]
    raise IncompleteStream("Responses stream has no terminal response event")


def _messages(chunks: list[Any]) -> dict[str, Any]:
    """Accumulate Anthropic Messages SSE events into one message.

    Unknown delta types, a second ``message_start`` and events after
    ``message_stop`` are refused rather than partly interpreted, and the stream
    must reach ``message_stop``.
    """
    if not all(isinstance(chunk, bytes) for chunk in chunks):
        raise UnsupportedStream("Unexpected Messages stream chunk")
    message: dict[str, Any] | None = None
    partial_json: dict[int, str] = {}
    stopped = False
    for sse in SSEDecoder().iter_bytes(iter(chunks)):
        event = json.loads(sse.data)
        kind = event["type"]
        if kind == "ping":
            continue
        if stopped:
            raise UnsupportedStream("Messages stream continued after message_stop")
        if kind == "message_start":
            if message is not None:
                raise UnsupportedStream("Messages stream started twice")
            message = {**event["message"], "content": []}
            continue
        if kind == "error" or message is None:
            raise IncompleteStream("Messages stream reported an error or has no message_start")
        if kind == "content_block_start":
            message["content"].append(event["content_block"])
        elif kind == "content_block_delta":
            block, delta = message["content"][event["index"]], event["delta"]
            if delta["type"] == "input_json_delta":
                partial_json[event["index"]] = partial_json.get(event["index"], "") + delta["partial_json"]
            elif delta["type"] in ("text_delta", "thinking_delta", "signature_delta"):
                field = delta["type"].removesuffix("_delta")
                block[field] = block.get(field, "") + delta[field]
            elif delta["type"] == "citations_delta":
                # Blocks may start with "citations": null.
                block["citations"] = [*(block.get("citations") or []), delta["citation"]]
            else:
                raise UnsupportedStream("Unsupported Messages delta")
        elif kind == "content_block_stop":
            if event["index"] in partial_json:
                message["content"][event["index"]]["input"] = json.loads(partial_json.pop(event["index"]) or "{}")
        elif kind == "message_delta":
            message.update(event["delta"])
            message["usage"] = {**message.get("usage", {}), **event.get("usage", {})}
        elif kind == "message_stop":
            stopped = True
    if message is None or not stopped:
        raise IncompleteStream("Messages stream ended before message_stop")
    return message


def _sse(data: dict[str, Any], event: str | None = None) -> bytes:
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


def encode(api: API, response: dict[str, Any]) -> Iterator[bytes]:
    """Stream a complete response as SSE events for its API.

    The proxy appends Chat Completions' ``[DONE]`` marker itself.
    """
    if api == "chat_completions":
        yield from _encode_chat(response)
    elif api == "responses":
        yield from _encode_responses(response)
    else:
        yield from _encode_messages(response)


def _encode_chat(response: dict[str, Any]) -> Iterator[bytes]:
    envelope = {key: response.get(key) for key in ("id", "created", "model", "system_fingerprint")}
    envelope["object"] = "chat.completion.chunk"
    choice = response["choices"][0]
    message = choice["message"]
    # Every populated message field travels in the first delta (content,
    # refusal, reasoning, annotations and provider extras); tool calls follow
    # as their own deltas, one per call.
    delta: dict[str, Any] = {
        key: value
        for key, value in message.items()
        if key not in ("role", "tool_calls", "function_call") and value not in (None, [], {}, "")
    }
    delta = {"role": "assistant", "content": message.get("content"), **delta}
    yield _sse({**envelope, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]})
    for index, call in enumerate(message.get("tool_calls") or []):
        tool_delta = {"index": index, "id": call["id"], "type": "function", "function": call["function"]}
        yield _sse(
            {**envelope, "choices": [{"index": 0, "delta": {"tool_calls": [tool_delta]}, "finish_reason": None}]}
        )
    final: dict[str, Any] = {
        **envelope,
        "choices": [{"index": 0, "delta": {}, "finish_reason": choice["finish_reason"]}],
    }
    if response.get("usage"):
        final["usage"] = response["usage"]
    yield _sse(final)


def _encode_responses(response: dict[str, Any]) -> Iterator[bytes]:
    """Emit the standard Responses event sequence.

    Items start empty and are filled by their deltas, as providers stream them:
    SDK clients build per-event snapshots by appending each delta to the added
    item, so an added item that already held its text would appear twice.
    """
    sequence = iter(range(1_000_000))

    def event(kind: str, **fields: Any) -> bytes:
        return _sse({"type": kind, "sequence_number": next(sequence), **fields}, kind)

    yield event("response.created", response={**response, "status": "in_progress", "output": []})
    for index, item in enumerate(response["output"]):
        if item.get("type") != "message":
            yield event("response.output_item.added", output_index=index, item=item)
            yield event("response.output_item.done", output_index=index, item=item)
            continue
        yield event(
            "response.output_item.added", output_index=index, item={**item, "status": "in_progress", "content": []}
        )
        for part_index, part in enumerate(item.get("content") or []):
            location = {"output_index": index, "content_index": part_index, "item_id": item.get("id")}
            if part.get("type") == "output_text":
                yield event("response.content_part.added", **location, part={**part, "text": ""})
                yield event("response.output_text.delta", **location, delta=part["text"], logprobs=[])
                yield event("response.output_text.done", **location, text=part["text"], logprobs=[])
            else:
                yield event("response.content_part.added", **location, part=part)
            yield event("response.content_part.done", **location, part=part)
        yield event("response.output_item.done", output_index=index, item=item)
    terminal = "response.incomplete" if response.get("status") == "incomplete" else "response.completed"
    yield event(terminal, response=response)


def _encode_messages(response: dict[str, Any]) -> Iterator[bytes]:
    def event(data: dict[str, Any]) -> bytes:
        return _sse(data, data["type"])

    usage = response.get("usage") or {}
    yield event({"type": "message_start", "message": {**response, "content": [], "stop_reason": None}})
    for index, block in enumerate(response["content"]):
        if block["type"] == "text":
            yield event({"type": "content_block_start", "index": index, "content_block": {**block, "text": ""}})
            yield event(
                {"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": block["text"]}}
            )
        elif block["type"] == "tool_use":
            yield event({"type": "content_block_start", "index": index, "content_block": {**block, "input": {}}})
            yield event(
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "input_json_delta", "partial_json": json.dumps(block["input"])},
                }
            )
        elif block["type"] == "thinking":
            yield event(
                {
                    "type": "content_block_start",
                    "index": index,
                    "content_block": {**block, "thinking": "", "signature": ""},
                }
            )
            yield event(
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "thinking_delta", "thinking": block["thinking"]},
                }
            )
            if block.get("signature"):
                yield event(
                    {
                        "type": "content_block_delta",
                        "index": index,
                        "delta": {"type": "signature_delta", "signature": block["signature"]},
                    }
                )
        else:
            yield event({"type": "content_block_start", "index": index, "content_block": block})
        yield event({"type": "content_block_stop", "index": index})
    yield event(
        {
            "type": "message_delta",
            # SDK clients overwrite these from the terminal delta, so every
            # populated stop field must be repeated here.
            "delta": {
                "stop_reason": response.get("stop_reason"),
                "stop_sequence": response.get("stop_sequence"),
                **({"stop_details": response["stop_details"]} if response.get("stop_details") else {}),
            },
            "usage": {"output_tokens": usage.get("output_tokens", 0)},
        }
    )
    yield event({"type": "message_stop"})
