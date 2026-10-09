"""End-to-end behavior of the packaged callback inside a running LiteLLM proxy.

Clients are the official OpenAI and Anthropic SDKs, so synthesized streams are
checked by the same parsers real applications use. Each case runs for Chat
Completions, Responses and Anthropic Messages, streamed and not.
"""

import time
from typing import Any, cast

import anthropic
import httpx
import openai
import pytest
from openai.types.chat import ChatCompletionFunctionToolParam, ChatCompletionMessageParam
from openai.types.chat.completion_create_params import CompletionCreateParamsBase
from openai.types.responses import FunctionToolParam, ResponseFunctionToolCall
from openai.types.responses.response_create_params import ResponseCreateParamsBase
from servers import ProviderState, WatcherState

pytestmark = pytest.mark.usefixtures("reset_states")

APIS = ["chat_completions", "responses", "messages"]
SESSION_HEADERS = {"x-watcher-session-id": "fixture-session"}
TOOLS: list[ChatCompletionFunctionToolParam] = [
    {"type": "function", "function": {"name": name, "parameters": {"type": "object"}}} for name in ("read_file", "rm")
]


def _await_requests(state: WatcherState, count: int) -> None:
    """Require asynchronous tail recording before a test resets the shared HTTP peer."""
    deadline = time.monotonic() + 5
    while len(state.requests) < count and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(state.requests) == count


def _failed_stream_calls(proxy_url: str, api: str, message: str, *, default_retries: bool) -> list[str]:
    """Read official SDK events through a terminal error and return already delivered IDs.

    Responses exposes an ``error`` event instead of raising an API exception;
    consuming that event gives the diagnostic which ``get_final_response``
    otherwise replaces with a generic missing-completed-response exception.
    """
    options: dict[str, Any] = {} if default_retries else {"max_retries": 0}
    user_message: Any = [{"role": "user", "content": "Clean up."}]
    if api == "messages":
        client: Any = anthropic.Anthropic(
            base_url=proxy_url, api_key="sk-proxy", default_headers=SESSION_HEADERS, **options
        )
        stream = client.messages.create(model="claude-test", max_tokens=100, messages=user_message, stream=True)
    else:
        client = openai.OpenAI(
            base_url=f"{proxy_url}/v1", api_key="sk-proxy", default_headers=SESSION_HEADERS, **options
        )
        stream = (
            client.responses.create(model="gpt-test", input="Clean up.", stream=True)
            if api == "responses"
            else client.chat.completions.create(model="gpt-test", messages=user_message, stream=True)
        )
    events: list[dict[str, Any]] = []
    failure: str | None = None
    try:
        with stream:
            for event in stream:
                events.append(event.model_dump())
    except (openai.APIError, anthropic.APIError) as error:
        failure = str(error)
    finally:
        client.close()
    if api == "responses":
        assert events[-1]["type"] == "error"
        failure = events[-1]["message"]
    assert failure is not None
    assert message in failure
    if api == "messages":
        return [
            event["content_block"]["id"]
            for event in events
            if event["type"] == "content_block_start" and event["content_block"]["type"] == "tool_use"
        ]
    if api == "responses":
        return [
            event["item"]["call_id"]
            for event in events
            if event["type"] == "response.output_item.added" and event["item"]["type"] == "function_call"
        ]
    return [
        call["id"]
        for event in events
        for choice in event["choices"]
        for call in choice["delta"].get("tool_calls") or []
        if call.get("id")
    ]


def _call(proxy_url: str, api: str, stream: bool, **headers: str) -> tuple[str, list[tuple[str, str]]]:
    """Send one request through the proxy; return the reply text and its (tool name, call id) pairs."""
    headers = {**SESSION_HEADERS, **headers}
    if api == "messages":
        client = anthropic.Anthropic(base_url=proxy_url, api_key="sk-proxy", default_headers=headers, max_retries=0)
        kwargs: dict[str, Any] = {
            "model": "claude-test",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Clean up."}],
            "tools": [{"name": t["function"]["name"], "input_schema": {"type": "object"}} for t in TOOLS],
        }
        if stream:
            with client.messages.stream(**kwargs) as events:
                message = events.get_final_message()
        else:
            message = client.messages.create(**kwargs)
        text = "".join(block.text for block in message.content if block.type == "text")
        return text, [(block.name, block.id) for block in message.content if block.type == "tool_use"]
    client = openai.OpenAI(base_url=f"{proxy_url}/v1", api_key="sk-proxy", default_headers=headers, max_retries=0)
    if api == "responses":
        # Keep strict omitted in the request; the SDK's tool stub requires it.
        response_kwargs: ResponseCreateParamsBase = {
            "model": "gpt-test",
            "input": "Clean up.",
            "tools": [
                cast(
                    FunctionToolParam,
                    {"type": "function", "name": t["function"]["name"], "parameters": {"type": "object"}},
                )
                for t in TOOLS
            ],
        }
        if stream:
            with client.responses.stream(**response_kwargs) as events:
                response = events.get_final_response()
        else:
            response = client.responses.create(**response_kwargs)
        calls = [
            (cast(ResponseFunctionToolCall, item).name, cast(ResponseFunctionToolCall, item).call_id)
            for item in response.output
            if item.type == "function_call"
        ]
        return response.output_text, calls
    chat_kwargs: CompletionCreateParamsBase = {
        "model": "gpt-test",
        "messages": [{"role": "user", "content": "Clean up."}],
        "tools": TOOLS,
    }
    if stream:
        with client.chat.completions.stream(**chat_kwargs) as events:
            completion = events.get_final_completion()
    else:
        completion = client.chat.completions.create(**chat_kwargs)
    message = completion.choices[0].message
    chat_calls: list[tuple[str, str]] = []
    for call in message.tool_calls or []:
        assert call.type == "function", "The fixture only declares function tools"
        chat_calls.append((call.function.name, call.id))
    return message.content or "", chat_calls


@pytest.mark.parametrize("stream", [False, True], ids=["json", "stream"])
@pytest.mark.parametrize("api", APIS)
class TestProxy:
    def test_allowed_tool_calls_are_released_unchanged(
        self, proxy_url: str, provider_state: ProviderState, watcher_state: WatcherState, api: str, stream: bool
    ) -> None:
        provider_state.tools = ["read_file", "read_file"]

        text, calls = _call(proxy_url, api, stream)

        assert [name for name, _ in calls] == ["read_file", "read_file"]
        assert len({call_id for _, call_id in calls}) == 2
        assert "withheld" not in text
        _await_requests(watcher_state, 3 if stream else 1)
        for sent in watcher_state.requests:
            assert "litellm_call_id" not in sent["request_body"]
            assert "litellm_metadata" not in sent["request_body"]
            assert sent["request_body"]["model"] in ("gpt-test", "claude-test")
            assert ("input" if api == "responses" else "messages") in sent["request_body"]

    def test_denial_withholds_unreleased_calls(
        self, proxy_url: str, provider_state: ProviderState, watcher_state: WatcherState, api: str, stream: bool
    ) -> None:
        provider_state.tools = ["read_file", "rm"]
        watcher_state.deny = {"rm"}

        text, calls = _call(proxy_url, api, stream)

        expected = [("read_file", "toolu_0" if api == "messages" else "call_0")] if stream else []
        assert calls == expected
        assert "Watcher did not approve" in text
        assert "rm is not allowed here." in text
        assert len(provider_state.requests) == 3
        _await_requests(watcher_state, 3 if stream else 2)

    def test_text_replies_are_recorded_and_released(
        self, proxy_url: str, provider_state: ProviderState, watcher_state: WatcherState, api: str, stream: bool
    ) -> None:
        text, calls = _call(proxy_url, api, stream)

        assert (text.strip(), calls) == ("Hello from the provider.", [])
        _await_requests(watcher_state, 1)

    def test_observe_mode_releases_denied_calls(
        self, proxy_url: str, provider_state: ProviderState, watcher_state: WatcherState, api: str, stream: bool
    ) -> None:
        provider_state.tools = ["rm"]
        watcher_state.deny = {"rm"}
        watcher_state.mode = "observe"

        _, calls = _call(proxy_url, api, stream)

        assert [name for name, _ in calls] == ["rm"]
        _await_requests(watcher_state, 2 if stream else 1)

    def test_a_call_watcher_could_not_evaluate_is_withheld(
        self, proxy_url: str, provider_state: ProviderState, watcher_state: WatcherState, api: str, stream: bool
    ) -> None:
        provider_state.tools = ["read_file"]
        watcher_state.call_error = True

        if stream:
            assert _failed_stream_calls(proxy_url, api, "Watcher could not evaluate", default_retries=False) == []
            assert len(provider_state.requests) == 1
            return
        with pytest.raises((openai.APIStatusError, anthropic.APIStatusError)) as failed:
            _call(proxy_url, api, stream)
        assert failed.value.status_code == 503
        assert len(provider_state.requests) == 1

    def test_watcher_outage_fails_closed(
        self, proxy_url: str, provider_state: ProviderState, watcher_state: WatcherState, api: str, stream: bool
    ) -> None:
        provider_state.tools = ["read_file"]
        watcher_state.fail_status = 503

        if stream:
            assert (
                _failed_stream_calls(proxy_url, api, "Watcher could not evaluate this response", default_retries=False)
                == []
            )
            return
        with pytest.raises((openai.APIError, anthropic.APIError)):
            _call(proxy_url, api, stream)


def _default_retry_call(proxy_url: str, api: str, stream: bool) -> list[str]:
    """One request through the proxy with the official client's default retries; return delivered tool names."""
    messages: list[anthropic.types.MessageParam] = [{"role": "user", "content": "Clean up."}]
    if api == "messages":
        client = anthropic.Anthropic(base_url=proxy_url, api_key="sk-proxy", default_headers=SESSION_HEADERS)
        tools: list[Any] = [{"name": "read_file", "input_schema": {"type": "object"}}]
        if stream:
            with client.messages.stream(model="claude-test", max_tokens=100, messages=messages, tools=tools) as s:
                message = s.get_final_message()
        else:
            message = client.messages.create(model="claude-test", max_tokens=100, messages=messages, tools=tools)
        return [block.name for block in message.content if block.type == "tool_use"]
    openai_client = openai.OpenAI(base_url=f"{proxy_url}/v1", api_key="sk-proxy", default_headers=SESSION_HEADERS)
    if api == "responses":
        response_kwargs: ResponseCreateParamsBase = {"model": "gpt-test", "input": "Clean up."}
        if stream:
            with openai_client.responses.stream(**response_kwargs) as events:
                response = events.get_final_response()
        else:
            response = openai_client.responses.create(**response_kwargs)
        return [cast(ResponseFunctionToolCall, item).name for item in response.output if item.type == "function_call"]
    chat_kwargs: CompletionCreateParamsBase = {
        "model": "gpt-test",
        "messages": cast(list[ChatCompletionMessageParam], messages),
    }
    if stream:
        with openai_client.chat.completions.stream(**chat_kwargs) as events:
            completion = events.get_final_completion()
    else:
        completion = openai_client.chat.completions.create(**chat_kwargs)
    names = []
    for call in completion.choices[0].message.tool_calls or []:
        assert call.type == "function", "The fixture only declares function tools"
        names.append(call.function.name)
    return names


@pytest.mark.parametrize("watcher_status", [401, 403, 413, 422])
@pytest.mark.parametrize(
    ("api", "stream"),
    [(api, stream) for api in APIS for stream in (False, True)],
)
def test_permanent_watcher_errors_are_not_retried_by_clients(
    proxy_url: str,
    provider_state: ProviderState,
    watcher_state: WatcherState,
    api: str,
    stream: bool,
    watcher_status: int,
) -> None:
    """With their default retries, official clients call once: a retry would regenerate the response for nothing."""
    provider_state.tools = ["read_file"]
    watcher_state.fail_status = watcher_status

    if stream:
        assert (
            _failed_stream_calls(proxy_url, api, "Watcher could not evaluate this response", default_retries=True) == []
        )
    else:
        with pytest.raises((openai.APIStatusError, anthropic.APIStatusError)) as refused:
            _default_retry_call(proxy_url, api, stream)
        assert refused.value.status_code == 422
    assert len(provider_state.requests) == 1
    assert len(watcher_state.requests) == 1


@pytest.mark.parametrize("reason", ["max_output_tokens", "content_filter"])
@pytest.mark.parametrize(("tool", "released"), [("read_file", True), ("rm", False)])
def test_incomplete_responses_stream_is_delivered_once(
    proxy_url: str, provider_state: ProviderState, watcher_state: WatcherState, reason: str, tool: str, released: bool
) -> None:
    """Allowed calls retain incomplete status; denied alternatives end with a normal notice."""
    provider_state.tools = [tool]
    provider_state.responses_incomplete = reason
    watcher_state.deny = {"rm"}
    client = openai.OpenAI(base_url=f"{proxy_url}/v1", api_key="sk-proxy", default_headers=SESSION_HEADERS)

    events = list(client.responses.create(model="gpt-test", input="Clean up.", stream=True))

    final = events[-1]
    if not released:
        assert final.type == "response.completed" or final.type == "response.incomplete"
        assert not any(item.type == "function_call" for item in final.response.output)
        assert "rm is not allowed here." in final.response.output_text
        assert len(provider_state.requests) == 3
        _await_requests(watcher_state, 2)
        return
    assert final.type == "response.incomplete"
    assert final.response.incomplete_details is not None
    assert final.response.incomplete_details.reason == reason
    delivered = {
        event.item.type
        for event in events
        if event.type == "response.output_item.added" or event.type == "response.output_item.done"
    } | {item.type for item in final.response.output}
    assert ("function_call" in delivered) is released
    assert len(provider_state.requests) == 1
    _await_requests(watcher_state, 2)


def test_a_provider_error_before_the_stream_starts_is_retried_and_only_the_complete_one_evaluated(
    proxy_url: str, provider_state: ProviderState, watcher_state: WatcherState
) -> None:
    """The failed attempt never reaches the client."""
    provider_state.tools = ["read_file"]
    provider_state.stream_faults = ["error"]

    delivered = _default_retry_call(proxy_url, "messages", stream=True)

    assert delivered == ["read_file"]
    assert len(provider_state.requests) == 2
    _await_requests(watcher_state, 2)


def test_a_truncated_provider_stream_errors_after_releasing_only_evaluated_calls(
    proxy_url: str, provider_state: ProviderState, watcher_state: WatcherState
) -> None:
    provider_state.tools = ["read_file"]
    provider_state.stream_faults = ["truncate"]

    assert _failed_stream_calls(
        proxy_url, "messages", "Model response stream was incomplete", default_retries=True
    ) == ["toolu_0"]
    assert len(watcher_state.requests) == 1


@pytest.mark.parametrize("api", APIS)
def test_session_header_and_user_agent_reach_watcher(proxy_url: str, watcher_state: WatcherState, api: str) -> None:
    _call(proxy_url, api, False, **{"x-watcher-session-id": "conversation-7", "user-agent": "my-agent/2.0"})

    (sent,) = watcher_state.requests
    assert sent["external_ids"] == {"other": "litellm:conversation-7"}
    assert sent["user_agent"] == "my-agent/2.0"
    assert sent["url"].endswith(
        {"chat_completions": "/chat/completions", "responses": "/responses", "messages": "/messages"}[api]
    )
    assert sent["provider"].startswith("litellm/")


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("stream", [False, True])
def test_requests_without_identity_are_refused_before_the_provider_runs(
    proxy_url: str, provider_state: ProviderState, watcher_state: WatcherState, api: str, stream: bool
) -> None:
    path = {"chat_completions": "chat/completions", "messages": "messages", "responses": "responses"}[api]
    body: dict[str, Any] = {"model": "claude-test" if api == "messages" else "gpt-test", "stream": stream}
    if api == "responses":
        body["input"] = "Clean up."
    else:
        body["messages"] = [{"role": "user", "content": "Clean up."}]
    if api == "messages":
        body["max_tokens"] = 100
    response = httpx.post(f"{proxy_url}/v1/{path}", headers={"authorization": "Bearer sk-proxy"}, json=body)
    assert response.status_code == 400
    assert provider_state.requests == []
    assert watcher_state.requests == []


def test_multiple_choices_are_refused_before_the_provider_runs(proxy_url: str, provider_state: ProviderState) -> None:
    response = httpx.post(
        f"{proxy_url}/v1/chat/completions",
        headers={"authorization": "Bearer sk-proxy", **SESSION_HEADERS},
        json={"model": "gpt-test", "n": 2, "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 400
    assert provider_state.requests == []


def test_server_stored_responses_history_is_refused(proxy_url: str, provider_state: ProviderState) -> None:
    response = httpx.post(
        f"{proxy_url}/v1/responses",
        headers={"authorization": "Bearer sk-proxy", **SESSION_HEADERS},
        json={"model": "gpt-test", "input": "hi", "previous_response_id": "resp_earlier"},
    )

    assert response.status_code == 400
    assert provider_state.requests == []


def test_client_metadata_is_forwarded_except_litellms_chat_slot(proxy_url: str, watcher_state: WatcherState) -> None:
    """Messages metadata carries Claude Code's session; Chat's metadata slot belongs to LiteLLM."""
    for path, body in (
        ("/v1/messages", {"model": "claude-test", "max_tokens": 10, "metadata": {"user_id": "u"}}),
        ("/v1/chat/completions", {"model": "gpt-test", "metadata": {"user_id": "u"}}),
    ):
        httpx.post(
            f"{proxy_url}{path}",
            headers={"authorization": "Bearer sk-proxy", **SESSION_HEADERS},
            json={**body, "messages": [{"role": "user", "content": "hi"}]},
        ).raise_for_status()

    messages_body, chat_body = (request["request_body"] for request in watcher_state.requests)
    assert messages_body["metadata"] == {"user_id": "u"}
    assert "metadata" not in chat_body
