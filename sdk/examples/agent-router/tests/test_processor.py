"""Drive the external processor with Envoy's protobuf messages and a fake Watcher API."""

import asyncio
import json
import socket

import grpc
import httpx
import pytest
import structlog
import watcher_agent_router.processor as processor
from envoy.config.core.v3.base_pb2 import HeaderMap, HeaderValue
from envoy.extensions.filters.http.ext_proc.v3.processing_mode_pb2 import ProcessingMode
from envoy.service.ext_proc.v3 import external_processor_pb2 as ext_proc
from envoy.service.ext_proc.v3 import external_processor_pb2_grpc as ext_proc_grpc
from typer.testing import CliRunner
from watcher_agent_router.alternatives import Gateway, Recovery, marker_key, sign_marker, verify_marker
from watcher_agent_router.exchange import withheld_notice
from watcher_agent_router.processor import MAX_BODY, WatcherProcessor, _Exchange, app

from watcher_sdk import AsyncWatcherClient

CLIENT_KEY = "fixture-client-key"
REQUEST = {
    "model": "fixture",
    "messages": [{"role": "user", "content": "fixture marker"}],
    "tools": [{"type": "function", "function": {"name": "write_file"}}],
}
RESPONSE = {
    "choices": [
        {
            "index": 0,
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"type": "function", "id": "call-1", "function": {"name": "write_file", "arguments": "{}"}}
                ],
            },
        }
    ]
}


def decision(value: str) -> list[dict]:
    return [
        {
            "tool_use_id": "call-1",
            "decision": value,
            "judged_decision": value,
            "decision_source": "rule",
            "enforcement_mode": "enforce",
            "verdict": {},
            "latency_ms": 1,
        }
    ]


def fake_watcher(handler) -> AsyncWatcherClient:
    return AsyncWatcherClient(
        "http://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="http://watcher.invalid", transport=httpx.MockTransport(handler)),
    )


def headers(*, end_of_stream: bool = False, raw: bool = True, **values: str) -> ext_proc.HttpHeaders:
    """Build an Envoy header message; Envoy may use either value field."""
    items = [
        HeaderValue(key=key.replace("_", "-").replace("pseudo-", ":"), raw_value=value.encode())
        if raw
        else HeaderValue(key=key.replace("_", "-").replace("pseudo-", ":"), value=value)
        for key, value in values.items()
    ]
    return ext_proc.HttpHeaders(headers=HeaderMap(headers=items), end_of_stream=end_of_stream)


def chat_request_headers(**extra: str) -> ext_proc.ProcessingRequest:
    values = {
        "pseudo_method": "POST",
        "pseudo_path": "/v1/chat/completions",
        "user_agent": "fixture/1.0",
        "x_api_key": CLIENT_KEY,
        **extra,
    }
    return ext_proc.ProcessingRequest(request_headers=headers(**values))


def body(field: str, payload: object, end_of_stream: bool = True) -> ext_proc.ProcessingRequest:
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return ext_proc.ProcessingRequest(**{field: ext_proc.HttpBody(body=data, end_of_stream=end_of_stream)})


def response_headers(status: str = "200", **extra: str) -> ext_proc.ProcessingRequest:
    return ext_proc.ProcessingRequest(response_headers=headers(pseudo_status=status, **extra))


def immediate(reply: ext_proc.ProcessingResponse) -> tuple[int, dict, dict]:
    assert reply.HasField("immediate_response")
    response = reply.immediate_response
    header_values = {item.header.key: item.header.raw_value.decode() for item in response.headers.set_headers}
    return response.status.code, header_values, json.loads(response.body)


async def run_exchange(processor_: WatcherProcessor, *messages: ext_proc.ProcessingRequest):
    exchange = _Exchange()
    return exchange, [await processor_.handle(exchange, message) for message in messages]


async def test_allowed_exchange_passes_through_with_conversation_header():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=decision("allow"))

    async with fake_watcher(handler) as client:
        exchange, replies = await run_exchange(
            WatcherProcessor(client, CLIENT_KEY),
            chat_request_headers(),
            body("request_body", REQUEST),
            response_headers(),
            body("response_body", RESPONSE),
        )
    assert replies[0].request_headers.response.header_mutation.remove_headers == [
        "x-api-key",
        "accept-encoding",
        "x-watcher-alternative",
    ]
    assert replies[1].HasField("request_body") and not replies[1].request_body.response.HasField("body_mutation")
    [header] = replies[2].response_headers.response.header_mutation.set_headers
    assert header.header.key == "x-watcher-conversation-id"
    assert header.header.raw_value.decode() == exchange.conversation_id
    assert exchange.conversation_id.startswith("agent-router:")
    assert replies[3].HasField("response_body") and not replies[3].response_body.response.HasField("body_mutation")
    assert seen[0]["external_ids"] == {"other": exchange.conversation_id}
    assert seen[0]["user_agent"] == "fixture/1.0"


@pytest.mark.parametrize("verdict", ["deny", "escalate"])
async def test_refused_call_becomes_an_ordinary_response_without_it(verdict):
    """The harness receives a normal completion explaining the refusal, never an error or the call."""
    async with fake_watcher(lambda _: httpx.Response(200, json=decision(verdict))) as client:
        with structlog.testing.capture_logs() as logs:
            exchange, replies = await run_exchange(
                WatcherProcessor(client, CLIENT_KEY),
                chat_request_headers(),
                body("request_body", REQUEST),
                response_headers(),
                body("response_body", RESPONSE),
            )
    common = replies[-1].response_body.response
    delivered = json.loads(common.body_mutation.body)
    [length] = common.header_mutation.set_headers
    assert length.header.key == "content-length" and int(length.header.raw_value) == len(common.body_mutation.body)
    choice = delivered["choices"][0]
    assert choice["finish_reason"] == "stop" and "tool_calls" not in choice["message"]
    assert "Watcher did not approve" in choice["message"]["content"]
    assert json.loads(choice["message"]["content"].split("\n\n", 1)[1])[0]["is_escalation"] is (verdict == "escalate")
    assert logs == [
        {
            "event": "tool_calls_withheld",
            "log_level": "info",
            "conversation_id": exchange.conversation_id,
            "denied": 1,
            "escalated": int(verdict == "escalate"),
        }
    ]


async def test_unmatched_decisions_still_withhold_with_403():
    mismatched = [{**decision("allow")[0], "tool_use_id": "other"}]
    async with fake_watcher(lambda _: httpx.Response(200, json=mismatched)) as client:
        exchange, replies = await run_exchange(
            WatcherProcessor(client, CLIENT_KEY),
            chat_request_headers(),
            body("request_body", REQUEST),
            response_headers(),
            body("response_body", RESPONSE),
        )
    status, header_values, error = immediate(replies[-1])
    assert status == 403 and header_values["x-watcher-conversation-id"] == exchange.conversation_id
    assert error["error"]["type"] == "watcher_withheld" and "fixture marker" not in json.dumps(error)


@pytest.mark.parametrize(
    "failure,status",
    [(400, 403), (422, 403), (408, 503), (429, 503), (503, 503), ("connection", 503)],
)
async def test_watcher_failures_map_to_permanent_or_transient(failure, status):
    def handler(request):
        if failure == "connection":
            raise httpx.ConnectError("fixture connection failure", request=request)
        return httpx.Response(failure, json={"detail": "fixture"})

    async with fake_watcher(handler) as client:
        with structlog.testing.capture_logs() as logs:
            exchange, replies = await run_exchange(
                WatcherProcessor(client, CLIENT_KEY),
                chat_request_headers(),
                body("request_body", REQUEST),
                response_headers(),
                body("response_body", RESPONSE),
            )
    assert immediate(replies[-1])[0] == status
    # Operators can tell outages from rejections, and no exchange content is logged.
    [event] = logs
    assert event["event"] == "exchange_withheld" and event["conversation_id"] == exchange.conversation_id
    assert event["status"] == status
    if failure == "connection":
        assert event["error_type"] == "WatcherConnectionError"
    else:
        assert event["watcher_status"] == failure
    assert "fixture marker" not in json.dumps(event)


async def test_watcher_decision_has_a_total_deadline(monkeypatch):
    """A decision slower than the deadline ends in the processor's own logged 503."""

    async def stalled(_request):
        await asyncio.sleep(5)

    monkeypatch.setattr(processor, "WATCHER_DEADLINE_SECONDS", 0.05)
    async with fake_watcher(stalled) as client:
        with structlog.testing.capture_logs() as logs:
            _, replies = await run_exchange(
                WatcherProcessor(client, CLIENT_KEY),
                chat_request_headers(),
                body("request_body", REQUEST),
                response_headers(),
                body("response_body", RESPONSE),
            )
    assert immediate(replies[-1])[0] == 503
    assert logs[-1]["error_type"] == "TimeoutError"


@pytest.mark.parametrize(
    "response_message",
    [
        body("response_body", RESPONSE, end_of_stream=False),
        body("response_body", b"not json"),
        body("response_body", ["not", "an", "object"]),
        body("response_body", b"x" * (MAX_BODY + 1)),
    ],
)
async def test_unverifiable_response_body_is_withheld(response_message):
    async with fake_watcher(lambda _: pytest.fail("Watcher must not be called")) as client:
        _, replies = await run_exchange(
            WatcherProcessor(client, CLIENT_KEY),
            chat_request_headers(),
            body("request_body", REQUEST),
            response_headers(),
            response_message,
        )
    assert immediate(replies[-1])[0] == 403


@pytest.mark.parametrize("content_type", ["application/json", "text/event-stream"])
async def test_compressed_success_is_refused_before_its_headers_go_downstream(content_type):
    """A rewritten body would not match the Content-Encoding already sent to the client."""
    async with fake_watcher(lambda _: pytest.fail("Watcher must not be called")) as client:
        _, replies = await run_exchange(
            WatcherProcessor(client, CLIENT_KEY),
            chat_request_headers(),
            body("request_body", {**REQUEST, "stream": content_type == "text/event-stream"}),
            response_headers(content_encoding="gzip", content_type=content_type),
        )
    status, _headers, error = immediate(replies[-1])
    assert status == 403 and error["error"]["type"] == "watcher_withheld"


async def test_compressed_provider_error_passes_through():
    async with fake_watcher(lambda _: pytest.fail("Watcher must not be called")) as client:
        processor_ = WatcherProcessor(client, CLIENT_KEY)
        exchange = _Exchange(conversation_id="agent-router:x", request=REQUEST)
        reply = await processor_.handle(exchange, response_headers("503", content_encoding="gzip"))
    assert reply.HasField("response_headers")


async def test_response_without_validated_request_is_withheld():
    async with fake_watcher(lambda _: pytest.fail("Watcher must not be called")) as client:
        processor_ = WatcherProcessor(client, CLIENT_KEY)
        exchange = _Exchange(conversation_id="agent-router:x", status="200", encoding="identity")
        assert immediate(await processor_.handle(exchange, body("response_body", RESPONSE)))[0] == 403


@pytest.mark.parametrize("status,expected", [("200", 404), ("404", None), ("503", None)])
async def test_gateway_generated_response_without_a_request(status, expected):
    """Agent Router's own replies reach this processor with no request phase before them."""
    async with fake_watcher(lambda _: pytest.fail("Watcher must not be called")) as client:
        reply = await WatcherProcessor(client, CLIENT_KEY).handle(_Exchange(), response_headers(status))
    if expected is None:
        assert reply.HasField("response_headers") and not reply.response_headers.HasField("response")
    else:
        assert immediate(reply)[0] == expected


@pytest.mark.parametrize("status", ["301", "302", "307", "308"])
async def test_provider_redirect_is_refused_at_the_headers(status):
    """A followed redirect would fetch a completion from outside the gateway."""
    async with fake_watcher(lambda _: pytest.fail("Watcher must not be called")) as client:
        exchange, replies = await run_exchange(
            WatcherProcessor(client, CLIENT_KEY),
            chat_request_headers(),
            body("request_body", REQUEST),
            response_headers(status, location="https://elsewhere.example/v1/chat/completions"),
        )
    code, header_values, _error = immediate(replies[-1])
    assert code == 502 and "location" not in header_values
    assert header_values["x-watcher-conversation-id"] == exchange.conversation_id


async def test_response_without_a_status_is_evaluated_not_passed_through():
    async with fake_watcher(lambda _: httpx.Response(200, json=decision("deny"))) as client:
        processor_ = WatcherProcessor(client, CLIENT_KEY)
        exchange = _Exchange(conversation_id="agent-router:x", request=REQUEST, encoding="identity")
        reply = await processor_.handle(exchange, body("response_body", RESPONSE))
    assert (
        "Watcher did not approve"
        in json.loads(reply.response_body.response.body_mutation.body)["choices"][0]["message"]["content"]
    )


async def test_provider_error_passes_through_without_watcher():
    async with fake_watcher(lambda _: pytest.fail("Watcher must not be called")) as client:
        _, replies = await run_exchange(
            WatcherProcessor(client, CLIENT_KEY),
            chat_request_headers(),
            body("request_body", REQUEST),
            response_headers("429"),
            body("response_body", {"error": {"message": "rate limited"}}),
        )
    assert replies[-1].HasField("response_body")


@pytest.mark.parametrize(
    "message,status",
    [
        (chat_request_headers(pseudo_method="GET"), 404),
        (chat_request_headers(pseudo_path="/v1/embeddings"), 404),
        (chat_request_headers(pseudo_path="/v1/chat/completions/extra"), 404),
        (
            ext_proc.ProcessingRequest(
                request_headers=headers(
                    end_of_stream=True, pseudo_method="POST", pseudo_path="/v1/chat/completions", x_api_key=CLIENT_KEY
                )
            ),
            400,
        ),
        (chat_request_headers(x_api_key="wrong"), 401),
        (chat_request_headers(x_api_key=""), 401),
        (ext_proc.ProcessingRequest(request_headers=headers(pseudo_method="GET", pseudo_path="/v1/models")), 401),
        (ext_proc.ProcessingRequest(request_trailers=ext_proc.HttpTrailers()), 500),
    ],
)
async def test_uncovered_requests_are_rejected_at_the_gateway(message, status):
    async with fake_watcher(lambda _: pytest.fail("Watcher must not be called")) as client:
        reply = await WatcherProcessor(client, CLIENT_KEY).handle(_Exchange(), message)
    assert immediate(reply)[0] == status


async def test_query_string_and_plain_header_values_are_accepted():
    async with fake_watcher(lambda _: pytest.fail("Watcher must not be called")) as client:
        message = ext_proc.ProcessingRequest(
            request_headers=headers(
                raw=False, pseudo_method="POST", pseudo_path="/v1/chat/completions?x=1", x_api_key=CLIENT_KEY
            )
        )
        reply = await WatcherProcessor(client, CLIENT_KEY).handle(_Exchange(), message)
    assert reply.HasField("request_headers")


@pytest.mark.parametrize(
    "request_message",
    [
        body("request_body", {**REQUEST, "n": 2}),
        body("request_body", b"{"),
        body("request_body", REQUEST, end_of_stream=False),
        body("request_body", b"x" * (MAX_BODY + 1)),
    ],
)
async def test_unsupported_request_body_is_rejected_before_the_provider(request_message):
    async with fake_watcher(lambda _: pytest.fail("Watcher must not be called")) as client:
        _, replies = await run_exchange(WatcherProcessor(client, CLIENT_KEY), chat_request_headers(), request_message)
    assert immediate(replies[-1])[0] == 400


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.mark.parametrize("gateway_url", [None, "http://127.0.0.1:1975"])
async def test_served_streams_end_normally_or_after_an_immediate_response(monkeypatch, gateway_url):
    """Serve over real gRPC and require the credential check before listening."""
    calls = []
    verdicts = iter([decision("allow"), [{"status_code": 503, "detail": "unavailable", "tool_use_id": "call-1"}]])

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/v1/auth/check-permissions":
            return httpx.Response(200, json={"granted": True, "missing": []})
        return httpx.Response(200, json=next(verdicts))

    monkeypatch.setattr(processor, "AsyncWatcherClient", lambda *args, **kwargs: fake_watcher(handler))
    address = f"127.0.0.1:{_free_port()}"
    ready = asyncio.Event()
    configured = []

    class Recording(WatcherProcessor):
        def __init__(self, *args, **kwargs):
            configured.append(kwargs)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(processor, "WatcherProcessor", Recording)
    server = asyncio.create_task(
        processor._serve(address, "http://watcher.invalid", "key", CLIENT_KEY, ready, gateway_url)
    )
    await asyncio.wait_for(ready.wait(), 10)
    try:
        async with grpc.aio.insecure_channel(address) as channel:
            stub = ext_proc_grpc.ExternalProcessorStub(channel)
            messages = [
                chat_request_headers(),
                body("request_body", REQUEST),
                response_headers(),
                body("response_body", RESPONSE),
            ]
            allowed = [reply async for reply in stub.Process(iter(messages))]
            # A message after the immediate response must not be answered.
            denied = [reply async for reply in stub.Process(iter([*messages, body("response_body", RESPONSE)]))]
    finally:
        server.cancel()
        with pytest.raises(asyncio.CancelledError):
            await server
    assert calls == ["/v1/auth/check-permissions", "/v1/hooks/pre-tool-use", "/v1/hooks/pre-tool-use"]
    assert len(allowed) == 4 and allowed[-1].HasField("response_body")
    assert len(denied) == 4 and immediate(denied[-1])[0] == 403
    [kwargs] = configured
    assert kwargs["marker"] == marker_key("key")
    assert (kwargs["gateway"] is None) is (gateway_url is None)


async def test_serve_refuses_a_credential_without_ingestion(monkeypatch):
    monkeypatch.setattr(
        processor,
        "AsyncWatcherClient",
        lambda *args, **kwargs: fake_watcher(
            lambda _: httpx.Response(200, json={"granted": False, "missing": ["sessions:ingest"]})
        ),
    )
    with pytest.raises(PermissionError):
        await processor._serve("127.0.0.1:0", "http://watcher.invalid", "key", None, asyncio.Event())


def test_cli_requires_watcher_configuration(monkeypatch):
    monkeypatch.delenv("WATCHER_BASE_URL", raising=False)
    monkeypatch.delenv("WATCHER_API_KEY", raising=False)
    result = CliRunner().invoke(app, ["serve"])
    assert result.exit_code == 2 and "WATCHER_BASE_URL" in result.output


def test_cli_serves_with_environment_configuration(monkeypatch):
    started = []

    async def fake_serve(address, api_url, api_key, client_key, ready, gateway_url):
        started.append((address, api_url, api_key, client_key, ready.is_set(), gateway_url))

    monkeypatch.setattr(processor, "_serve", fake_serve)
    monkeypatch.setenv("WATCHER_BASE_URL", "http://watcher.invalid")
    monkeypatch.setenv("WATCHER_API_KEY", "key")
    monkeypatch.setenv("GATEWAY_API_KEY", CLIENT_KEY)
    monkeypatch.delenv("GATEWAY_URL", raising=False)
    result = CliRunner().invoke(app, ["serve", "--address", "unix:/tmp/watcher.sock"])
    assert result.exit_code == 0 and "without alternatives" in result.output
    monkeypatch.setenv("GATEWAY_URL", "http://127.0.0.1:1975")
    assert CliRunner().invoke(app, ["serve", "--address", "unix:/tmp/watcher.sock"]).exit_code == 0
    assert started == [
        ("unix:/tmp/watcher.sock", "http://watcher.invalid", "key", CLIENT_KEY, False, None),
        ("unix:/tmp/watcher.sock", "http://watcher.invalid", "key", CLIENT_KEY, False, "http://127.0.0.1:1975"),
    ]


def test_cli_requires_a_client_key_unless_explicitly_disabled(monkeypatch):
    started = []

    async def fake_serve(address, api_url, api_key, client_key, ready, gateway_url):
        started.append(client_key)

    monkeypatch.setattr(processor, "_serve", fake_serve)
    monkeypatch.setenv("WATCHER_BASE_URL", "http://watcher.invalid")
    monkeypatch.setenv("WATCHER_API_KEY", "key")
    monkeypatch.delenv("GATEWAY_API_KEY", raising=False)
    monkeypatch.delenv("GATEWAY_URL", raising=False)
    refused = CliRunner().invoke(app, ["serve"])
    assert refused.exit_code == 2 and "GATEWAY_API_KEY" in refused.output and started == []
    allowed = CliRunner().invoke(app, ["serve", "--allow-unauthenticated-clients"])
    assert allowed.exit_code == 0 and started == [None]
    # The flag wins over a leftover key, so Gateway-authenticated clients are not refused.
    monkeypatch.setenv("GATEWAY_API_KEY", CLIENT_KEY)
    overridden = CliRunner().invoke(app, ["serve", "--allow-unauthenticated-clients"])
    assert overridden.exit_code == 0 and started == [None, None]
    # Alternatives are requested as a gateway client, so they need the key.
    monkeypatch.setenv("GATEWAY_URL", "http://127.0.0.1:1975")
    keyless = CliRunner().invoke(app, ["serve", "--allow-unauthenticated-clients"])
    assert keyless.exit_code == 2 and "GATEWAY_URL requires GATEWAY_API_KEY" in keyless.output


async def test_unauthenticated_mode_accepts_requests_without_a_key():
    async with fake_watcher(lambda _: pytest.fail("Watcher must not be called")) as client:
        message = ext_proc.ProcessingRequest(
            request_headers=headers(pseudo_method="POST", pseudo_path="/v1/chat/completions")
        )
        reply = await WatcherProcessor(client, None).handle(_Exchange(), message)
    assert reply.HasField("request_headers")


def test_help_command_and_main(monkeypatch):
    assert "serve" in CliRunner().invoke(app, ["help"]).output
    monkeypatch.setattr("sys.argv", ["watcher-agent-router", "help"])
    with pytest.raises(SystemExit) as exited:
        processor.main()
    assert exited.value.code == 0


STREAM_REQUEST = {**REQUEST, "stream": True}


def sse(*payloads: object) -> bytes:
    return b"".join(f"data: {json.dumps(item)}\n\n".encode() for item in payloads)


STREAM_TEXT = sse({"choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hi"}, "finish_reason": None}]})
STREAM_TOOL = sse(
    {
        "choices": [
            {
                "index": 0,
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "write_file", "arguments": "{}"},
                        }
                    ]
                },
                "finish_reason": None,
            }
        ]
    },
    {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
)


def chunk_body(reply: ext_proc.ProcessingResponse) -> bytes:
    """What the client receives in place of one streamed chunk."""
    mutation = reply.response_body.response.body_mutation
    assert mutation.WhichOneof("mutation") in ("body", "clear_body")
    return mutation.body if mutation.WhichOneof("mutation") == "body" else b""


async def stream_exchange(handler, *chunks: bytes, encoding: str | None = None):
    """Run one streamed exchange; the last chunk ends the provider stream."""
    extra = {"content_encoding": encoding} if encoding else {}
    messages = [
        chat_request_headers(),
        body("request_body", STREAM_REQUEST),
        response_headers(content_type="text/event-stream; charset=utf-8", **extra),
        *[body("response_body", data, end_of_stream=index == len(chunks) - 1) for index, data in enumerate(chunks)],
    ]
    async with fake_watcher(handler) as client:
        with structlog.testing.capture_logs() as logs:
            exchange, replies = await run_exchange(WatcherProcessor(client, CLIENT_KEY), *messages)
    return exchange, replies, logs


async def test_streamed_response_switches_mode_and_releases_text_before_tools():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=decision("allow"))

    _, replies, _ = await stream_exchange(handler, STREAM_TEXT, STREAM_TOOL, b"data: [DONE]\n\n")
    assert replies[2].mode_override.response_body_mode == ProcessingMode.STREAMED
    assert chunk_body(replies[3]) == STREAM_TEXT
    assert chunk_body(replies[4]) == b""
    assert chunk_body(replies[5]) == STREAM_TOOL + b"data: [DONE]\n\n"
    [hook] = seen
    assert hook["request_body"]["stream"] is True
    message = hook["response_body"]["choices"][0]["message"]
    assert message["content"] == "Hi" and message["tool_calls"][0]["id"] == "call-1"


def parse_events(data: bytes) -> list:
    return [line[6:] if line == b"data: [DONE]" else json.loads(line[6:]) for line in data.split(b"\n\n") if line]


async def test_refused_streamed_call_ends_the_stream_normally_with_an_explanation():
    _, replies, logs = await stream_exchange(
        lambda _: httpx.Response(200, json=decision("deny")), STREAM_TEXT + STREAM_TOOL, b"data: [DONE]\n\n"
    )
    assert chunk_body(replies[3]) == STREAM_TEXT
    notice, finish, done = parse_events(chunk_body(replies[4]))
    assert notice["choices"][0]["delta"]["content"].startswith("\n\nWatcher did not approve")
    assert "tool_calls" not in notice["choices"][0]["delta"] and "error" not in notice
    assert finish["choices"][0]["finish_reason"] == "stop" and done == b"[DONE]"
    assert logs[-1]["event"] == "tool_calls_withheld"


async def test_refused_stream_without_prior_text_starts_the_assistant_message():
    _, replies, _ = await stream_exchange(lambda _: httpx.Response(200, json=decision("deny")), STREAM_TOOL)
    notice, _finish, _done = parse_events(chunk_body(replies[3]))
    assert notice["choices"][0]["delta"]["role"] == "assistant"
    assert notice["choices"][0]["delta"]["content"].startswith("Watcher did not approve")


async def test_text_only_stream_is_recorded_without_holding_text():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json=[])

    end = sse({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}) + b"data: [DONE]\n\n"
    _, replies, _ = await stream_exchange(handler, STREAM_TEXT, end)
    assert chunk_body(replies[3]) == STREAM_TEXT and chunk_body(replies[4]) == end
    assert seen == ["/v1/hooks/pre-tool-use"]


async def test_malformed_stream_is_cut_off_and_the_rest_dropped():
    _, replies, logs = await stream_exchange(
        lambda _: pytest.fail("Watcher must not be called"), b"data: not json\n\n", STREAM_TOOL, b""
    )
    assert b"watcher_withheld" in chunk_body(replies[3])
    assert chunk_body(replies[4]) == b"" and chunk_body(replies[5]) == b""
    assert logs[0]["check"] == "Body is not valid JSON"


async def test_watcher_outage_ends_a_streamed_response():
    def handler(request):
        raise httpx.ConnectError("fixture connection failure", request=request)

    _, replies, logs = await stream_exchange(handler, STREAM_TOOL)
    assert b"watcher_withheld" in chunk_body(replies[3]) and b"call-1" not in chunk_body(replies[3])
    assert logs[-1]["status"] == 503
    # The client can tell a retryable outage from a refusal.
    assert json.loads(chunk_body(replies[3])[6:])["error"]["code"] == 503


@pytest.mark.parametrize(
    "stream,content_type,status",
    [(False, "text/event-stream", "200"), (True, "application/json", "200"), (True, "text/event-stream", "429")],
)
async def test_only_streamed_success_responses_switch_mode(stream, content_type, status):
    async with fake_watcher(lambda _: pytest.fail("Watcher must not be called")) as client:
        processor_ = WatcherProcessor(client, CLIENT_KEY)
        exchange = _Exchange(conversation_id="agent-router:x", request={**REQUEST, "stream": stream})
        reply = await processor_.handle(exchange, response_headers(status, content_type=content_type))
    assert not reply.HasField("mode_override") and exchange.gate is None


async def test_streamed_response_that_fails_the_delivery_inventory_is_cut_off():
    """A tool call cut short by the token limit cannot be verified, so it never reaches the client."""
    truncated = STREAM_TOOL.replace(b'"finish_reason": "tool_calls"', b'"finish_reason": "length"')
    _, replies, logs = await stream_exchange(lambda _: pytest.fail("Watcher must not be called"), truncated)
    assert b"call-1" not in chunk_body(replies[3]) and b"watcher_withheld" in chunk_body(replies[3])
    assert logs[-1]["check"] == "Incomplete executable response"


@pytest.mark.parametrize("field", ["reasoning_details", "tool_calls"])
@pytest.mark.parametrize("value", [1, True])
async def test_scalar_list_fields_end_the_stream_with_a_refusal(field, value):
    bad = sse({"choices": [{"index": 0, "delta": {field: value}, "finish_reason": None}]})
    finish = sse({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
    tool_event = STREAM_TOOL[: STREAM_TOOL.index(b"\n\n") + 2]
    _, replies, logs = await stream_exchange(
        lambda _: pytest.fail("Watcher must not be called"), tool_event + bad + finish
    )
    final = chunk_body(replies[3])
    assert b"call-1" not in final and json.loads(final[6:])["error"]["code"] == 403
    assert len(logs) == 1 and logs[0]["check"].startswith("Invalid streamed")


async def test_unexpected_parsing_failure_still_ends_the_stream(monkeypatch):
    def broken(self):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(processor.StreamGate, "completion", broken)
    _, replies, logs = await stream_exchange(lambda _: pytest.fail("Watcher must not be called"), STREAM_TOOL)
    assert b"watcher_withheld" in chunk_body(replies[3]) and logs[-1]["error_type"] == "RuntimeError"


@pytest.mark.parametrize("status", ["200", "204"])
async def test_bodyless_success_is_refused_at_the_headers(status):
    async with fake_watcher(lambda _: pytest.fail("Watcher must not be called")) as client:
        processor_ = WatcherProcessor(client, CLIENT_KEY)
        exchange = _Exchange(conversation_id="agent-router:x", request=REQUEST)
        message = ext_proc.ProcessingRequest(response_headers=headers(end_of_stream=True, pseudo_status=status))
        assert immediate(await processor_.handle(exchange, message))[0] == 502


async def test_bodyless_provider_error_still_passes_through():
    async with fake_watcher(lambda _: pytest.fail("Watcher must not be called")) as client:
        processor_ = WatcherProcessor(client, CLIENT_KEY)
        exchange = _Exchange(conversation_id="agent-router:x", request=REQUEST)
        message = ext_proc.ProcessingRequest(response_headers=headers(end_of_stream=True, pseudo_status="503"))
        assert (await processor_.handle(exchange, message)).HasField("response_headers")


async def test_denied_non_ascii_arguments_are_not_escaped_in_the_rewritten_body():
    response = json.loads(json.dumps(RESPONSE))
    response["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = json.dumps(
        {"t": "é" * 1000}, ensure_ascii=False
    )
    async with fake_watcher(lambda _: httpx.Response(200, json=decision("deny"))) as client:
        _, replies = await run_exchange(
            WatcherProcessor(client, CLIENT_KEY),
            chat_request_headers(),
            body("request_body", REQUEST),
            response_headers(),
            body("response_body", json.dumps(response, ensure_ascii=False).encode()),
        )
    rewritten = replies[-1].response_body.response.body_mutation.body
    assert b"\\u00e9" not in rewritten and "é".encode() in rewritten


async def test_denied_body_is_bounded_whatever_the_identifiers(monkeypatch):
    monkeypatch.setattr(processor, "MAX_BODY", 120_000)
    response = json.loads(json.dumps(RESPONSE))
    call = response["choices"][0]["message"]["tool_calls"][0]
    call["id"] = "\\\\" * 20_000
    response["choices"][0]["message"]["tool_calls"].append(
        {"type": "function", "id": "é" * 20_000, "function": {"name": "read_file", "arguments": "{}"}}
    )
    response["choices"][0]["message"]["content"] = '"' * 30_000
    response["id"] = "i" * 1_000
    outcomes = [
        {**decision("deny")[0], "tool_use_id": call["id"]},
        {**decision("allow")[0], "tool_use_id": "é" * 20_000},
    ]
    evaluation = None
    async with fake_watcher(lambda _: httpx.Response(200, json=outcomes)) as client:
        evaluation = await processor.evaluate(client, REQUEST, response, conversation_id="agent-router:x")
    recovery = Recovery(notices=[withheld_notice(response, evaluation)])
    full = processor._denied_body(response, evaluation, recovery)
    assert len(full) <= 120_000 and b"\\\\\\\\" * 300 not in full
    delivered = json.loads(full)["choices"][0]
    assert "tool_calls" not in delivered["message"] and delivered["finish_reason"] == "stop"

    monkeypatch.setattr(processor, "MAX_BODY", 1_000)
    compact = json.loads(processor._denied_body(response, evaluation, recovery))
    assert compact["choices"][0]["message"] == {
        "role": "assistant",
        "content": "Watcher did not approve 1 tool calls, so the gateway withheld them and 1 other calls"
        " from the same response. None of them were run.",
    }
    assert len(compact["id"]) == 256


def test_compact_fallback_is_a_valid_chat_completion(monkeypatch):
    from openai.types.chat import ChatCompletion
    from watcher_agent_router.exchange import Denial, Evaluation

    response = json.loads(json.dumps(RESPONSE)) | {"id": "c-1", "created": 7, "model": "m" * 1000}
    evaluation = Evaluation(
        verified=True,
        denials=[Denial(tool_use_id="call-1", tool_name="write_file", tool_input={}, reason="no", is_escalation=False)],
    )
    monkeypatch.setattr(processor, "MAX_BODY", 10)
    recovery = Recovery(notices=["no"])
    completion = ChatCompletion.model_validate_json(processor._denied_body(response, evaluation, recovery))
    assert completion.created == 7 and len(completion.model) == 256
    assert completion.choices[0].finish_reason == "stop" and not completion.choices[0].message.tool_calls


async def test_streamed_denial_drops_oversized_usage_and_fits_the_reply_limit():
    usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "extension": [0] * 200_000}
    tail = sse({"choices": [], "usage": usage}) + b"data: [DONE]\n\n"
    _, replies, _ = await stream_exchange(lambda _: httpx.Response(200, json=decision("deny")), STREAM_TOOL + tail)
    reply = replies[3]
    assert reply.ByteSize() < processor._GRPC_MESSAGE_LIMIT
    events = parse_events(chunk_body(reply))
    assert all("usage" not in event for event in events if isinstance(event, dict))
    assert not any(
        event["choices"] and "tool_calls" in event["choices"][0]["delta"] for event in events if isinstance(event, dict)
    )


async def test_streamed_denial_falls_back_to_a_short_notice_near_the_reply_limit(monkeypatch):
    monkeypatch.setattr(processor, "_GRPC_MESSAGE_LIMIT", processor._REPLY_HEADROOM + 100)
    _, replies, _ = await stream_exchange(lambda _: httpx.Response(200, json=decision("deny")), STREAM_TOOL)
    notice = parse_events(chunk_body(replies[3]))[0]["choices"][0]["delta"]["content"]
    assert notice.startswith("Watcher did not approve 1 tool calls") and "{" not in notice


MARKER_KEY = marker_key("fixture-watcher-key")
ALTERNATIVE = {
    "id": "chatcmpl-alt",
    "choices": [
        {
            "index": 0,
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": "Reading instead.",
                "tool_calls": [
                    {"type": "function", "id": "call-9", "function": {"name": "read_file", "arguments": '{"p":1}'}}
                ],
            },
        }
    ],
}


def alternative_watcher(first: str = "deny"):
    """Refuse the client's proposal, then allow the alternative; record each hook body."""
    hooks = []

    def handler(request):
        hooks.append(json.loads(request.content))
        if len(hooks) == 1:
            return httpx.Response(200, json=decision(first))
        return httpx.Response(200, json=[{**decision("allow")[0], "tool_use_id": "call-9"}])

    return handler, hooks


def listener(http: httpx.AsyncClient) -> Gateway:
    return Gateway(client=http, client_key=CLIENT_KEY, marker_key=MARKER_KEY, max_body=MAX_BODY)


@pytest.mark.parametrize("valid", [True, False])
async def test_marked_alternative_request_passes_through_ungraded(valid):
    """The requesting pass grades its own alternative, so the nested pass must not grade it again."""
    data = json.dumps(REQUEST).encode()
    marker = sign_marker(MARKER_KEY, data if valid else b"{}", expiry=10**10)
    async with fake_watcher(lambda _: pytest.fail("Watcher must not be called")) as client:
        exchange, replies = await run_exchange(
            WatcherProcessor(client, CLIENT_KEY, marker=MARKER_KEY),
            chat_request_headers(x_watcher_alternative=marker),
            body("request_body", data),
            *([response_headers(content_type="text/event-stream"), body("response_body", RESPONSE)] if valid else []),
        )
    assert "x-watcher-alternative" in replies[0].request_headers.response.header_mutation.remove_headers
    if not valid:
        assert immediate(replies[-1])[0] == 403
        return
    assert exchange.passthrough and exchange.gate is None
    assert not replies[2].response_headers.response.HasField("header_mutation")
    assert not replies[3].response_body.response.HasField("body_mutation")


@pytest.mark.parametrize(
    "status,extra,expected",
    [("200", {"content_encoding": "gzip"}, 403), ("307", {"location": "http://elsewhere.invalid"}, 502)],
)
async def test_marked_alternative_response_still_gets_header_checks(status, extra, expected):
    """A compressed or redirected alternative is refused before Agent Router decodes or forwards it."""
    data = json.dumps(REQUEST).encode()
    async with fake_watcher(lambda _: pytest.fail("Watcher must not be called")) as client:
        _, replies = await run_exchange(
            WatcherProcessor(client, CLIENT_KEY, marker=MARKER_KEY),
            chat_request_headers(x_watcher_alternative=sign_marker(MARKER_KEY, data, expiry=10**10)),
            body("request_body", data),
            response_headers(status, **extra),
        )
    assert immediate(replies[-1])[0] == expected


async def test_marker_is_refused_when_the_processor_has_no_key():
    async with fake_watcher(lambda _: pytest.fail("Watcher must not be called")) as client:
        data = json.dumps(REQUEST).encode()
        _, replies = await run_exchange(
            WatcherProcessor(client, CLIENT_KEY),
            chat_request_headers(x_watcher_alternative=sign_marker(MARKER_KEY, data, expiry=10**10)),
            body("request_body", data),
        )
    assert immediate(replies[-1])[0] == 403


def gateway_handler(sent: list, alternative: dict = ALTERNATIVE):
    def handler(request):
        sent.append(request)
        return httpx.Response(200, json=alternative)

    return handler


async def test_refused_buffered_proposal_is_replaced_by_an_approved_alternative():
    handler, hooks = alternative_watcher()
    sent: list = []
    async with (
        fake_watcher(handler) as client,
        httpx.AsyncClient(
            base_url="http://gateway.invalid", transport=httpx.MockTransport(gateway_handler(sent))
        ) as http,
    ):
        exchange, replies = await run_exchange(
            WatcherProcessor(client, CLIENT_KEY, marker=MARKER_KEY, gateway=listener(http)),
            chat_request_headers(),
            body("request_body", REQUEST),
            response_headers(),
            body("response_body", RESPONSE),
        )
    delivered = json.loads(replies[-1].response_body.response.body_mutation.body)["choices"][0]
    assert delivered["finish_reason"] == "tool_calls"
    assert delivered["message"]["tool_calls"] == ALTERNATIVE["choices"][0]["message"]["tool_calls"]
    content = delivered["message"]["content"]
    assert content.startswith("Watcher did not approve") and content.endswith("\n\nReading instead.")
    assert hooks[0]["external_ids"] == {"other": exchange.conversation_id}
    assert hooks[1]["external_ids"]["other"] != exchange.conversation_id
    assert len(sent) == 1 and verify_marker(MARKER_KEY, sent[0].headers["x-watcher-alternative"], sent[0].content)


async def test_refused_stream_continues_with_an_approved_alternative():
    handler, _ = alternative_watcher("escalate")
    reasoning = json.loads(json.dumps(ALTERNATIVE))
    reasoning["choices"][0]["message"]["reasoning_content"] = "Safer."
    async with (
        fake_watcher(handler) as client,
        httpx.AsyncClient(
            base_url="http://gateway.invalid", transport=httpx.MockTransport(gateway_handler([], reasoning))
        ) as http,
    ):
        processor_ = WatcherProcessor(client, CLIENT_KEY, marker=MARKER_KEY, gateway=listener(http))
        _, replies = await run_exchange(
            processor_,
            chat_request_headers(),
            body("request_body", STREAM_REQUEST),
            response_headers(content_type="text/event-stream"),
            body("response_body", STREAM_TEXT, end_of_stream=False),
            body("response_body", STREAM_TOOL),
        )
    events = parse_events(chunk_body(replies[-1]))
    assert events[-1] == b"[DONE]"
    content, calls, finish = events[0], events[1], events[2]
    assert (
        "role" not in content["choices"][0]["delta"] and content["choices"][0]["delta"]["reasoning_content"] == "Safer."
    )
    text = content["choices"][0]["delta"]["content"]
    assert text.startswith("\n\nWatcher did not approve") and text.endswith("\n\nReading instead.")
    [call] = calls["choices"][0]["delta"]["tool_calls"]
    assert call == {
        "index": 0,
        "id": "call-9",
        "type": "function",
        "function": {"name": "read_file", "arguments": '{"p":1}'},
    }
    assert finish["choices"][0]["finish_reason"] == "tool_calls"


async def test_alternative_too_large_for_the_stream_reply_falls_back_to_a_short_notice(monkeypatch):
    monkeypatch.setattr(processor, "_GRPC_MESSAGE_LIMIT", processor._REPLY_HEADROOM + 600)
    handler, _ = alternative_watcher()
    async with (
        fake_watcher(handler) as client,
        httpx.AsyncClient(
            base_url="http://gateway.invalid", transport=httpx.MockTransport(gateway_handler([]))
        ) as http,
    ):
        _, replies = await run_exchange(
            WatcherProcessor(client, CLIENT_KEY, marker=MARKER_KEY, gateway=listener(http)),
            chat_request_headers(),
            body("request_body", STREAM_REQUEST),
            response_headers(content_type="text/event-stream"),
            body("response_body", STREAM_TOOL),
        )
    events = parse_events(chunk_body(replies[-1]))
    assert events[0]["choices"][0]["delta"]["content"].endswith("The approved alternative was too large to deliver.")
    assert not any(event["choices"] and "tool_calls" in event["choices"][0]["delta"] for event in events[:-1])


def test_alternative_too_large_for_the_buffered_body_falls_back_to_a_short_notice(monkeypatch):
    from watcher_agent_router.exchange import Denial, Evaluation

    evaluation = Evaluation(
        verified=True,
        denials=[Denial(tool_use_id="call-1", tool_name="write_file", tool_input={}, reason="no", is_escalation=False)],
    )
    monkeypatch.setattr(processor, "MAX_BODY", 200)
    recovery = Recovery(notices=["no"], alternative=ALTERNATIVE)
    delivered = json.loads(processor._denied_body(RESPONSE, evaluation, recovery))
    message = delivered["choices"][0]["message"]
    assert "tool_calls" not in message and message["content"].endswith("too large to deliver.")


@pytest.mark.parametrize("alternatives", [False, True])
async def test_refused_proposal_with_content_parts_gets_a_controlled_reply(alternatives):
    response = json.loads(json.dumps(RESPONSE))
    response["choices"][0]["message"]["content"] = [{"type": "text", "text": "Let me write it."}]
    handler, _ = alternative_watcher()
    async with (
        fake_watcher(handler) as client,
        httpx.AsyncClient(
            base_url="http://gateway.invalid", transport=httpx.MockTransport(gateway_handler([]))
        ) as http,
    ):
        _, replies = await run_exchange(
            WatcherProcessor(client, CLIENT_KEY, marker=MARKER_KEY, gateway=listener(http) if alternatives else None),
            chat_request_headers(),
            body("request_body", REQUEST),
            response_headers(),
            body("response_body", response),
        )
    message = json.loads(replies[-1].response_body.response.body_mutation.body)["choices"][0]["message"]
    parts = message["content"]
    assert parts[0] == {"type": "text", "text": "Let me write it."}
    assert parts[1]["text"].startswith("Watcher did not approve")
    assert [call["id"] for call in message.get("tool_calls", [])] == (["call-9"] if alternatives else [])


async def test_alternatives_use_what_the_first_decision_left_of_one_deadline(monkeypatch):
    """The first grade and the alternative share a single budget; it is not restarted for recovery."""
    monkeypatch.setattr(processor, "WATCHER_DEADLINE_SECONDS", 0.4)

    async def slow_watcher(_request):
        await asyncio.sleep(0.25)
        return httpx.Response(200, json=decision("deny"))

    async def slow_gateway(_request):
        await asyncio.sleep(0.25)
        return httpx.Response(200, json=ALTERNATIVE)

    loop = asyncio.get_running_loop()
    async with (
        fake_watcher(slow_watcher) as client,
        httpx.AsyncClient(base_url="http://gateway.invalid", transport=httpx.MockTransport(slow_gateway)) as http,
    ):
        started = loop.time()
        _, replies = await run_exchange(
            WatcherProcessor(client, CLIENT_KEY, marker=MARKER_KEY, gateway=listener(http)),
            chat_request_headers(),
            body("request_body", REQUEST),
            response_headers(),
            body("response_body", RESPONSE),
        )
        elapsed = loop.time() - started
    message = json.loads(replies[-1].response_body.response.body_mutation.body)["choices"][0]["message"]
    assert "tool_calls" not in message and elapsed < 0.5
    assert message["content"].endswith("No alternative was delivered because the time limit was reached.")
