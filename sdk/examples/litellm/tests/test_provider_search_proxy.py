"""Check provider search context and item fields across the real LiteLLM proxy."""

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from harness import litellm_proxy, serve_in_thread
from pydantic import BaseModel, Field
from servers import WatcherState, watcher_app
from watcher_litellm.streams import encode


class ProviderScript(BaseModel):
    """Complete provider replies and the requests that consumed them."""

    replies: list[dict[str, Any]] = Field(default_factory=list)
    requests: list[dict[str, Any]] = Field(default_factory=list)


def provider_app(script: ProviderScript) -> FastAPI:
    app = FastAPI()

    @app.post("/v1/responses", response_model=None)
    async def generate(request: Request) -> JSONResponse | StreamingResponse:
        body = await request.json()
        reply = script.replies[min(len(script.requests), len(script.replies) - 1)]
        script.requests.append(body)
        if not body.get("stream"):
            return JSONResponse(reply)

        async def events() -> AsyncIterator[bytes]:
            for frame in encode("responses", reply):
                event = json.loads(frame.decode().split("data: ", 1)[1])
                item = event.get("item", {})
                if event["type"] == "response.output_item.added" and item.get("type") == "function_call":
                    arguments = item["arguments"]
                    event["item"] = {**item, "arguments": "", "status": "in_progress"}
                    yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()
                    location = {"output_index": event["output_index"], "item_id": item["id"]}
                    for kind, fields in [("delta", {"delta": arguments}), ("done", {"arguments": arguments})]:
                        argument_event = {"type": f"response.function_call_arguments.{kind}", **location, **fields}
                        yield f"event: {argument_event['type']}\ndata: {json.dumps(argument_event)}\n\n".encode()
                elif event["type"] == "response.output_item.added" and item.get("type") == "reasoning":
                    event["item"] = {**item, "summary": []}
                    yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()
                    for index, part in enumerate(item["summary"]):
                        for boundary in ["added", "done"]:
                            summary_event = {
                                "type": f"response.reasoning_summary_part.{boundary}",
                                "output_index": event["output_index"],
                                "item_id": item["id"],
                                "summary_index": index,
                                "part": {**part, "text": ""} if boundary == "added" else part,
                            }
                            yield f"event: {summary_event['type']}\ndata: {json.dumps(summary_event)}\n\n".encode()
                else:
                    yield frame
                await asyncio.sleep(0)

        return StreamingResponse(events(), media_type="text/event-stream")

    return app


def response(search: bool, *, alternative: bool = False) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    if search:
        items.extend(
            [
                {
                    "type": "tool_search_call",
                    "id": "tsc_search_1",
                    "execution": "server",
                    "call_id": None,
                    "arguments": {"paths": ["desk"], "query": "current user"},
                    "status": "completed",
                },
                {
                    "type": "tool_search_output",
                    "id": "search_output_1",
                    "execution": "server",
                    "call_id": None,
                    "tools": [
                        {
                            "type": "namespace",
                            "name": "desk",
                            "tools": [{"type": "function", "name": "desk-crm_whoami", "defer_loading": True}],
                        }
                    ],
                    "status": "completed",
                },
            ]
        )
    if not alternative:
        call = {
            "type": "function_call",
            "id": "fc_1",
            "call_id": "call_1",
            "name": "desk-crm_whoami",
            "arguments": '{"include_teams":true}',
            "status": "completed",
        }
        if search:
            call["namespace"] = "desk"
        items.append(call)
    if not search or alternative:
        items.append(
            {
                "type": "message",
                "id": "msg_alt" if alternative else "msg_1",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "A permitted alternative.", "annotations": []}],
            }
        )
    return {
        "id": "resp_alt" if alternative else "resp_raw",
        "object": "response",
        "created_at": 1,
        "model": "gpt-test",
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "status": "completed",
        "output": items,
        "usage": {
            "input_tokens": 3,
            "output_tokens": 4,
            "total_tokens": 7,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


@pytest.fixture(scope="module")
def script() -> ProviderScript:
    return ProviderScript()


@pytest.fixture(scope="module")
def policy() -> WatcherState:
    return WatcherState()


@pytest.fixture(scope="module")
def proxy(script: ProviderScript, policy: WatcherState, tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    provider = serve_in_thread(provider_app(script))
    watcher = serve_in_thread(watcher_app(policy))
    models = [
        {
            "model_name": name,
            "litellm_params": {"model": f"openai/{name}", "api_base": f"{provider}/v1", "api_key": "k"},
            "model_info": {"supports_native_streaming": native},
        }
        for name, native in [("gpt-test", True), ("gpt-simulated", False)]
    ]
    with litellm_proxy(
        models, {"WATCHER_API_URL": watcher, "WATCHER_API_KEY": "fixture"}, tmp_path_factory.mktemp("provider-search")
    ) as url:
        yield url


def send(proxy: str, model: str, stream: bool) -> dict[str, Any]:
    result = httpx.post(
        f"{proxy}/v1/responses",
        json={"model": model, "input": "Who am I?", "stream": stream},
        headers={"x-watcher-session-id": "provider-search-test"},
        timeout=30,
    )
    result.raise_for_status()
    if not stream:
        return {"events": [], "response": result.json()}
    events = [
        json.loads(line[6:])
        for line in result.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    assert all(event.get("type") != "error" for event in events), events
    return {"events": events, "response": events[-1]["response"]}


@pytest.mark.parametrize("model", ["gpt-test", "gpt-simulated"])
@pytest.mark.parametrize("stream", [True, False])
@pytest.mark.parametrize("denied", [False, True])
def test_provider_search_crosses_proxy(
    proxy: str, script: ProviderScript, policy: WatcherState, model: str, stream: bool, denied: bool
) -> None:
    original = response(True)
    script.replies = [original, response(False, alternative=True)]
    script.requests.clear()
    policy.requests.clear()
    policy.deny = {"desk-crm_whoami"} if denied else set()
    result = send(proxy, model, stream)
    assert bool(script.requests[0].get("stream")) == (stream and model == "gpt-test")
    final = result["response"]
    assert final["output"][:2] == original["output"][:2]
    by_id = {item["id"]: item for item in original["output"]}
    for event in result["events"]:
        if "item" in event and event["item"]["id"] in by_id:
            assert set(event["item"]) == set(by_id[event["item"]["id"]])
    if denied:
        text = " ".join(
            part["text"] for item in final["output"] if item["type"] == "message" for part in item["content"]
        )
        assert "WATCHER NOTICE (added by Watcher, not written by the assistant): Watcher blocked" in text
        assert "A permitted alternative." in text
        history = script.requests[1]["input"]
        assert [item for item in history if item.get("type", "").startswith("tool_search")] == original["output"][:2]
        assert not any("Gateway delivery receipt" in str(item.get("content")) for item in history)
    else:
        assert final["output"] == original["output"]
    calls = [
        item
        for request in policy.requests
        for item in request["response_body"].get("output", [])
        if item["type"] == "function_call"
    ]
    assert [item["call_id"] for item in calls] == ["call_1"]
    assert calls[0]["arguments"] == original["output"][2]["arguments"]


def test_simulated_plain_items_keep_provider_keys(proxy: str, script: ProviderScript, policy: WatcherState) -> None:
    original = response(False)
    script.replies = [original]
    script.requests.clear()
    policy.requests.clear()
    policy.deny.clear()
    result = send(proxy, "gpt-simulated", True)
    assert not script.requests[0].get("stream")
    assert result["response"]["output"] == original["output"]
    by_id = {item["id"]: item for item in original["output"]}
    for event in result["events"]:
        if "item" in event:
            assert set(event["item"]) == set(by_id[event["item"]["id"]])


@pytest.mark.parametrize("stream", [True, False])
def test_explicit_provider_null_fields_survive(
    proxy: str, script: ProviderScript, policy: WatcherState, stream: bool
) -> None:
    original = response(True)
    original["output"][0]["created_by"] = None
    original["output"][1]["created_by"] = None
    original["output"][2]["caller"] = None
    script.replies = [original]
    script.requests.clear()
    policy.requests.clear()
    policy.deny.clear()
    result = send(proxy, "gpt-simulated", stream)
    assert result["response"]["output"] == original["output"]


@pytest.mark.parametrize("model", ["gpt-test", "gpt-simulated"])
def test_reasoning_summary_parts_preserve_provider_fields(
    proxy: str, script: ProviderScript, policy: WatcherState, model: str
) -> None:
    original = response(True)
    original["output"].insert(
        0,
        {
            "type": "reasoning",
            "id": "rs_1",
            "encrypted_content": None,
            "summary": [{"type": "summary_text", "text": "Check the current user."}],
        },
    )
    script.replies = [original]
    script.requests.clear()
    policy.requests.clear()
    policy.deny.clear()
    result = send(proxy, model, True)
    assert result["response"]["output"] == original["output"]
    parts = [event["part"] for event in result["events"] if "summary_index" in event and "part" in event]
    assert parts
    expected = original["output"][0]["summary"][0]
    assert all(set(part) == set(expected) for part in parts)
    assert parts[-1] == expected
