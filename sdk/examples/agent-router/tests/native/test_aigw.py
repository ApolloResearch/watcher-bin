"""Drive an installed ``aigw`` gateway with the Watcher processor attached.

Set ``AIGW_BIN`` to an Agent Router CLI binary to run these tests; they skip
otherwise. ``aigw run`` downloads Envoy on first use, so the first run needs
network access. The provider and the Watcher API are local fixtures: this
checks gateway wiring and delivery, not model quality or a real Watcher server.
"""

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import openai
import pytest
from aigw_support import (
    AIGW,
    GATEWAY_KEY,
    SLOW_GRADE_SECONDS,
    STREAM_PAUSE_SECONDS,
    Fixture,
    Provider,
    SimulatedWatcher,
    ask,
    client,
    running_gateway,
)

pytestmark = pytest.mark.skipif(not AIGW, reason="Set AIGW_BIN to an aigw binary to run native gateway tests")


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict]:
    """Run the installed processor CLI against the simulated provider and Watcher API."""
    provider, watcher = Fixture(Provider), Fixture(SimulatedWatcher)
    serve = [sys.executable, "-m", "watcher_agent_router.processor", "serve", "--address"]
    watcher_url = f"http://127.0.0.1:{watcher.server_port}"
    try:
        with running_gateway(tmp_path_factory.mktemp("aigw"), provider, watcher_url, "fixture-key", serve) as urls:
            yield {**urls, "provider": provider, "watcher": watcher}
    finally:
        provider.shutdown()
        watcher.shutdown()


@pytest.mark.parametrize(
    "marker,released",
    [("allow", True), ("deny", False), ("escalate", False), ("observe", True), ("paused", True)],
)
def test_tool_call_follows_watcher_decision(stack: dict, marker: str, released: bool) -> None:
    """Deliver the tool call only when Watcher's applied decision releases it."""
    before = len(stack["watcher"].requests)
    prompt = f"{marker} tool request"
    if released:
        raw = ask(stack, prompt)
        call = raw.parse().choices[0].message.tool_calls[0]
        assert call.id == f"call-{marker}" and json.loads(call.function.arguments) == {
            "path": "notes.txt",
            "force": True,
        }
        conversation = raw.headers["x-watcher-conversation-id"]
    else:
        # A refusal is an ordinary completion: no executable call, an explanation instead.
        raw = ask(stack, prompt)
        message = raw.parse().choices[0]
        assert message.finish_reason == "stop" and not message.message.tool_calls
        assert message.message.content.startswith("Watcher did not approve")
        assert f'"tool_use_id": "call-{marker}"' in message.message.content
        conversation = raw.headers["x-watcher-conversation-id"]
    path, _headers, hook = stack["watcher"].requests[-1]
    assert len(stack["watcher"].requests) == before + 1 and path == "/v1/hooks/pre-tool-use"
    assert hook["format"] == "raw" and hook["url"] == "/v1/chat/completions"
    assert hook["external_ids"] == {"other": conversation} and conversation.startswith("agent-router:")
    assert hook["request_body"]["messages"] == [{"role": "user", "content": prompt}]
    assert hook["response_body"]["choices"][0]["message"]["tool_calls"][0]["id"] == f"call-{marker}"


def test_provider_receives_gateway_credentials_and_uncompressed_request(stack: dict) -> None:
    """The gateway owns the provider key, and the processor strips Accept-Encoding."""
    client(stack).chat.completions.create(model="fixture-model", messages=[{"role": "user", "content": "hi"}])
    path, headers, _body = stack["provider"].requests[-1]
    lowered = {key.lower(): value for key, value in headers.items()}
    assert path == "/v1/chat/completions"
    assert lowered["authorization"] == "Bearer fixture-provider-key"
    assert "accept-encoding" not in lowered and "x-api-key" not in lowered


def test_text_only_response_is_still_submitted(stack: dict) -> None:
    before = len(stack["watcher"].requests)
    reply = client(stack).chat.completions.create(
        model="fixture-model", messages=[{"role": "user", "content": "hello there"}]
    )
    assert reply.choices[0].message.content == "Hello."
    assert len(stack["watcher"].requests) == before + 1


def test_compressed_provider_response_is_withheld(stack: dict) -> None:
    with pytest.raises(openai.PermissionDeniedError):
        ask(stack, "compressed tool request")


def test_provider_error_passes_through_unevaluated(stack: dict) -> None:
    before = len(stack["watcher"].requests)
    with pytest.raises(openai.RateLimitError):
        ask(stack, "provider error")
    assert len(stack["watcher"].requests) == before


def test_unsupported_requests_never_reach_the_provider(stack: dict) -> None:
    before = len(stack["provider"].requests)
    with pytest.raises(openai.BadRequestError):
        client(stack).chat.completions.create(model="fixture-model", messages=[{"role": "user", "content": "hi"}], n=2)
    with pytest.raises(openai.NotFoundError):
        client(stack).embeddings.create(model="fixture-model", input="hi")
    assert len(stack["provider"].requests) == before


def test_demo_client_receives_a_released_tool_call(stack: dict) -> None:
    """Run the shipped demo unchanged; the fixtures allow its tool call."""
    demo = Path(__file__).parents[2] / "demo/client.py"
    env = {
        **os.environ,
        "GATEWAY_BASE_URL": stack["base_url"] + "/v1",
        "GATEWAY_API_KEY": GATEWAY_KEY,
        "PROVIDER_MODEL": "fixture-model",
    }
    result = subprocess.run(
        [sys.executable, str(demo)], env=env, capture_output=True, text=True, timeout=60, check=True
    )
    assert "Conversation agent-router:" in result.stdout
    assert 'Released tool call: delete_file {"path": "notes.txt", "force": true}' in result.stdout


def test_envoy_applies_the_shipped_timeouts_and_fail_closed_processor(stack: dict) -> None:
    """Envoy must outlast the SDK's 420-second hook budget so slow grades are not cut off."""
    dump = json.dumps(httpx.get(stack["envoy_admin"] + "/config_dump", timeout=10).json())
    assert '"stream_idle_timeout": "660s"' in dump
    assert '"message_timeout": "450s"' in dump
    assert '"allow_mode_override": true' in dump
    # The Chat Completions route's overall deadline, shared by provider and grading.
    assert '"timeout": "660s"' in dump
    assert '"failure_mode_allow": true' not in dump


def test_slow_grade_is_still_released(stack: dict) -> None:
    """A grade slower than Envoy Gateway's default gRPC timeout still reaches the client."""
    started = time.monotonic()
    call = ask(stack, "slow tool request").parse().choices[0].message.tool_calls[0]
    assert call.id == "call-slow" and time.monotonic() - started >= SLOW_GRADE_SECONDS


@pytest.mark.parametrize("prompt", ["redirect tool request", "redirect empty tool request"])
def test_provider_redirect_is_never_followed(stack: dict, prompt: str) -> None:
    """A 307 must not reach the client, which would resend the POST outside the gateway."""
    target = Fixture(Provider)
    Provider.redirect_target = f"http://127.0.0.1:{target.server_port}/v1/chat/completions"
    try:
        with pytest.raises(openai.InternalServerError) as refused:
            ask(stack, prompt)
        assert refused.value.status_code == 502
        assert "location" not in refused.value.response.headers
        assert target.requests == []
    finally:
        target.shutdown()


@pytest.mark.parametrize("prompt", ["deny created tool request", "deny chunked tool request"])
def test_denied_call_in_201_or_chunked_response_is_withheld(stack: dict, prompt: str) -> None:
    before = len(stack["watcher"].requests)
    choice = ask(stack, prompt).parse().choices[0]
    assert not choice.message.tool_calls and "Watcher did not approve" in choice.message.content
    assert len(stack["watcher"].requests) == before + 1


def test_allowed_call_in_chunked_response_arrives_whole(stack: dict) -> None:
    call = ask(stack, "allow chunked tool request").parse().choices[0].message.tool_calls[0]
    assert call.id == "call-allow"


def test_responses_agent_router_generates_itself_are_handled(stack: dict) -> None:
    """Agent Router answers GET /v1/models and routing errors before this processor sees a request.

    Its model listing gets the same 404 as other uncovered paths; its own
    errors pass through so clients still see why a request failed.
    """
    before = len(stack["watcher"].requests), len(stack["provider"].requests)
    authenticated = {"x-api-key": GATEWAY_KEY}
    models = httpx.get(stack["base_url"] + "/v1/models", headers=authenticated, timeout=10)
    assert models.status_code == 404 and models.json()["error"]["type"] == "watcher_withheld"
    missing_model = httpx.post(stack["base_url"] + "/v1/chat/completions", json={}, headers=authenticated, timeout=10)
    assert 400 <= missing_model.status_code < 500
    assert (len(stack["watcher"].requests), len(stack["provider"].requests)) == before


@pytest.mark.parametrize("gateway_key", ["", "wrong-key"])
def test_clients_without_the_gateway_key_never_reach_the_provider(stack: dict, gateway_key: str) -> None:
    """The gateway injects the operator's provider key, so it must not serve anonymous callers."""
    before = len(stack["watcher"].requests), len(stack["provider"].requests)
    with pytest.raises(openai.AuthenticationError):
        client(stack, gateway_key).chat.completions.create(
            model="fixture-model", messages=[{"role": "user", "content": "hello there"}]
        )
    assert (len(stack["watcher"].requests), len(stack["provider"].requests)) == before


def _stream(stack: dict, prompt: str) -> tuple[float | None, list]:
    """Stream one request; return seconds until the first text and every chunk received."""
    started, first_text, chunks = time.monotonic(), None, []
    stream = client(stack).chat.completions.create(
        model="fixture-model",
        messages=[{"role": "user", "content": prompt}],
        tools=[{"type": "function", "function": {"name": "delete_file", "parameters": {"type": "object"}}}],
        stream=True,
    )
    for item in stream:
        chunks.append(item)
        if first_text is None and item.choices and item.choices[0].delta.content:
            first_text = time.monotonic() - started
    return first_text, chunks


def test_streamed_text_arrives_before_the_provider_finishes(stack: dict) -> None:
    before = len(stack["watcher"].requests)
    first_text, chunks = _stream(stack, "allow tool request")
    assert first_text is not None and first_text < STREAM_PAUSE_SECONDS
    calls = [call for item in chunks if item.choices for call in item.choices[0].delta.tool_calls or []]
    assert calls and calls[0].id == "call-stream"
    _path, _headers, hook = stack["watcher"].requests[-1]
    assert len(stack["watcher"].requests) == before + 1 and hook["request_body"]["stream"] is True
    message = hook["response_body"]["choices"][0]["message"]
    assert message["content"] == "Working on it. "
    assert message["tool_calls"][0]["function"]["arguments"] == '{"path": "notes.txt"}'


def test_denied_streamed_tool_call_never_reaches_the_client(stack: dict) -> None:
    """The stream ends normally: the text so far, then an explanation instead of the call."""
    _first, received = _stream(stack, "deny tool request")
    assert not any(item.choices and item.choices[0].delta.tool_calls for item in received)
    text = "".join(item.choices[0].delta.content or "" for item in received if item.choices)
    assert text.startswith("Working on it. \n\nWatcher did not approve")
    assert received[-1].choices[0].finish_reason == "stop"


def test_text_only_stream_is_recorded(stack: dict) -> None:
    before = len(stack["watcher"].requests)
    _first, chunks = _stream(stack, "hello there")
    text = "".join(item.choices[0].delta.content or "" for item in chunks if item.choices)
    assert text == "Working on it. Done." and len(stack["watcher"].requests) == before + 1


@pytest.mark.parametrize("prompt", ["allow crlf tool request", "allow lone-cr tool request"])
def test_cr_and_crlf_streams_are_gated_and_delivered(stack: dict, prompt: str) -> None:
    first_text, chunks = _stream(stack, prompt)
    # A CR-ended event is only known complete once the next byte shows it is not a CRLF.
    assert first_text is not None and ("lone-cr" in prompt or first_text < STREAM_PAUSE_SECONDS)
    assert any(item.choices and item.choices[0].delta.tool_calls for item in chunks)


def test_tool_event_behind_a_lone_cr_is_still_held(stack: dict) -> None:
    _first, received = _stream(stack, "deny hidden tool request")
    assert not any(item.choices and item.choices[0].delta.tool_calls for item in received)
    assert received[-1].choices[0].finish_reason == "stop"


@pytest.mark.parametrize("prompt", ["allow late tool request", "allow twin tool request"])
def test_tool_events_the_gate_cannot_vouch_for_never_reach_the_client(stack: dict, prompt: str) -> None:
    """Data after [DONE] or a second choice ends the stream with an error instead of a call."""
    received: list = []
    with pytest.raises(openai.APIError):
        stream = client(stack).chat.completions.create(
            model="fixture-model",
            messages=[{"role": "user", "content": prompt}],
            tools=[{"type": "function", "function": {"name": "delete_file", "parameters": {"type": "object"}}}],
            stream=True,
        )
        received.extend(stream)
    assert not any(item.choices and item.choices[0].delta.tool_calls for item in received)


def test_denied_stream_keeps_requested_usage(stack: dict) -> None:
    stream = client(stack).chat.completions.create(
        model="fixture-model",
        messages=[{"role": "user", "content": "deny tool request"}],
        tools=[{"type": "function", "function": {"name": "delete_file", "parameters": {"type": "object"}}}],
        stream=True,
        stream_options={"include_usage": True},
    )
    received = list(stream)
    assert not any(item.choices and item.choices[0].delta.tool_calls for item in received)
    usage = [item.usage for item in received if item.usage is not None]
    assert len(usage) == 1 and usage[0].total_tokens == 12


def test_denied_tool_only_stream_accumulates_into_a_valid_message(stack: dict) -> None:
    """OpenAI's stream helper must assemble the denial into one assistant message the agent can reuse."""
    with client(stack).chat.completions.stream(
        model="fixture-model",
        messages=[{"role": "user", "content": "deny silent tool request"}],
        tools=[{"type": "function", "function": {"name": "delete_file", "parameters": {"type": "object"}}}],
    ) as stream:
        message = stream.get_final_completion().choices[0].message
    assert message.role == "assistant" and not message.tool_calls
    assert message.content is not None and message.content.startswith("Watcher did not approve")


def test_bodyless_success_never_reaches_the_client_unevaluated(stack: dict) -> None:
    """A 204 carries nothing Watcher could check, so the gateway refuses it."""
    with pytest.raises(openai.InternalServerError) as refused:
        ask(stack, "no body tool request")
    assert refused.value.status_code == 502
