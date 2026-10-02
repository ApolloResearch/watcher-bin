"""Exercise the public SDK contract used by the gateway-private receiver."""

import copy
import json
from unittest.mock import create_autospec

import httpx
import pytest
from watcher_bifrost.bridge import UnsupportedExchange, decode_json, evaluate, validate_request

from watcher_sdk import AsyncWatcherClient


@pytest.fixture
def exchange():
    return (
        {
            "model": "fixture",
            "messages": [{"role": "user", "content": "fixture marker"}],
            "tools": [{"type": "function", "function": {"name": "write_file"}}],
        },
        {
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "type": "function",
                                "id": "native-call-1",
                                "function": {
                                    "name": "write_file",
                                    "arguments": '{"number":1,"float":1.0,"boolean":true,"null":null}',
                                },
                            }
                        ],
                    },
                }
            ]
        },
    )


@pytest.mark.parametrize(
    "mode,decision,judgment,expected",
    [
        ("enforce", "allow", "allow", True),
        ("enforce", "deny", "deny", False),
        ("enforce", "escalate", "escalate", False),
        ("observe", "deferred", "deny", True),
        ("paused", "deferred", None, True),
        ("enforce", "allow", None, False),
    ],
)
async def test_applied_policy_controls_delivery(exchange, mode, decision, judgment, expected):
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body["format"] == "raw"
        assert body["request_body"] == exchange[0]
        assert body["response_body"] == exchange[1]
        assert body["url"] == "/v1/chat/completions"
        assert body["provider"] == "openai"
        assert body["user_agent"] == "ordinary-client/1"
        assert body.get("settings_overrides") is None
        assert body["external_ids"] == {"other": "bifrost:trusted-exchange"}
        arguments = json.loads(body["response_body"]["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])
        assert type(arguments["number"]) is int
        assert type(arguments["float"]) is float
        assert type(arguments["boolean"]) is bool
        assert arguments["null"] is None
        return httpx.Response(
            200,
            json=[
                {
                    "decision": decision,
                    "judged_decision": judgment,
                    "decision_source": "bypass" if mode == "paused" else "rule",
                    "enforcement_mode": mode,
                    "tool_use_id": "native-call-1",
                    "verdict": {},
                    "latency_ms": 1,
                }
            ],
        )

    async with AsyncWatcherClient(
        "http://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="http://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as client:
        assert (
            await evaluate(
                client, *exchange, conversation_id="bifrost:trusted-exchange", user_agent="ordinary-client/1"
            )
            is expected
        )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "result",
    [
        [],
        [
            {
                "decision": "allow",
                "decision_source": "rule",
                "enforcement_mode": "enforce",
                "tool_use_id": "other",
                "verdict": {},
                "latency_ms": 1,
            }
        ],
        [{"status_code": 503, "detail": "unavailable", "tool_use_id": "native-call-1"}],
    ],
)
async def test_missing_mismatched_or_error_outcome_withholds(exchange, result):
    async with AsyncWatcherClient(
        "http://watcher.invalid",
        httpx_client=httpx.AsyncClient(
            base_url="http://watcher.invalid", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=result))
        ),
    ) as client:
        try:
            permitted = await evaluate(client, *exchange, conversation_id="bifrost:trusted-exchange")
        except (ValueError, TypeError, AttributeError, KeyError):
            permitted = False
        assert not permitted


async def test_text_tail_records_through_same_hook(exchange):
    request, response = exchange
    request["messages"] += [
        response["choices"][0]["message"],
        {"role": "tool", "tool_call_id": "native-call-1", "content": "completed"},
    ]
    response = {
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "finished"}}]
    }
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        assert body.get("input") is None
        assert body["format"] == "raw"
        assert body["response_body"]["choices"][0]["message"]["content"] == "finished"
        return httpx.Response(200, json=[])

    async with AsyncWatcherClient(
        "http://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="http://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as client:
        assert await evaluate(client, request, response, conversation_id="bifrost:trusted-exchange")
    assert len(seen) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"stream": True},
        {"stream": "false"},
        {"n": 2},
        {"n": True},
        {"functions": []},
        {"previous_response_id": "hidden"},
        {"tools": [{"type": "custom"}]},
    ],
)
def test_unsupported_requests_rejected_before_provider(exchange, change):
    request, _ = exchange
    request.update(change)
    with pytest.raises(UnsupportedExchange):
        validate_request(request)


def test_stream_requires_explicit_native_buffering(exchange):
    request, _ = exchange
    request["stream"] = True
    assert validate_request(request, allow_stream=True) is None


@pytest.mark.parametrize("arguments", ['{"x":1,"x":2}', '{"x":NaN}', "[]", "null"])
async def test_ambiguous_arguments_never_reach_watcher(exchange, arguments):
    request, response = exchange
    response["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = arguments
    with pytest.raises((ValueError, UnsupportedExchange)):
        await evaluate(
            create_autospec(AsyncWatcherClient, instance=True),
            request,
            response,
            conversation_id="bifrost:trusted-exchange",
        )


@pytest.mark.parametrize("identifier", [1, True, None, ""])
async def test_native_id_is_not_coerced(exchange, identifier):
    request, response = exchange
    response["choices"][0]["message"]["tool_calls"][0]["id"] = identifier
    with pytest.raises(UnsupportedExchange):
        await evaluate(
            create_autospec(AsyncWatcherClient, instance=True),
            request,
            response,
            conversation_id="bifrost:trusted-exchange",
        )


async def test_incomplete_response_never_reaches_watcher(exchange):
    request, response = exchange
    response["choices"][0]["finish_reason"] = "length"
    with pytest.raises(UnsupportedExchange):
        await evaluate(
            create_autospec(AsyncWatcherClient, instance=True),
            request,
            response,
            conversation_id="bifrost:trusted-exchange",
        )


async def test_duplicate_native_id_rejected(exchange):
    request, response = exchange
    response["choices"][0]["message"]["tool_calls"].append(
        copy.deepcopy(response["choices"][0]["message"]["tool_calls"][0])
    )
    with pytest.raises(UnsupportedExchange):
        await evaluate(
            create_autospec(AsyncWatcherClient, instance=True),
            request,
            response,
            conversation_id="bifrost:trusted-exchange",
        )


@pytest.mark.parametrize("identifier", ["trusted-exchange", "bifrost:", "Bifrost:exchange", "portkey:exchange", None])
async def test_conversation_id_requires_documented_prefix(exchange, identifier):
    request, response = exchange
    watcher = create_autospec(AsyncWatcherClient, instance=True)
    with pytest.raises(UnsupportedExchange):
        await evaluate(watcher, request, response, conversation_id=identifier)
    watcher.pre_tool_use_hook.assert_not_called()


def test_decode_json_rejects_duplicate_keys():
    with pytest.raises(UnsupportedExchange):
        decode_json('{"verdict":false,"verdict":true}')


@pytest.mark.parametrize("fault", ["missing_id", "empty_id", "duplicate", "wrong_id", "missing_judgment", "error"])
async def test_unique_native_id_must_cover_each_delivered_call(exchange, fault):
    result = {
        "decision": "allow",
        "judged_decision": "allow",
        "decision_source": "rule",
        "enforcement_mode": "enforce",
        "tool_use_id": "native-call-1",
        "verdict": {},
        "latency_ms": 1,
    }
    if fault == "missing_id":
        result.pop("tool_use_id")
    elif fault == "empty_id":
        result["tool_use_id"] = ""
    elif fault == "wrong_id":
        result["tool_use_id"] = "different"
    elif fault == "missing_judgment":
        result.pop("judged_decision")
    elif fault == "error":
        result = {"tool_use_id": "native-call-1", "status_code": 503, "detail": "fixture"}
    outcomes = [result, result] if fault == "duplicate" else [result]
    async with AsyncWatcherClient(
        "http://watcher.invalid",
        httpx_client=httpx.AsyncClient(
            base_url="http://watcher.invalid",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=outcomes)),
        ),
    ) as client:
        assert not await evaluate(client, *exchange, conversation_id="bifrost:trusted-exchange")


async def test_raw_pair_has_no_structured_32_call_limit(exchange):
    request, response = exchange
    original = response["choices"][0]["message"]["tool_calls"][0]
    response["choices"][0]["message"]["tool_calls"] = [dict(copy.deepcopy(original), id=f"call-{i}") for i in range(33)]

    def handler(request):
        body = json.loads(request.content)
        assert body["format"] == "raw" and "input" not in body and "messages" not in body
        return httpx.Response(
            200,
            json=[
                {
                    "decision": "allow",
                    "judged_decision": "allow",
                    "decision_source": "rule",
                    "enforcement_mode": "enforce",
                    "tool_use_id": f"call-{i}",
                    "verdict": {},
                    "latency_ms": 1,
                }
                for i in range(33)
            ],
        )

    async with AsyncWatcherClient(
        "http://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="http://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as client:
        assert await evaluate(client, request, response, conversation_id="bifrost:trusted-exchange")


async def test_backend_receives_original_multimodal_body_without_local_conversion(exchange):
    request, response = exchange
    request["messages"][0]["content"] = [
        {"type": "text", "text": "Inspect the picture"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,fixture"}},
    ]

    def handler(payload):
        body = json.loads(payload.content)
        assert body["request_body"] == request and body["response_body"] == response
        return httpx.Response(
            200,
            json=[
                {
                    "decision": "allow",
                    "judged_decision": "allow",
                    "decision_source": "rule",
                    "enforcement_mode": "enforce",
                    "tool_use_id": "native-call-1",
                    "verdict": {},
                    "latency_ms": 1,
                }
            ],
        )

    async with AsyncWatcherClient(
        "http://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="http://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as client:
        assert await evaluate(client, request, response, conversation_id="bifrost:trusted-exchange")


async def test_applied_grading_failure_allow_remains_releasable(exchange):
    result = {
        "decision": "allow",
        "judged_decision": "allow",
        "decision_source": "grading_error",
        "enforcement_mode": "enforce",
        "tool_use_id": "native-call-1",
        "verdict": {},
        "latency_ms": 1,
        "grading_error": {"code": "timeout", "message": "Fixture timeout"},
    }
    async with AsyncWatcherClient(
        "http://watcher.invalid",
        httpx_client=httpx.AsyncClient(
            base_url="http://watcher.invalid",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[result])),
        ),
    ) as client:
        assert await evaluate(client, *exchange, conversation_id="bifrost:trusted-exchange")


@pytest.mark.parametrize("reason", ["length", "content_filter"])
async def test_truncated_text_is_submitted_without_inventing_or_authorizing_a_tool(exchange, reason):
    request, _ = exchange
    response = {
        "choices": [{"index": 0, "finish_reason": reason, "message": {"role": "assistant", "content": "Partial text"}}]
    }
    seen = []

    def transport(http_request):
        body = json.loads(http_request.content)
        seen.append(body)
        assert body["response_body"] == response
        return httpx.Response(200, json=[])

    async with AsyncWatcherClient(
        "http://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="http://watcher.invalid", transport=httpx.MockTransport(transport)),
    ) as client:
        assert await evaluate(client, request, response, conversation_id="bifrost:partial-text")
    assert len(seen) == 1
