"""Verify truthful recovery history and routing through the public replanning helpers."""

import json
import threading
from collections.abc import AsyncIterator
from copy import deepcopy
from typing import Any

import litellm
import pytest
from harness import serve_in_thread
from litellm.proxy import proxy_server
from openai.types.responses import ResponseInputItemParam
from openai.types.responses.response_input_item_param import LocalShellCallOutput
from openai.types.responses.response_tool_search_output_item_param_param import ResponseToolSearchOutputItemParamParam
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from servers import ProviderState, provider_app
from watcher_litellm.replan import (
    ToolCall,
    ToolDenial,
    build_replan_request,
    client_tool_details,
    complete_replan,
    denial_notice,
)
from watcher_litellm.streams import API, as_dict, assemble


class Exchange(BaseModel):
    """A complete provider request and response for one supported client format."""

    request: dict[str, Any]
    response: dict[str, Any]


def exchange(api: API) -> Exchange:
    shared = {"model": "fixture", "stream": True, "metadata": {"session_id": "native-session"}}
    calls: list[dict[str, Any]] = [
        {"id": "released", "name": "read_file", "input": {"path": "approved.txt"}},
        {"id": "denied", "name": "read_file", "input": {"path": "blocked.txt"}},
        {"id": "cancelled", "name": "read_file", "input": {"path": "later.txt"}},
    ]
    if api == "messages":
        return Exchange(
            request={
                **shared,
                "system": [{"type": "text", "text": "Keep all controls.", "cache_control": {"type": "ephemeral"}}],
                "thinking": {"type": "enabled", "budget_tokens": 1000},
                "tools": [{"name": "read_file", "input_schema": {"type": "object"}}],
                "tool_choice": {"type": "tool", "name": "read_file", "disable_parallel_tool_use": True},
                "messages": [{"role": "user", "content": [{"type": "text", "text": "Read the files."}]}],
            },
            response={
                "id": "msg_original",
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "Original reasoning.", "signature": "opaque-signed-thinking"},
                    {"type": "server_tool_use", "id": "server_search", "name": "web_search", "input": {"query": "q"}},
                    *[{"type": "tool_use", **call} for call in calls],
                ],
            },
        )
    if api == "chat_completions":
        return Exchange(
            request={
                **shared,
                "reasoning_effort": "high",
                "tools": [{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}}],
                "tool_choice": {"type": "function", "function": {"name": "read_file"}},
                "messages": [
                    {"role": "developer", "content": "Keep all controls."},
                    {"role": "user", "content": "Read the files."},
                ],
            },
            response={
                "id": "chat_original",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Original text.",
                            "reasoning_content": "Original reasoning.",
                            "provider_specific_fields": {"encrypted_content": "opaque-original-reasoning"},
                            "tool_calls": [
                                {
                                    "id": call["id"],
                                    "type": "function",
                                    "function": {
                                        "name": call["name"],
                                        "arguments": json.dumps(call["input"]),
                                    },
                                }
                                for call in calls
                            ],
                        },
                    }
                ],
            },
        )
    return Exchange(
        request={
            **shared,
            "instructions": "Keep all controls.",
            "reasoning": {"effort": "high"},
            "include": ["reasoning.encrypted_content"],
            "tools": [{"type": "function", "name": "read_file", "parameters": {"type": "object"}}],
            "tool_choice": "required",
            "input": [
                {"type": "reasoning", "id": "previous_reasoning", "summary": [], "encrypted_content": "opaque-prior"},
                {"role": "user", "content": "Read the files."},
            ],
        },
        response={
            "id": "resp_original",
            "output": [
                {"type": "reasoning", "id": "reasoning", "summary": [], "encrypted_content": "opaque-current"},
                {
                    "type": "web_search_call",
                    "id": "server_search",
                    "status": "completed",
                    "action": {"type": "search", "query": "q"},
                },
                *[
                    {
                        "type": "function_call",
                        "id": "item_" + call["id"],
                        "call_id": call["id"],
                        "name": call["name"],
                        "arguments": json.dumps(call["input"]),
                        "status": "completed",
                    }
                    for call in calls
                ],
            ],
        },
    )


def denial() -> ToolDenial:
    return ToolDenial(
        tool_use_id="denied",
        tool_name="read_file",
        tool_input={"path": "blocked.txt"},
        reason="This path needs approval.",
        is_escalation=True,
    )


@pytest.mark.parametrize("api", ["messages", "chat_completions", "responses"])
def test_continuation_preserves_original_history_and_distinguishes_delivery_states(api: API) -> None:
    value = exchange(api)
    before = value.model_dump()

    result = build_replan_request(api, value.request, value.response, [denial()], released_ids={"released"})

    assert value.model_dump() == before
    history_key = "input" if api == "responses" else "messages"
    count = len(value.request[history_key])
    assert result[history_key][:count] == value.request[history_key]
    assert {key: item for key, item in result.items() if key != history_key} == {
        key: item for key, item in value.request.items() if key != history_key
    }
    if api == "messages":
        assert result["messages"][count]["content"] == value.response["content"]
        results = result["messages"][-1]["content"]
        assert [item["tool_use_id"] for item in results] == ["released", "denied", "cancelled"]
        assert "is_error" not in results[0]
        assert results[1]["is_error"] is True and results[2]["is_error"] is True
        texts = [item["content"] for item in results]
    elif api == "responses":
        assert result["input"][count : count + len(value.response["output"])] == value.response["output"]
        results = result["input"][-3:]
        assert [item["call_id"] for item in results] == ["released", "denied", "cancelled"]
        assert [item["type"] for item in results] == ["function_call_output"] * 3
        texts = [item["output"] for item in results]
    else:
        assert result["messages"][count] == value.response["choices"][0]["message"]
        results = result["messages"][-3:]
        assert [item["tool_call_id"] for item in results] == ["released", "denied", "cancelled"]
        assert [item["role"] for item in results] == ["tool"] * 3
        texts = [item["content"] for item in results]
    assert texts[0] == (
        "Watcher approved this tool call and sent it to the client. "
        "Its execution result is not yet available. Do not repeat it."
    )
    assert '"tool_use_id": "denied"' in texts[1]
    assert '"tool_input": {"path": "blocked.txt"}' in texts[1]
    assert '"is_escalation": true' in texts[1]
    assert "This path needs approval." in texts[1]
    assert "Choose an alternative" in texts[1]
    assert "not executed because another call" in texts[2]
    result[history_key][0]["mutated"] = True
    assert value.model_dump() == before


def test_notice_preserves_public_denial_evidence_and_cancelled_sibling_details() -> None:
    text = denial_notice([denial()], cancelled=[ToolCall(tool_use_id="later", tool_name="read", tool_input={"p": "f"})])
    assert json.loads(text.split("\n\n")[1]) == [
        {
            "tool_use_id": "denied",
            "tool_name": "read_file",
            "tool_input": {"path": "blocked.txt"},
            "reason": "This path needs approval.",
            "is_escalation": True,
        }
    ]
    assert '"tool_use_id": "later"' in text
    assert "sibling call was blocked" in text


@pytest.mark.parametrize(
    "invalid",
    ["unknown-denial", "duplicate-denial", "changed-name", "changed-input", "released-denial", "unknown-release"],
)
def test_continuation_refuses_a_receipt_for_the_wrong_call(invalid: str) -> None:
    value = exchange("messages")
    denials = [denial()]
    released = {"released"}
    if invalid == "unknown-denial":
        denials[0].tool_use_id = "missing"
    elif invalid == "duplicate-denial":
        denials.append(denial())
    elif invalid == "changed-name":
        denials[0].tool_name = "different"
    elif invalid == "changed-input":
        denials[0].tool_input = {"path": "different"}
    elif invalid == "released-denial":
        released.add("denied")
    else:
        released.add("missing")
    with pytest.raises(ValueError, match="Invalid replan"):
        build_replan_request("messages", value.request, value.response, denials, released_ids=released)


@pytest.mark.parametrize("api", ["messages", "chat_completions", "responses"])
def test_duplicate_tool_id_cannot_create_ambiguous_continuation_results(api: API) -> None:
    value = exchange(api)
    if api == "messages":
        value.response["content"][-1]["id"] = "denied"
    elif api == "responses":
        value.response["output"][-1]["call_id"] = "denied"
    else:
        value.response["choices"][0]["message"]["tool_calls"][-1]["id"] = "denied"
    with pytest.raises(ValueError, match="Duplicate"):
        client_tool_details(api, value.response)


@pytest.mark.parametrize("raw", ["[]", "null", '{"path":', '{"path":"f"} extra', '{"value":NaN}'])
def test_incomplete_or_nonobject_function_arguments_cannot_be_replanned(raw: str) -> None:
    value = exchange("responses")
    value.response["output"][-1]["arguments"] = raw
    with pytest.raises(ValueError):
        client_tool_details("responses", value.response)


@pytest.mark.parametrize("api", ["chat_completions", "responses"])
def test_custom_tool_input_remains_an_opaque_string(api: API) -> None:
    call = {
        "type": "custom_tool_call",
        "id": "item",
        "call_id": "custom",
        "name": "apply_patch",
        "input": "*** opaque patch ***",
    }
    response = (
        {"output": [call]}
        if api == "responses"
        else {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "type": "custom",
                                "id": "custom",
                                "custom": {"name": "apply_patch", "input": call["input"]},
                            }
                        ],
                    }
                }
            ]
        }
    )
    request = (
        {"input": "Change the file."}
        if api == "responses"
        else {"messages": [{"role": "user", "content": "Change the file."}]}
    )
    refused = ToolDenial(
        tool_use_id="custom",
        tool_name="apply_patch",
        tool_input=call["input"],
        reason="Do not change it.",
        is_escalation=False,
    )

    result = build_replan_request(api, request, response, [refused], released_ids=set())

    assert client_tool_details(api, response) == [
        ToolCall(tool_use_id="custom", tool_name="apply_patch", tool_input="*** opaque patch ***")
    ]
    if api == "responses":
        assert result["input"][0] == {"role": "user", "content": "Change the file."}
        assert result["input"][-1]["type"] == "custom_tool_call_output"
    assert "*** opaque patch ***" in json.dumps(result)


def test_legacy_chat_uses_a_named_function_result() -> None:
    response = {
        "choices": [{"message": {"role": "assistant", "function_call": {"name": "read", "arguments": '{"path":"f"}'}}}]
    }
    denied = ToolDenial(
        tool_use_id="function_call", tool_name="read", tool_input={"path": "f"}, reason="Blocked.", is_escalation=False
    )

    result = build_replan_request("chat_completions", {"messages": []}, response, [denied], released_ids=set())

    assert result["messages"][-1]["role"] == "function"
    assert result["messages"][-1]["name"] == "read"
    assert "tool_call_id" not in result["messages"][-1]


@pytest.mark.parametrize("kind", ["computer_call", "future_client_call"])
def test_unknown_executable_response_items_fail_closed(kind: str) -> None:
    with pytest.raises(ValueError, match="Unsupported Responses"):
        client_tool_details("responses", {"output": [{"type": kind, "id": "unsupported"}]})


@pytest.mark.parametrize(
    ("namespace", "name", "expected"),
    [
        (None, "read", "read"),
        ("functions", "read", "read"),
        ("mcp__shelf__", "__read", "mcp__shelf__read"),
        ("collaboration", "send_message", "collaborationsend_message"),
        ("multi_agent_v1", "spawn_agent", "spawn_agent"),
        ("multi_agent_v1", "wait", "multi_agent_v1wait"),
    ],
)
def test_responses_namespaces_match_watcher_without_changing_raw_history(
    namespace: str | None, name: str, expected: str
) -> None:
    item = {
        "type": "function_call",
        "id": "item",
        "call_id": "call",
        "name": name,
        "namespace": namespace,
        "arguments": '{"path":"fixture"}',
        "status": "completed",
    }
    response = {"output": [item]}
    before = deepcopy(response)
    calls = client_tool_details("responses", response)
    assert calls == [ToolCall(tool_use_id="call", tool_name=expected, tool_input={"path": "fixture"})]
    denied = ToolDenial(**calls[0].model_dump(), reason="Blocked.", is_escalation=False)

    result = build_replan_request("responses", {"input": []}, response, [denied], released_ids=set())

    assert result["input"][0] == item and response == before
    assert expected in result["input"][1]["output"]


def test_same_bare_response_tool_in_two_namespaces_remains_two_operations() -> None:
    response = {
        "output": [
            {"type": "function_call", "call_id": "first", "namespace": "mcp__one", "name": "read", "arguments": "{}"},
            {"type": "function_call", "call_id": "second", "namespace": "mcp__two", "name": "read", "arguments": "{}"},
        ]
    }
    assert [call.tool_name for call in client_tool_details("responses", response)] == [
        "mcp__one__read",
        "mcp__two__read",
    ]


def native_response(kind: str) -> dict[str, Any]:
    """Distinct released, denied and cancelled calls in the same native API family."""
    output = []
    for call_id in ("released", "denied", "cancelled"):
        item: dict[str, Any] = {"type": kind, "id": f"item_{call_id}", "call_id": call_id, "status": "completed"}
        if kind == "local_shell_call":
            item["action"] = {"type": "exec", "command": ["pwd"], "env": {}}
        else:
            item.update(execution="client", arguments={"query": "lookup", "limit": 5})
        output.append(item)
    return {"id": "resp_native", "model": "fixture", "output": output}


@pytest.mark.parametrize("kind", ["local_shell_call", "tool_search_call"])
def test_native_receipts_validate_against_the_exact_sdk_input_schema(kind: str) -> None:
    response = native_response(kind)
    before = deepcopy(response)
    calls = client_tool_details("responses", response)
    denied = ToolDenial(**calls[1].model_dump(), reason="Needs human approval.", is_escalation=True)

    result = build_replan_request(
        "responses", {"input": "Read the directory."}, response, [denied], released_ids={"released"}
    )

    assert response == before
    assert result["input"][1:4] == response["output"]
    TypeAdapter(list[ResponseInputItemParam]).validate_python(result["input"])
    receipts = result["input"][4:7]
    if kind == "local_shell_call":
        adapter = TypeAdapter(LocalShellCallOutput)
        for receipt in receipts:
            assert adapter.validate_python(receipt) == receipt
        assert [receipt["id"] for receipt in receipts] == ["released", "denied", "cancelled"]
        assert [receipt["status"] for receipt in receipts] == ["incomplete", "incomplete", "incomplete"]
        assert "execution result is not yet available" in receipts[0]["output"]
        assert "Needs human approval." in receipts[1]["output"]
        assert "not executed because another call" in receipts[2]["output"]
        assert calls[0].tool_input == {
            "type": "exec",
            "command": ["pwd"],
            "timeout_ms": None,
            "working_directory": None,
            "env": {},
            "user": None,
        }
    else:
        adapter = TypeAdapter(ResponseToolSearchOutputItemParamParam)
        for receipt in receipts:
            assert adapter.dump_python(adapter.validate_python(receipt), mode="json") == receipt
        assert receipts == [
            {
                "type": "tool_search_output",
                "call_id": "released",
                "execution": "client",
                "status": "incomplete",
                "tools": [],
            },
            {
                "type": "tool_search_output",
                "call_id": "denied",
                "execution": "client",
                "status": "incomplete",
                "tools": [],
            },
            {
                "type": "tool_search_output",
                "call_id": "cancelled",
                "execution": "client",
                "status": "incomplete",
                "tools": [],
            },
        ]
        explanation = result["input"][-1]
        assert explanation["role"] == "user"
        assert "not a completed search result" in explanation["content"]
        assert "execution result is not yet available" in explanation["content"]
        assert "Needs human approval." in explanation["content"]
        assert "not executed because another call" in explanation["content"]


@pytest.mark.parametrize("arguments", [{"query": "lookup"}, '{"query":"lookup"}'])
def test_native_tool_search_accepts_decoded_and_json_arguments(arguments: Any) -> None:
    item = native_response("tool_search_call")["output"][0]
    item["arguments"] = arguments
    assert client_tool_details("responses", {"output": [item]}) == [
        ToolCall(tool_use_id="released", tool_name="tool_search", tool_input={"query": "lookup"})
    ]


def test_native_tool_search_with_server_execution_is_rejected_before_retry() -> None:
    item = native_response("tool_search_call")["output"][0]
    item["execution"] = "server"
    with pytest.raises(ValueError, match="Unsupported Responses tool search"):
        client_tool_details("responses", {"output": [item]})


@pytest.mark.parametrize(
    ("api", "response", "reason"),
    [
        (
            "messages",
            {"content": [{"type": "tool_use", "id": "call", "name": "read", "input": []}]},
            "must be an object",
        ),
        ("chat_completions", {"choices": [{"message": {}}, {"message": {}}]}, "one Chat choice"),
        (
            "chat_completions",
            {
                "choices": [
                    {
                        "message": {
                            "function_call": {"name": "read", "arguments": "{}"},
                            "tool_calls": [
                                {"type": "function", "id": "call", "function": {"name": "read", "arguments": "{}"}}
                            ],
                        }
                    }
                ]
            },
            "Mixed legacy",
        ),
        (
            "chat_completions",
            {"choices": [{"message": {"tool_calls": [{"type": "future", "id": "call"}]}}]},
            "Unsupported Chat",
        ),
        ("responses", {"output": [{"type": "function_call", "call_id": "call", "name": "read"}]}, "Malformed client"),
    ],
)
def test_unrepresentable_tool_shapes_never_create_synthetic_results(
    api: API, response: dict[str, Any], reason: str
) -> None:
    with pytest.raises(ValueError, match=reason):
        client_tool_details(api, response)


@pytest.mark.parametrize("api", ["messages", "chat_completions", "responses"])
def test_second_continuation_preserves_earlier_denials_and_released_receipts(api: API) -> None:
    original = exchange(api)
    first = build_replan_request(api, original.request, original.response, [denial()], released_ids={"released"})
    before = deepcopy(first)
    new_call = ToolDenial(
        tool_use_id="next",
        tool_name="read",
        tool_input={"path": "next.txt"},
        reason="Also blocked.",
        is_escalation=False,
    )
    if api == "messages":
        response = {"content": [{"type": "tool_use", "id": "next", "name": "read", "input": {"path": "next.txt"}}]}
    elif api == "chat_completions":
        response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "type": "function",
                                "id": "next",
                                "function": {"name": "read", "arguments": '{"path":"next.txt"}'},
                            }
                        ],
                    }
                }
            ]
        }
    else:
        response = {
            "output": [
                {
                    "type": "function_call",
                    "call_id": "next",
                    "id": "item_next",
                    "name": "read",
                    "arguments": '{"path":"next.txt"}',
                }
            ]
        }

    second = build_replan_request(api, first, response, [new_call], released_ids=set())

    key = "input" if api == "responses" else "messages"
    assert second[key][: len(first[key])] == first[key]
    assert first == before
    assert "Its execution result is not yet available. Do not repeat it." in json.dumps(second)
    assert "Also blocked." in json.dumps(second)


async def test_missing_router_cannot_generate_an_unchecked_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(proxy_server, "llm_router", None)
    with pytest.raises(ValueError, match="configured LiteLLM Router"):
        await complete_replan("responses", {"input": "Work."}, {})


class NonStreamingRouter:
    """An external Router returning the wrong transport shape despite stream=True."""

    async def aresponses(self, **kwargs: Any) -> dict[str, Any]:
        return {"id": "unexpected-buffered-response", "output": []}


async def test_wrong_router_stream_shape_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(proxy_server, "llm_router", NonStreamingRouter())
    with pytest.raises(ValueError, match="streaming alternative"):
        await complete_replan("responses", {"model": "fixture", "input": "Work."}, {}, stream=True)


class RouterBoundary(BaseModel):
    """Capture Router arguments and attempt mutation to verify caller-owned state isolation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    calls: list[dict[str, Any]] = Field(default_factory=list)

    async def invoke(self, api: API, kwargs: dict[str, Any]) -> Any:
        self.calls.append({"api": api, "kwargs": kwargs})
        kwargs["litellm_metadata"]["ownership"]["team"] = "changed-inside-router"
        kwargs["proxy_server_request"]["body"]["model"] = "changed-inside-router"
        if kwargs["stream"]:

            async def events() -> AsyncIterator[dict[str, str]]:
                yield {"type": "fixture"}

            return events()
        return {"id": "replacement", "output": []}

    async def aanthropic_messages(self, **kwargs: Any) -> Any:
        return await self.invoke("messages", kwargs)

    async def acompletion(self, **kwargs: Any) -> Any:
        return await self.invoke("chat_completions", kwargs)

    async def aresponses(self, **kwargs: Any) -> Any:
        return await self.invoke("responses", kwargs)


@pytest.mark.parametrize("api", ["messages", "chat_completions", "responses"])
@pytest.mark.parametrize("stream", [False, True])
async def test_router_keeps_routing_and_isolates_attempt_state(
    monkeypatch: pytest.MonkeyPatch, api: API, stream: bool
) -> None:
    router = RouterBoundary()
    monkeypatch.setattr(proxy_server, "llm_router", router)
    span = threading.Lock()
    data: dict[str, Any] = {
        "model": "deployment-group",
        "api_base": "http://route.test",
        "api_key": "fixture-key",
        "custom_llm_provider": "openai",
        "litellm_logging_obj": object(),
        "litellm_call_id": "old-attempt",
        "deployment": "old-deployment",
        "stream_options": {"include_usage": True},
        "metadata": {"team": "routing-owner", "span": span},
        "litellm_metadata": {"ownership": {"team": "original-owner"}, "span": span},
        "proxy_server_request": {
            "url": "http://proxy/v1/responses",
            "headers": {"trace": "original"},
            "body": {"model": "client-model"},
        },
    }
    request = {
        "model": "client-model",
        "stream": True,
        "stream_options": {"include_usage": True},
        "metadata": {"session_id": "native"},
    }
    before = deepcopy(request)

    result = await complete_replan(api, request, data, stream=stream)

    assert request == before
    assert data["litellm_metadata"]["ownership"] == {"team": "original-owner"}
    assert data["proxy_server_request"]["body"] == {"model": "client-model"}
    observed = router.calls[0]
    assert observed["api"] == api
    kwargs = observed["kwargs"]
    assert kwargs["model"] == "deployment-group"
    assert kwargs["api_base"] == "http://route.test" and kwargs["api_key"] == "fixture-key"
    assert kwargs["custom_llm_provider"] == "openai"
    assert kwargs["litellm_metadata"]["span"] is span
    assert "litellm_logging_obj" not in kwargs and "litellm_call_id" not in kwargs and "deployment" not in kwargs
    assert ("stream_options" in kwargs) is stream
    assert kwargs["metadata"] == (
        {"team": "routing-owner", "span": span} if api == "chat_completions" else {"session_id": "native"}
    )
    if stream:
        assert isinstance(result, AsyncIterator)
        assert [event async for event in result] == [{"type": "fixture"}]
    else:
        assert result == {"id": "replacement", "output": []}


@pytest.fixture(scope="module")
async def replan_provider() -> AsyncIterator[str]:
    try:
        yield serve_in_thread(provider_app(ProviderState(tools=["read_file"])))
    finally:
        await litellm.close_litellm_async_clients()


@pytest.mark.parametrize(
    ("api", "expected_id"), [("messages", "toolu_0"), ("chat_completions", "call_0"), ("responses", "call_0")]
)
@pytest.mark.parametrize("is_streaming", [False, True])
async def test_real_router_streams_have_the_shapes_expected_by_the_callback(
    monkeypatch: pytest.MonkeyPatch, replan_provider: str, api: API, expected_id: str, is_streaming: bool
) -> None:
    router = litellm.Router(
        model_list=[
            {
                "model_name": "fixture",
                "litellm_params": {
                    "model": "anthropic/claude-test" if api == "messages" else "openai/gpt-test",
                    "api_base": replan_provider if api == "messages" else replan_provider + "/v1",
                    "api_key": "fixture",
                },
            }
        ],
        num_retries=0,
    )
    monkeypatch.setattr(proxy_server, "llm_router", router)
    request: dict[str, Any] = {"model": "fixture"}
    if api == "responses":
        request["input"] = "Read the file."
    else:
        request["messages"] = [{"role": "user", "content": "Read the file."}]
    if api == "messages":
        request["max_tokens"] = 100
    generated = await complete_replan(api, request, {}, stream=is_streaming)
    if is_streaming:
        assert isinstance(generated, AsyncIterator)
        chunks = [chunk async for chunk in generated]
        assert chunks
        if api == "messages":
            assert all(isinstance(chunk, bytes) for chunk in chunks)
        elif api == "chat_completions":
            assert all(isinstance(chunk, litellm.ModelResponseStream) for chunk in chunks)
        else:
            assert as_dict(chunks[0])["type"] == "response.created"
        completed = assemble(api, chunks)
    else:
        assert isinstance(generated, dict)
        completed = generated
    assert client_tool_details(api, completed) == [
        ToolCall(tool_use_id=expected_id, tool_name="read_file", tool_input={"path": "f0"})
    ]
