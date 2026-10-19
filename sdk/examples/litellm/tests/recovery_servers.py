"""Scripted HTTP peers that verify denial recovery uses genuine provider continuations.

The next reply is selected from structured tool-result feedback in the incoming
request. Merely issuing another request with the original prompt cannot advance
the fixture. Each attempt has different tool IDs so an operation repeated under
a new ID can be distinguished from a permitted alternative.
"""

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from queue import Queue
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from incremental_servers import API, Grade, call_ids, wait_gate
from pydantic import BaseModel, ConfigDict, Field
from servers import _chat_stream, _messages_stream, _responses_stream

_DENIED_FEEDBACK = "Watcher did not approve these client tool calls"

Decision = Literal["allow", "deny", "escalate"]


def _deny_first_call() -> dict[str, Decision]:
    """The default policy: deny the first attempt's call so the scenario must recover."""
    return {"call_0_0": "deny"}


class RecoveryState(BaseModel):
    """Provider attempts, policy decisions and explicit gates for one recovery scenario."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    case_id: str = Field(default_factory=lambda: str(uuid4()))
    paths: list[list[str]] = Field(default_factory=lambda: [["blocked-a"], ["allowed-b"]])
    decisions: dict[str, Decision] = Field(default_factory=_deny_first_call)
    provider_requests: list[dict[str, Any]] = Field(default_factory=list)
    hook_requests: list[dict[str, Any]] = Field(default_factory=list)
    graded_ids: list[str] = Field(default_factory=list)
    grades: Queue[Grade] = Field(default_factory=Queue)
    gate_tools: bool = False
    gate_grades: bool = False
    provider_gates: list[threading.Event] = Field(default_factory=lambda: [threading.Event() for _ in range(3)])
    watcher_status: int = 200
    reject_replacements: bool = False


class RecoveryHolder(BaseModel):
    """Give each test fresh state while retaining the actual LiteLLM process."""

    current: RecoveryState = Field(default_factory=RecoveryState)
    cases: dict[str, RecoveryState] = Field(default_factory=dict)


def tool_feedback(api: API, body: dict[str, Any]) -> dict[str, str]:
    """Extract native tool-result messages rather than counting arbitrary notice text."""
    if api == "chat_completions":
        return {
            message["tool_call_id"]: message["content"] for message in body["messages"] if message["role"] == "tool"
        }
    if api == "messages":
        return {
            block["tool_use_id"]: block["content"]
            for message in body["messages"]
            if isinstance(message["content"], list)
            for block in message["content"]
            if block["type"] == "tool_result"
        }
    return {
        item["call_id"]: item["output"]
        for item in body["input"]
        if isinstance(item, dict) and item.get("type") == "function_call_output"
    }


def response_body(api: API, model: str, attempt: int, paths: list[str]) -> dict[str, Any]:
    """Build one provider response containing ordinary prefix text and native tool calls."""
    prefix = f"prefix-{attempt}"
    if api == "messages":
        return {
            "id": f"msg_attempt_{attempt}",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [
                {"type": "text", "text": prefix},
                *[
                    {"type": "tool_use", "id": f"call_{attempt}_{index}", "name": "read_file", "input": {"path": path}}
                    for index, path in enumerate(paths)
                ],
            ],
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "usage": {"input_tokens": 5, "output_tokens": 20},
        }
    if api == "chat_completions":
        return {
            "id": f"chatcmpl_attempt_{attempt}",
            "object": "chat.completion",
            "created": 1,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": prefix,
                        "tool_calls": [
                            {
                                "type": "function",
                                "id": f"call_{attempt}_{index}",
                                "function": {"name": "read_file", "arguments": json.dumps({"path": path})},
                            }
                            for index, path in enumerate(paths)
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 20, "total_tokens": 25},
        }
    return {
        "id": f"resp_attempt_{attempt}",
        "object": "response",
        "created_at": 1,
        "status": "completed",
        "model": model,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "output": [
            {
                "type": "message",
                "id": f"msg_attempt_{attempt}",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": prefix, "annotations": []}],
            },
            *[
                {
                    "type": "function_call",
                    "id": f"fc_{attempt}_{index}",
                    "call_id": f"call_{attempt}_{index}",
                    "name": "read_file",
                    "arguments": json.dumps({"path": path}),
                    "status": "completed",
                }
                for index, path in enumerate(paths)
            ],
        ],
        "usage": {"input_tokens": 5, "output_tokens": 20, "total_tokens": 25},
    }


def provider_app(holder: RecoveryHolder) -> FastAPI:
    """Serve native provider APIs, optionally stopping after each attempt's prefix."""
    app = FastAPI()

    @app.post("/v1/{path:path}", response_model=None)
    async def generate(path: str, request: Request) -> JSONResponse | StreamingResponse:
        api: API = (
            "chat_completions" if path == "chat/completions" else "messages" if path == "messages" else "responses"
        )
        body = await request.json()
        state = holder.current
        feedback = tool_feedback(api, body)
        attempt = sum(_DENIED_FEEDBACK in text for text in feedback.values())
        state.provider_requests.append(body)
        if attempt and state.reject_replacements:
            return JSONResponse({"error": {"message": "private provider diagnostic", "type": "invalid_request"}}, 400)
        assert attempt == len(state.provider_requests) - 1, "replacement omitted or duplicated native denial feedback"
        assert attempt < len(state.paths), "unexpected extra provider attempt"
        response = response_body(api, body["model"], attempt, state.paths[attempt])
        if not body.get("stream"):
            return JSONResponse(response)
        encode = {"messages": _messages_stream, "chat_completions": _chat_stream, "responses": _responses_stream}[api]

        async def events() -> AsyncIterator[str]:
            gated = False
            for event in encode(response):
                if state.gate_tools and not gated and f"call_{attempt}_0" in event:
                    gated = True
                    await wait_gate(state.provider_gates[attempt])
                yield event

        return StreamingResponse(events(), media_type="text/event-stream")

    return app


def watcher_app(holder: RecoveryHolder) -> FastAPI:
    """Return policy outcomes by ID; unknown IDs are allowed to expose unsafe retry caching."""
    app = FastAPI()

    @app.post("/v1/hooks/pre-tool-use")
    async def grade(request: Request) -> JSONResponse:
        body = await request.json()
        state = holder.cases[body["external_ids"]["other"].removeprefix("litellm:")]
        state.hook_requests.append(body)
        ids = call_ids(body)
        state.graded_ids.extend(ids)
        if ids and state.gate_grades:
            pending = Grade(ids=ids, body=body)
            state.grades.put(pending)
            async with asyncio.timeout(20):
                while not pending.release.is_set():
                    if await request.is_disconnected():
                        pending.disconnected.set()
                        return JSONResponse({"detail": "client disconnected"}, status_code=499)
                    await asyncio.sleep(0.01)
        if state.watcher_status != 200:
            return JSONResponse({"detail": "fixture Watcher failure"}, status_code=state.watcher_status)
        return JSONResponse(
            [
                {
                    "decision": state.decisions.get(call_id, "allow"),
                    "judged_decision": state.decisions.get(call_id, "allow"),
                    "decision_source": "rule",
                    "enforcement_mode": "enforce",
                    "tool_use_id": call_id,
                    "verdict": {"explanation": f"Fixture blocks {call_id}."},
                    "latency_ms": 1.0,
                }
                for call_id in ids
            ]
        )

    return app
