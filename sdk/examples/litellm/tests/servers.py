"""Local stand-ins for a model provider and for Watcher, used by the proxy tests.

``provider_app`` answers OpenAI Chat Completions, OpenAI Responses and
Anthropic Messages requests with a scripted reply: text, or one tool call per
name in ``state.tools``. Streaming requests receive the standard event
sequence for their API.

``watcher_app`` implements the pre-tool-use hook's raw-format response contract
with a trivial policy: tools named in ``state.deny`` are denied, others are
allowed. It records every request so tests can inspect what the callback sent.
It does not convert transcripts; the real server's conversion is covered by the
product test suite and by the live tests.
"""

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse


@dataclass
class ProviderState:
    """What the next provider reply contains, and every request it received."""

    tools: list[str] = field(default_factory=list)
    text: str = "Hello from the provider."
    requests: list[dict[str, Any]] = field(default_factory=list)
    # Faults for the next Messages streams, one per request: "truncate" ends the
    # stream before message_stop, "error" sends an overloaded error event.
    stream_faults: list[str] = field(default_factory=list)
    # When set, Responses replies end incomplete for this reason, such as
    # "max_output_tokens", instead of completing.
    responses_incomplete: str | None = None


@dataclass
class WatcherState:
    """The fake Watcher policy and everything the callback sent it."""

    deny: set[str] = field(default_factory=set)
    mode: str = "enforce"
    fail_status: int | None = None
    call_error: bool = False
    requests: list[dict[str, Any]] = field(default_factory=list)


def _sse(data: dict[str, Any], event: str | None = None) -> str:
    return (f"event: {event}\n" if event else "") + f"data: {json.dumps(data)}\n\n"


def _chat(state: ProviderState, body: dict[str, Any]) -> dict[str, Any]:
    calls = [
        {"id": f"call_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps({"path": f"f{i}"})}}
        for i, name in enumerate(state.tools)
    ]
    message: dict[str, Any] = {"role": "assistant", "content": None if calls else state.text}
    if calls:
        message["tool_calls"] = calls
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body["model"],
        "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if calls else "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
    }


def _chat_stream(response: dict[str, Any]) -> Iterator[str]:
    base = {key: response[key] for key in ("id", "created", "model")} | {"object": "chat.completion.chunk"}
    message = response["choices"][0]["message"]
    yield _sse(
        {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]}
    )
    if message.get("content"):
        for word in message["content"].split(" "):
            yield _sse({**base, "choices": [{"index": 0, "delta": {"content": word + " "}, "finish_reason": None}]})
    for index, call in enumerate(message.get("tool_calls") or []):
        head = {
            "index": index,
            "id": call["id"],
            "type": "function",
            "function": {"name": call["function"]["name"], "arguments": ""},
        }
        yield _sse({**base, "choices": [{"index": 0, "delta": {"tool_calls": [head]}, "finish_reason": None}]})
        args = {"index": index, "function": {"arguments": call["function"]["arguments"]}}
        yield _sse({**base, "choices": [{"index": 0, "delta": {"tool_calls": [args]}, "finish_reason": None}]})
    finish = response["choices"][0]["finish_reason"]
    yield _sse({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}], "usage": response["usage"]})
    yield "data: [DONE]\n\n"


def _responses(state: ProviderState, body: dict[str, Any]) -> dict[str, Any]:
    output: list[dict[str, Any]] = [
        {
            "type": "function_call",
            "id": f"fc_{i}",
            "call_id": f"call_{i}",
            "name": name,
            "arguments": json.dumps({"path": f"f{i}"}),
            "status": "completed",
        }
        for i, name in enumerate(state.tools)
    ]
    if not output:
        output = [
            {
                "type": "message",
                "id": "msg_1",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": state.text, "annotations": []}],
            }
        ]
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": int(time.time()),
        "status": "incomplete" if state.responses_incomplete else "completed",
        "incomplete_details": {"reason": state.responses_incomplete} if state.responses_incomplete else None,
        "model": body["model"],
        "output": output,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": body.get("tools", []),
        "usage": {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
    }


def _responses_stream(response: dict[str, Any]) -> Iterator[str]:
    sequence = iter(range(10_000))

    def event(kind: str, **fields: Any) -> str:
        return _sse({"type": kind, "sequence_number": next(sequence), **fields}, kind)

    yield event("response.created", response={**response, "status": "in_progress", "output": []})
    for index, item in enumerate(response["output"]):
        yield event("response.output_item.added", output_index=index, item=item)
        yield event("response.output_item.done", output_index=index, item=item)
    terminal = "response.incomplete" if response["status"] == "incomplete" else "response.completed"
    yield event(terminal, response=response)


def _messages(state: ProviderState, body: dict[str, Any]) -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        {"type": "tool_use", "id": f"toolu_{i}", "name": name, "input": {"path": f"f{i}"}}
        for i, name in enumerate(state.tools)
    ] or [{"type": "text", "text": state.text}]
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": body["model"],
        "content": content,
        "stop_reason": "tool_use" if state.tools else "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 5, "output_tokens": 7},
    }


def _messages_stream(response: dict[str, Any]) -> Iterator[str]:
    def event(data: dict[str, Any]) -> str:
        return _sse(data, data["type"])

    yield event({"type": "message_start", "message": {**response, "content": [], "stop_reason": None}})
    for index, block in enumerate(response["content"]):
        if block["type"] == "text":
            yield event({"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}})
            yield event(
                {"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": block["text"]}}
            )
        else:
            yield event({"type": "content_block_start", "index": index, "content_block": {**block, "input": {}}})
            partial = json.dumps(block["input"])
            for piece in (partial[:5], partial[5:]):
                yield event(
                    {
                        "type": "content_block_delta",
                        "index": index,
                        "delta": {"type": "input_json_delta", "partial_json": piece},
                    }
                )
        yield event({"type": "content_block_stop", "index": index})
    yield event(
        {"type": "message_delta", "delta": {"stop_reason": response["stop_reason"]}, "usage": {"output_tokens": 7}}
    )
    yield event({"type": "message_stop"})


def provider_app(state: ProviderState) -> FastAPI:
    app = FastAPI()

    async def reply(request: Request, build: Any, stream: Any) -> Any:
        body = await request.json()
        state.requests.append({"path": request.url.path, "body": body})
        response = build(state, body)
        if body.get("stream"):
            events = list(stream(response))
            if stream is _messages_stream and state.stream_faults:
                fault = state.stream_faults.pop(0)
                error = {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}
                events = events[:-1] if fault == "truncate" else [events[0], _sse(error, "error")]
            return StreamingResponse(iter(events), media_type="text/event-stream")
        return JSONResponse(response)

    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> Any:
        return await reply(request, _chat, _chat_stream)

    @app.post("/v1/responses")
    async def responses(request: Request) -> Any:
        return await reply(request, _responses, _responses_stream)

    @app.post("/v1/messages")
    async def messages(request: Request) -> Any:
        return await reply(request, _messages, _messages_stream)

    return app


def _tool_calls(url: str, response: dict[str, Any]) -> list[tuple[str, str, list[str | int]]]:
    """(name, native id, path) for each client tool call in a response, by the endpoint's format."""
    if url.endswith("/chat/completions"):
        calls = response["choices"][0]["message"].get("tool_calls") or []
        return [
            (c["function"]["name"], c["id"], ["choices", 0, "message", "tool_calls", i]) for i, c in enumerate(calls)
        ]
    if url.endswith("/messages"):
        return [
            (b["name"], b["id"], ["content", i]) for i, b in enumerate(response["content"]) if b["type"] == "tool_use"
        ]
    return [
        (item["name"], item["call_id"], ["output", i])
        for i, item in enumerate(response["output"])
        if item["type"] == "function_call"
    ]


def watcher_app(state: WatcherState) -> FastAPI:
    app = FastAPI()

    @app.post("/v1/hooks/pre-tool-use")
    async def pre_tool_use(request: Request) -> Any:
        body = await request.json()
        state.requests.append(body)
        if state.fail_status is not None:
            return JSONResponse({"detail": "unavailable"}, status_code=state.fail_status)
        assert body["format"] == "raw"
        outputs = []
        for name, call_id, _ in _tool_calls(body["url"], body["response_body"]):
            if state.call_error:
                outputs.append({"status_code": 503, "detail": "grading unavailable", "tool_use_id": call_id})
                continue
            judged = "deny" if name in state.deny else "allow"
            outputs.append(
                {
                    "decision": "deferred" if state.mode == "observe" else judged,
                    "judged_decision": judged,
                    "decision_source": "rule",
                    "enforcement_mode": state.mode,
                    "tool_use_id": call_id,
                    "verdict": {"explanation": f"{name} is not allowed here." if judged == "deny" else None},
                    "latency_ms": 1.0,
                }
            )
        return outputs

    return app
