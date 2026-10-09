"""Deterministic provider and Watcher HTTP peers for the real LiteLLM streaming tests.

Provider gates let a test require client-visible text before producing a tool.
Each new tool then waits for a separate Watcher decision controlled by the
test. These peers never contact a model provider or a deployed Watcher.
"""

import asyncio
import json
import threading
import time
from collections.abc import AsyncIterator
from queue import Queue
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

API = Literal["messages", "chat_completions", "responses"]


class Grade(BaseModel):
    """One pending hook request, including its externally controlled decision."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ids: list[str]
    body: dict[str, Any]
    started: float = Field(default_factory=time.monotonic)
    release: threading.Event = Field(default_factory=threading.Event)
    disconnected: threading.Event = Field(default_factory=threading.Event)
    decision: Literal["allow", "deny"] = "allow"
    status_code: int = 200


class Scenario(BaseModel):
    """Controls shared between the test thread and the two HTTP server threads."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    case_id: str = Field(default_factory=lambda: str(uuid4()))
    start_tools: threading.Event = Field(default_factory=threading.Event)
    finish_provider: threading.Event = Field(default_factory=threading.Event)
    provider_finished: threading.Event = Field(default_factory=threading.Event)
    grades: Queue[Grade] = Field(default_factory=Queue)
    requests: list[dict[str, Any]] = Field(default_factory=list)
    decisions: dict[str, str] = Field(default_factory=dict)
    provider_error: bool = False
    auto_allow: bool = False
    auto_allow_delay: float = 0
    combined_chat_chunks: bool = False
    text_only: bool = False
    hold_recording: bool = False
    response_suffix: str = ""
    initial_stream_delay_seconds: float = 0


class ScenarioHolder(BaseModel):
    """Select a fresh scenario without restarting the HTTP peers or LiteLLM."""

    current: Scenario = Field(default_factory=Scenario)
    cases: dict[str, Scenario] = Field(default_factory=dict)


def sse(data: dict[str, Any], event: str | None = None) -> str:
    """Serialize a wire event; Messages and Responses also name the event type."""
    return (f"event: {event}\n" if event else "") + f"data: {json.dumps(data)}\n\n"


async def wait_gate(gate: threading.Event) -> None:
    """Wait for explicit test coordination, failing rather than hanging the suite."""
    async with asyncio.timeout(20):
        while not gate.is_set():
            await asyncio.sleep(0.01)


async def messages_events(state: Scenario, model: str) -> AsyncIterator[str]:
    """Stream text and two fragmented calls with a provider pause before each call."""
    message = {
        "id": f"msg_incremental{state.response_suffix}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 5, "output_tokens": 0},
    }
    yield sse({"type": "message_start", "message": message}, "message_start")
    for index, text in [(0, "before"), (2, "between"), (4, "after")]:
        yield sse(
            {"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}},
            "content_block_start",
        )
        yield sse(
            {"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": text}},
            "content_block_delta",
        )
        yield sse({"type": "content_block_stop", "index": index}, "content_block_stop")
        if index == 4 or state.text_only:
            break
        await wait_gate(state.start_tools if index == 0 else state.finish_provider)
        if state.provider_error:
            yield sse({"type": "error", "error": {"type": "overloaded_error", "message": "fixture error"}}, "error")
            return
        tool = index // 2
        yield sse(
            {
                "type": "content_block_start",
                "index": index + 1,
                "content_block": {"type": "tool_use", "id": f"call_{tool}", "name": "read_file", "input": {}},
            },
            "content_block_start",
        )
        for fragment in ('{"path":', f'"f{tool}"}}'):
            yield sse(
                {
                    "type": "content_block_delta",
                    "index": index + 1,
                    "delta": {"type": "input_json_delta", "partial_json": fragment},
                },
                "content_block_delta",
            )
        yield sse({"type": "content_block_stop", "index": index + 1}, "content_block_stop")
    yield sse(
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn" if state.text_only else "tool_use", "stop_sequence": None},
            "usage": {"output_tokens": 30},
        },
        "message_delta",
    )
    yield sse({"type": "message_stop"}, "message_stop")
    state.provider_finished.set()


async def chat_events(state: Scenario, model: str) -> AsyncIterator[str]:
    """Interleave two calls; only finish_reason proves their arguments are complete."""
    base = {
        "id": f"chatcmpl_incremental{state.response_suffix}",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": model,
    }

    def chunk(delta: dict[str, Any], finish: str | None = None) -> str:
        return sse({**base, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]})

    if state.combined_chat_chunks:
        yield chunk(
            {
                "role": "assistant",
                "content": "before",
                "tool_calls": [
                    {
                        "index": index,
                        "id": f"call_{index}",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path":'},
                    }
                    for index in (0, 1)
                ],
            }
        )
        await wait_gate(state.finish_provider)
        yield sse(
            {
                **base,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {"index": index, "function": {"arguments": f'"f{index}"}}'}} for index in (1, 0)
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 30, "total_tokens": 35},
            }
        )
        yield "data: [DONE]\n\n"
        state.provider_finished.set()
        return
    yield chunk({"role": "assistant", "content": "before"})
    if state.text_only:
        yield chunk({}, "stop")
        yield "data: [DONE]\n\n"
        state.provider_finished.set()
        return
    await wait_gate(state.start_tools)
    if state.provider_error:
        yield sse({"error": {"message": "fixture error", "type": "server_error", "code": "server_error"}})
        return
    for index in (0, 1):
        yield chunk(
            {
                "tool_calls": [
                    {
                        "index": index,
                        "id": f"call_{index}",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path":'},
                    }
                ]
            }
        )
        if index == 0:
            yield chunk({"content": "between"})
    for index in (1, 0):
        yield chunk({"tool_calls": [{"index": index, "function": {"arguments": f'"f{index}"}}'}}]})
    yield chunk({"content": "after"})
    await wait_gate(state.finish_provider)
    yield chunk({}, "tool_calls")
    yield "data: [DONE]\n\n"
    state.provider_finished.set()


async def responses_events(state: Scenario, model: str) -> AsyncIterator[str]:
    """Emit complete Responses event sequences with two separately completed calls."""
    sequence = 0
    output: list[dict[str, Any]] = []
    base = {
        "id": f"resp_incremental{state.response_suffix}",
        "object": "response",
        "created_at": 1,
        "model": model,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
    }

    def event(kind: str, **fields: Any) -> str:
        nonlocal sequence
        value = sse({"type": kind, "sequence_number": sequence, **fields}, kind)
        sequence += 1
        return value

    yield event("response.created", response={**base, "status": "in_progress", "output": []})
    yield event("response.in_progress", response={**base, "status": "in_progress", "output": []})
    for index, text in [(0, "before"), (2, "between"), (4, "after")]:
        item = {
            "id": f"msg_{index}{state.response_suffix}",
            "type": "message",
            "role": "assistant",
            "status": "in_progress",
            "content": [],
        }
        part = {"type": "output_text", "text": "", "annotations": []}
        yield event("response.output_item.added", output_index=index, item=item)
        yield event("response.content_part.added", item_id=item["id"], output_index=index, content_index=0, part=part)
        yield event(
            "response.output_text.delta",
            item_id=item["id"],
            output_index=index,
            content_index=0,
            delta=text,
            logprobs=[],
        )
        yield event(
            "response.output_text.done", item_id=item["id"], output_index=index, content_index=0, text=text, logprobs=[]
        )
        completed_part = {**part, "text": text}
        yield event(
            "response.content_part.done", item_id=item["id"], output_index=index, content_index=0, part=completed_part
        )
        completed = {**item, "status": "completed", "content": [completed_part]}
        output.append(completed)
        yield event("response.output_item.done", output_index=index, item=completed)
        if index == 4 or state.text_only:
            break
        await wait_gate(state.start_tools if index == 0 else state.finish_provider)
        if state.provider_error:
            yield event("error", message="fixture error", code="server_error", param=None)
            return
        tool = index // 2
        call = {
            "id": f"fc_{tool}",
            "type": "function_call",
            "call_id": f"call_{tool}",
            "name": "read_file",
            "arguments": "",
            "status": "in_progress",
        }
        yield event("response.output_item.added", output_index=index + 1, item=call)
        for fragment in ('{"path":', f'"f{tool}"}}'):
            yield event(
                "response.function_call_arguments.delta", item_id=call["id"], output_index=index + 1, delta=fragment
            )
        arguments = json.dumps({"path": f"f{tool}"}, separators=(",", ":"))
        yield event(
            "response.function_call_arguments.done",
            item_id=call["id"],
            output_index=index + 1,
            arguments=arguments,
            name="read_file",
        )
        complete_call = {**call, "status": "completed", "arguments": arguments}
        output.append(complete_call)
        yield event("response.output_item.done", output_index=index + 1, item=complete_call)
    yield event(
        "response.completed",
        response={
            **base,
            "status": "completed",
            "output": output,
            "usage": {"input_tokens": 5, "output_tokens": 30, "total_tokens": 35},
        },
    )
    state.provider_finished.set()


def provider_app(holder: ScenarioHolder) -> FastAPI:
    """Serve all native provider protocols from one disposable localhost endpoint."""
    app = FastAPI()

    @app.post("/v1/{api:path}")
    async def generate(api: str, request: Request) -> StreamingResponse:
        body = await request.json()
        state = holder.current
        if has_tool_feedback(api, body):
            state = state.model_copy(update={"text_only": True, "response_suffix": "_alternative"})
        streams = {"messages": messages_events, "chat/completions": chat_events, "responses": responses_events}

        async def events() -> AsyncIterator[str]:
            if state.initial_stream_delay_seconds:
                await asyncio.sleep(state.initial_stream_delay_seconds)
            async for event in streams[api](state, body["model"]):
                yield event

        return StreamingResponse(events(), media_type="text/event-stream")

    return app


def has_tool_feedback(api: str, body: dict[str, Any]) -> bool:
    """The transport fixture answers a native recovery continuation with text only."""
    if api == "chat/completions":
        return any(message["role"] in {"tool", "function"} for message in body["messages"])
    if api == "messages":
        return any(
            block["type"] == "tool_result"
            for message in body["messages"]
            if isinstance(message["content"], list)
            for block in message["content"]
        )
    return isinstance(body["input"], list) and any(
        item.get("type") in {"function_call_output", "custom_tool_call_output"} for item in body["input"]
    )


def call_ids(body: dict[str, Any]) -> list[str]:
    """Read the client call inventory independently of the callback implementation."""
    response = body["response_body"]
    if body["url"].endswith("/messages"):
        return [block["id"] for block in response["content"] if block["type"] == "tool_use"]
    if body["url"].endswith("/responses"):
        return [item["call_id"] for item in response["output"] if item["type"] == "function_call"]
    return [call["id"] for call in response["choices"][0]["message"].get("tool_calls", [])]


def watcher_app(holder: ScenarioHolder) -> FastAPI:
    """Delay each new decision until the test releases it and expose disconnects."""
    app = FastAPI()

    @app.post("/v1/hooks/pre-tool-use")
    async def grade(request: Request) -> JSONResponse:
        body = await request.json()
        state = holder.cases[body["external_ids"]["other"].removeprefix("litellm:")]
        state.requests.append(body)
        ids = call_ids(body)
        pending = [call_id for call_id in ids if call_id not in state.decisions]
        if pending or state.hold_recording:
            grade = Grade(ids=pending, body=body)
            state.grades.put(grade)
            if state.auto_allow:
                await asyncio.sleep(state.auto_allow_delay)
                grade.release.set()
            async with asyncio.timeout(330):
                while not grade.release.is_set():
                    if await request.is_disconnected():
                        grade.disconnected.set()
                        return JSONResponse({"detail": "client disconnected"}, status_code=499)
                    await asyncio.sleep(0.01)
            if grade.status_code != 200:
                return JSONResponse({"detail": "fixture Watcher unavailable"}, status_code=grade.status_code)
            state.decisions.update({call_id: grade.decision for call_id in pending})
        return JSONResponse(
            [
                {
                    "decision": state.decisions[call_id],
                    "judged_decision": state.decisions[call_id],
                    "decision_source": "rule",
                    "enforcement_mode": "enforce",
                    "tool_use_id": call_id,
                    "verdict": {
                        "explanation": "Fixture denied this call." if state.decisions[call_id] == "deny" else None
                    },
                    "latency_ms": 1.0,
                }
                for call_id in ids
            ]
        )

    return app
