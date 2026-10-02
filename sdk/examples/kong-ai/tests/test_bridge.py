"""Exercise the public SDK contract used by the gateway-private receiver."""

import copy
import io
import json
from types import SimpleNamespace

import httpx
import pytest
import watcher_kong_ai.bridge as bridge
from typer.testing import CliRunner
from watcher_kong_ai.bridge import UnsupportedExchange, app, decode_json, evaluate, validate_request

from watcher_sdk import AsyncWatcherClient


@pytest.fixture
async def forbidden_watcher():
    """Make malformed-input tests fail if validation reaches any SDK request."""
    async with AsyncWatcherClient(
        "http://watcher.invalid",
        httpx_client=httpx.AsyncClient(
            base_url="http://watcher.invalid",
            transport=httpx.MockTransport(lambda request: pytest.fail("Invalid input reached Watcher")),
        ),
    ) as client:
        yield client


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
        assert body.get("settings_overrides") is None
        assert body["external_ids"] == {"other": "kong:trusted-exchange"}
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
        assert await evaluate(client, *exchange, conversation_id="kong:trusted-exchange") is expected
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
            permitted = await evaluate(client, *exchange, conversation_id="kong:trusted-exchange")
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
        assert body["response_body"]["choices"][0]["message"]["content"] == "finished"
        return httpx.Response(200, json=[])

    async with AsyncWatcherClient(
        "http://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="http://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as client:
        assert await evaluate(client, request, response, conversation_id="kong:trusted-exchange")
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
        {"messages": []},
    ],
)
def test_unsupported_requests_rejected_before_provider(exchange, change):
    request, _ = exchange
    request.update(change)
    with pytest.raises(UnsupportedExchange):
        validate_request(request)


def test_cli_does_not_offer_unsupported_buffered_stream():

    result = CliRunner().invoke(app, ["serve", "--allow-buffered-stream"])
    assert result.exit_code == 2
    assert "No such option" in result.output


@pytest.mark.parametrize("arguments", ['{"x":1,"x":2}', '{"x":NaN}', "[]", "null"])
async def test_ambiguous_arguments_never_reach_watcher(exchange, arguments, forbidden_watcher):
    request, response = exchange
    response["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = arguments
    with pytest.raises((ValueError, UnsupportedExchange)):
        await evaluate(forbidden_watcher, request, response, conversation_id="kong:trusted-exchange")


@pytest.mark.parametrize("identifier", [1, True, None, ""])
async def test_native_id_is_not_coerced(exchange, identifier, forbidden_watcher):
    request, response = exchange
    response["choices"][0]["message"]["tool_calls"][0]["id"] = identifier
    with pytest.raises(UnsupportedExchange):
        await evaluate(forbidden_watcher, request, response, conversation_id="kong:trusted-exchange")


async def test_incomplete_response_never_reaches_watcher(exchange, forbidden_watcher):
    request, response = exchange
    response["choices"][0]["finish_reason"] = "length"
    with pytest.raises(UnsupportedExchange):
        await evaluate(forbidden_watcher, request, response, conversation_id="kong:trusted-exchange")


async def test_duplicate_native_id_rejected(exchange, forbidden_watcher):
    request, response = exchange
    response["choices"][0]["message"]["tool_calls"].append(
        copy.deepcopy(response["choices"][0]["message"]["tool_calls"][0])
    )
    with pytest.raises(UnsupportedExchange):
        await evaluate(forbidden_watcher, request, response, conversation_id="kong:trusted-exchange")


@pytest.mark.parametrize("identifier", ["trusted-exchange", "kong:", "Kong:exchange", "portkey:exchange", None])
async def test_conversation_id_requires_documented_prefix(exchange, identifier, forbidden_watcher):
    request, response = exchange
    with pytest.raises(UnsupportedExchange):
        await evaluate(forbidden_watcher, request, response, conversation_id=identifier)


def test_decode_json_rejects_duplicate_keys():
    with pytest.raises(UnsupportedExchange):
        decode_json('{"verdict":false,"verdict":true}')


@pytest.mark.parametrize(
    "failure,expected",
    [
        (400, 200),
        (401, 200),
        (403, 200),
        (404, 200),
        (422, 200),
        (408, 503),
        (429, 503),
        (503, 503),
        ("connection", 503),
    ],
)
def test_bridge_maps_permanent_raw_rejections_separately_from_outages(monkeypatch, exchange, failure, expected):
    """Exercise the HTTP handler and real public SDK without opening a listener."""
    handlers = []

    def server(address, handler):
        handlers.append(handler)
        return SimpleNamespace(serve_forever=lambda: None)

    def transport(request):
        if request.url.path == "/v1/auth/check-permissions":
            return httpx.Response(200, json={"granted": True, "missing": []})
        if failure == "connection":
            raise httpx.ConnectError("fixture connection failure", request=request)
        return httpx.Response(
            failure, json={"detail": [{"loc": ["body"], "msg": "malformed_exchange", "type": "value_error"}]}
        )

    monkeypatch.setattr(bridge, "ThreadingHTTPServer", server)
    monkeypatch.setattr(
        bridge,
        "AsyncWatcherClient",
        lambda *args, **kwargs: AsyncWatcherClient(
            "http://watcher.invalid",
            httpx_client=httpx.AsyncClient(base_url="http://watcher.invalid", transport=httpx.MockTransport(transport)),
        ),
    )
    monkeypatch.setenv("WATCHER_BRIDGE_TOKEN", "fixture-token")
    monkeypatch.setenv("WATCHER_BASE_URL", "http://watcher.invalid")
    monkeypatch.setenv("WATCHER_API_KEY", "fixture-key")
    bridge.serve("127.0.0.1", 8765)
    payload = json.dumps(
        {
            "request_json": json.dumps(exchange[0]),
            "response_json": json.dumps(exchange[1]),
            "metadata": {"watcher_conversation_id": "kong:fixture-conversation"},
        }
    ).encode()
    raw = (
        b"POST /evaluate HTTP/1.0\r\nAuthorization: Bearer fixture-token\r\nContent-Length: "
        + str(len(payload)).encode()
        + b"\r\n\r\n"
        + payload
    )

    class Socket:
        def __init__(self):
            self.response = bytearray()

        def makefile(self, *args):
            return io.BytesIO(raw)

        def sendall(self, data):
            self.response.extend(data)

    connection = Socket()
    handlers[0](connection, ("127.0.0.1", 1234), SimpleNamespace())
    head, body = bytes(connection.response).split(b"\r\n\r\n", 1)
    assert int(head.split()[1]) == expected
    assert json.loads(body) == {"verdict": False}
