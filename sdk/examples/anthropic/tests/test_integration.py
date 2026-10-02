"""Native Anthropic wire fidelity and tool-delivery checks using local transports."""

import json
from copy import deepcopy

import httpx
import httpx2
import pytest
from anthropic import AsyncAnthropic
from watcher_anthropic import complete

from watcher_sdk import AsyncWatcherClient, WatcherValidationError

PROVIDER_HTTP = httpx2
PROVIDER_CLASS = AsyncAnthropic
PROVIDER_NAME = "anthropic"
APIS = ["messages"]
DEFAULT_API = "messages"


async def invoke(provider, watcher, request, *, api, enforcement):
    return await complete(provider, watcher, request, "app-session", enforcement=enforcement)


def request_body(api):
    return {"model": "fixture-model", "max_tokens": 128, "messages": [{"role": "user", "content": "Inspect safely"}]}


def response_body(api, *, text_only=False):
    blocks = (
        [{"type": "text", "text": "Done"}]
        if text_only
        else [
            {"type": "thinking", "thinking": "Check", "signature": "opaque"},
            {"type": "tool_use", "id": "call-1", "name": "inspect", "input": {"count": 0, "enabled": False}},
            {"type": "tool_use", "id": "call-2", "name": "inspect", "input": {}},
        ]
    )
    return {
        "id": "message-1",
        "type": "message",
        "role": "assistant",
        "model": "fixture-model",
        "content": blocks,
        "stop_reason": "end_turn" if text_only else "tool_use",
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


async def exercise(
    api=DEFAULT_API,
    *,
    mode="enforce",
    decision="allow",
    failure=None,
    mutation=None,
    text_only=False,
    request=None,
    response=None,
    status=200,
    enforcement="server",
):
    request = deepcopy(request or request_body(api))
    original = deepcopy(request)
    response = deepcopy(response or response_body(api, text_only=text_only))
    response["provider_extension"] = {"unknown": "retained", "null": None}
    provider_seen, watcher_seen = [], []

    def provider_transport(req):
        provider_seen.append(req)
        return PROVIDER_HTTP.Response(200, json=response)

    def watcher_transport(req):
        body = json.loads(req.content)
        watcher_seen.append(body)
        assert body["format"] == "raw"
        assert "require_recording" not in req.url.params
        assert body["request_body"] == json.loads(provider_seen[0].content)
        assert body["response_body"] == response
        assert body["user_agent"] == provider_seen[0].headers["user-agent"]
        assert body["url"] == str(provider_seen[0].url)
        assert body["provider"] == PROVIDER_NAME
        if status != 200:
            return httpx.Response(
                status, json={"detail": [{"loc": ["body"], "msg": "fixture error", "type": "value_error"}]}
            )
        outcomes = []
        if api == "responses":
            delivered = [
                (["output", i], call["call_id"])
                for i, call in enumerate(response["output"])
                if call["type"] == "function_call"
            ]
        elif api == "messages":
            delivered = [
                (["content", i], call["id"]) for i, call in enumerate(response["content"]) if call["type"] == "tool_use"
            ]
        else:
            delivered = [
                (["choices", 0, "message", "tool_calls", i], call["id"])
                for i, call in enumerate(response["choices"][0]["message"].get("tool_calls", []))
            ]
        for _path, identifier in delivered:
            outcomes.append(
                {
                    "tool_use_id": identifier,
                    "decision": "deferred" if mode in {"observe", "paused"} else decision,
                    "judged_decision": None if mode == "paused" else decision,
                    "decision_source": "bypass" if mode == "paused" else ("grading_error" if failure else "rule"),
                    "enforcement_mode": mode,
                    "grading_error": failure,
                    "verdict": {},
                    "latency_ms": 0,
                }
            )
        if mutation == "missing":
            outcomes = []
        elif mutation == "wrong-id":
            outcomes[0]["tool_use_id"] = "different"
        elif mutation == "missing-id":
            outcomes[0].pop("tool_use_id")
        elif mutation == "reverse":
            outcomes.reverse()
        elif mutation == "duplicate":
            outcomes[-1] = outcomes[0]
        elif mutation == "item-error":
            outcomes[0] = {"tool_use_id": "call-1", "status_code": 503, "detail": "fixture"}
        elif mutation == "bad-provenance":
            outcomes[0]["judged_decision"] = "deny"
        return httpx.Response(200, json=outcomes)

    async with (
        PROVIDER_CLASS(
            api_key="fixture",
            max_retries=0,
            http_client=PROVIDER_HTTP.AsyncClient(transport=PROVIDER_HTTP.MockTransport(provider_transport)),
        ) as provider,
        AsyncWatcherClient(
            "https://watcher.test",
            httpx_client=httpx.AsyncClient(
                base_url="https://watcher.test", transport=httpx.MockTransport(watcher_transport)
            ),
        ) as watcher,
    ):
        result = await invoke(provider, watcher, request, api=api, enforcement=enforcement)
    assert request == original
    return watcher_seen, result


@pytest.mark.asyncio
@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize(
    "mode,decision", [("enforce", "allow"), ("observe", "deny"), ("observe", "escalate"), ("paused", "allow")]
)
async def test_native_raw_exchange_fidelity_and_inherited_policy(api, mode, decision):
    seen, response = await exercise(api, mode=mode, decision=decision)
    assert seen[0]["external_ids"] == {"other": "app-session"}
    assert response is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("decision", ["deny", "escalate"])
async def test_enforcement_withholds_before_tool_executor(api, decision):
    executed = []
    with pytest.raises(PermissionError):
        executed.append(await exercise(api, decision=decision))
    assert executed == []


@pytest.mark.asyncio
@pytest.mark.parametrize("api", APIS)
async def test_text_only_pair_ingests_without_fabricated_call(api):
    seen, _ = await exercise(api, text_only=True)
    assert "input" not in seen[0] and "messages" not in seen[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("mutation", ["missing", "wrong-id", "missing-id", "duplicate", "item-error", "bad-provenance"])
async def test_uncovered_or_invalid_outcomes_cannot_release_tools(api, mutation):
    with pytest.raises((RuntimeError, PermissionError)):
        await exercise(api, mutation=mutation)


@pytest.mark.asyncio
@pytest.mark.parametrize("api", APIS)
async def test_server_selected_grading_failure_allow_is_applied(api):
    await exercise(api, failure={"code": "grader_failed", "message": "fixture"})


@pytest.mark.asyncio
@pytest.mark.parametrize("api", APIS)
async def test_transport_rejection_surfaces_without_response_delivery(api):
    with pytest.raises(WatcherValidationError):
        await exercise(api, status=422)


@pytest.mark.asyncio
@pytest.mark.parametrize("api", APIS)
async def test_explicit_override_cannot_silently_be_ignored(api):
    with pytest.raises(RuntimeError, match="requested enforcement"):
        await exercise(api, mode="observe", enforcement="enforce")


@pytest.mark.asyncio
@pytest.mark.parametrize("api", APIS)
async def test_streaming_refused_before_generation(api):
    with pytest.raises(ValueError, match="buffered"):
        await exercise(api, request={**request_body(api), "stream": True})


@pytest.mark.asyncio
@pytest.mark.parametrize("api", APIS)
async def test_native_text_only_truncation_is_delivered_and_submitted(api):
    response = response_body(api, text_only=True)
    if api == "responses":
        response["status"] = "incomplete"
        response["incomplete_details"] = {"reason": "max_output_tokens"}
        response["output"][0]["status"] = "incomplete"
    elif api == "messages":
        response["stop_reason"] = "max_tokens"
    else:
        response["choices"][0]["finish_reason"] = "length"
    seen, native = await exercise(api, response=response, text_only=True)
    assert seen[0]["response_body"] == {**response, "provider_extension": {"unknown": "retained", "null": None}}
    assert native is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("api", APIS)
async def test_incomplete_native_tool_proposals_remain_withheld(api):
    response = response_body(api)
    if api == "responses":
        response["status"] = "incomplete"
    elif api == "messages":
        response["stop_reason"] = "max_tokens"
    else:
        response["choices"][0]["finish_reason"] = "length"
    with pytest.raises(ValueError, match="Incomplete"):
        await exercise(api, response=response)


@pytest.mark.asyncio
@pytest.mark.parametrize("api", APIS)
async def test_id_only_decisions_may_arrive_in_another_order(api):
    await exercise(api, mutation="reverse")


@pytest.mark.asyncio
@pytest.mark.parametrize("api", APIS)
async def test_reused_response_identity_cannot_authorize_a_second_call(api):
    response = response_body(api)
    if api == "responses":
        calls = [item for item in response["output"] if item["type"] == "function_call"]
        calls[1]["call_id"] = calls[0]["call_id"]
    elif api == "messages":
        calls = [item for item in response["content"] if item["type"] == "tool_use"]
        calls[1]["id"] = calls[0]["id"]
    else:
        calls = response["choices"][0]["message"]["tool_calls"]
        calls[1]["id"] = calls[0]["id"]
    with pytest.raises(ValueError, match="duplicate native tool identity"):
        await exercise(api, response=response)
