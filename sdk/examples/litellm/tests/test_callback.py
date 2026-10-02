"""In-process tests of the callback's decisions, stream assembly and encoding.

The proxy tests exercise the same code inside a real LiteLLM process; these
cover edge cases directly and measure coverage. Watcher is an HTTP stub behind
the real SDK client.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import litellm
import openai
import pytest
import yaml
from anthropic.lib.streaming._messages import accumulate_event
from anthropic.types import RawMessageStreamEvent
from fastapi import HTTPException
from litellm.proxy._types import UserAPIKeyAuth
from openai.lib.streaming.chat import ChatCompletionStreamState
from openai.types.chat import ChatCompletionChunk
from pydantic import BaseModel, TypeAdapter
from watcher_litellm.callback import (
    WatcherCallback,
    client_body,
    client_calls,
    route,
    withheld_response,
)
from watcher_litellm.config import main
from watcher_litellm.streams import IncompleteStream, UnsupportedStream, assemble, encode

from watcher_sdk import AsyncWatcherClient
from watcher_sdk._generated.models import HookCallError, PreToolUseHookResponse

USER = UserAPIKeyAuth(user_email="dev@example.com")
RAW_MESSAGE_EVENT: TypeAdapter[Any] = TypeAdapter(RawMessageStreamEvent)


def _outcome(decision: str, call_id: str, explanation: str | None = None) -> dict[str, Any]:
    return {
        "decision": decision,
        "judged_decision": decision if decision != "deferred" else "deny",
        "decision_source": "rule",
        "enforcement_mode": "enforce",
        "tool_use_id": call_id,
        "verdict": {"explanation": explanation},
        "latency_ms": 1.0,
    }


def _payload(*results: tuple[str, list[str | int], dict[str, Any]]) -> list[dict[str, Any]]:
    """Raw-format hook outputs as JSON: each outcome with its call ID (the path is only for readability)."""
    return [{**outcome, "tool_use_id": call_id} for call_id, _, outcome in results]


def _decisions(*results: tuple[str, list[str | int], dict[str, Any]]) -> list[PreToolUseHookResponse | HookCallError]:
    """The same outputs parsed by the SDK, as the callback receives them."""
    return [
        HookCallError.from_dict(item) if "status_code" in item else PreToolUseHookResponse.from_dict(item)
        for item in _payload(*results)
    ]


def _chat_response(*names: str, content: str | None = None) -> dict[str, Any]:
    calls = [
        {"id": f"call_{i}", "type": "function", "function": {"name": name, "arguments": "{}"}}
        for i, name in enumerate(names)
    ]
    return {
        "id": "chatcmpl-1",
        "created": 1,
        "model": "m",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls" if calls else "stop",
                "message": {"role": "assistant", "content": content, **({"tool_calls": calls} if calls else {})},
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _proxy_data(path: str, body: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "model": body.get("model", "m"),
        "proxy_server_request": {"url": f"http://proxy{path}", "body": body, "headers": headers or {}},
    }


class TestRequestHandling:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/v1/chat/completions", "chat_completions"),
            ("/chat/completions/", "chat_completions"),
            ("/openai/deployments/x/chat/completions", "chat_completions"),
            ("/v1/responses", "responses"),
            ("/v1/messages", "messages"),
            ("/v1/embeddings", None),
        ],
    )
    def test_route(self, path: str, expected: str | None) -> None:
        assert route(_proxy_data(path, {})) == expected

    def test_route_without_request_snapshot(self) -> None:
        assert route({}) is None

    def test_client_body_drops_proxy_fields(self) -> None:
        body = {"model": "m", "metadata": {"user_id": "u"}, "litellm_call_id": "x", "litellm_metadata": {}}

        assert client_body("chat_completions", body) == {"model": "m"}
        assert client_body("messages", body) == {"model": "m", "metadata": {"user_id": "u"}}

    @pytest.mark.parametrize(
        ("path", "body"),
        [
            ("/v1/chat/completions", {"n": 2}),
            ("/v1/chat/completions", {"modalities": ["text", "audio"]}),
            ("/v1/chat/completions", {"audio": {"voice": "alloy", "format": "wav"}}),
            ("/v1/responses", {"previous_response_id": "r"}),
            ("/v1/responses", {"conversation": "c"}),
            ("/v1/responses", {"background": True}),
        ],
    )
    async def test_pre_call_refuses_unsupported_options(self, path: str, body: dict[str, Any]) -> None:
        with pytest.raises(HTTPException) as refused:
            await WatcherCallback().async_pre_call_hook(USER, None, _proxy_data(path, body), "completion")
        assert refused.value.status_code == 400

    async def test_pre_call_passes_other_requests(self) -> None:
        data = _proxy_data("/v1/embeddings", {"n": 5})
        assert await WatcherCallback().async_pre_call_hook(USER, None, data, "embedding") is data
        data = _proxy_data("/v1/responses", {"input": "hi"})
        assert await WatcherCallback().async_pre_call_hook(USER, None, data, "responses") is data


class TestWithholding:
    def test_all_released_returns_none(self) -> None:
        decisions = _decisions(("call_0", ["choices", 0, "message", "tool_calls", 0], _outcome("allow", "call_0")))

        assert withheld_response("chat_completions", _chat_response("read"), decisions) is None

    def test_observe_decisions_release(self) -> None:
        decisions = _decisions(("call_0", ["choices", 0, "message", "tool_calls", 0], _outcome("deferred", "call_0")))

        assert withheld_response("chat_completions", _chat_response("rm"), decisions) is None

    def test_one_denial_withholds_every_chat_call_and_keeps_text(self) -> None:
        response = _chat_response(*[f"t{i}" for i in range(12)], content="Plan:")
        decisions = _decisions(
            *[
                (
                    f"call_{i}",
                    ["choices", 0, "message", "tool_calls", i],
                    _outcome("deny" if i == 10 else "allow", f"call_{i}", "Too risky." if i == 10 else None),
                )
                for i in range(12)
            ]
        )

        modified = withheld_response("chat_completions", response, decisions)

        assert modified is not None
        message = modified["choices"][0]["message"]
        assert "tool_calls" not in message
        assert message["content"].startswith("Plan:\n\nWatcher withheld the proposed tool calls")
        assert "- call_10: Too risky." in message["content"]
        assert modified["choices"][0]["finish_reason"] == "stop"
        assert response["choices"][0]["message"]["tool_calls"], "the original must not be mutated"

    def test_escalation_and_errors_are_explained(self) -> None:
        decisions = _decisions(
            ("call_0", ["choices", 0, "message", "tool_calls", 0], _outcome("escalate", "call_0")),
            (
                "call_1",
                ["choices", 0, "message", "tool_calls", 1],
                {"status_code": 503, "detail": "x", "tool_use_id": "call_1"},
            ),
        )

        modified = withheld_response("chat_completions", _chat_response("a", "b"), decisions)

        assert modified is not None
        text = modified["choices"][0]["message"]["content"]
        assert "- call_0: Approval is required." in text
        assert "- call_1: Watcher could not evaluate this call." in text

    def test_selected_chat_candidate_is_edited(self) -> None:
        response = _chat_response("a")
        response["choices"].insert(
            0, {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "x"}}
        )
        decisions = _decisions(("call_0", ["choices", 1, "message", "tool_calls", 0], _outcome("deny", "call_0")))

        modified = withheld_response("chat_completions", response, decisions)

        assert modified is not None
        assert modified["choices"][0]["message"]["content"] == "x"
        assert "withheld the proposed tool call (" in modified["choices"][1]["message"]["content"]

    def test_messages_blocks_are_removed_and_notice_appended(self) -> None:
        response = {
            "id": "msg",
            "content": [
                {"type": "text", "text": "Sure."},
                {"type": "tool_use", "id": "t1", "name": "rm", "input": {}},
                {"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {}},
                {"type": "tool_use", "id": "t2", "name": "ls", "input": {}},
            ],
            "stop_reason": "tool_use",
        }
        decisions = _decisions(
            ("t1", ["content", 1], _outcome("deny", "t1")), ("t2", ["content", 3], _outcome("allow", "t2"))
        )

        modified = withheld_response("messages", response, decisions)

        assert modified is not None
        assert [block["type"] for block in modified["content"]] == ["text", "server_tool_use", "text"]
        assert modified["stop_reason"] == "end_turn"

    def test_a_reused_call_id_withholds_every_call(self) -> None:
        """An allow for the final call must not release an unevaluated pre-fallback call with the same ID."""
        response = {
            "id": "msg",
            "content": [
                {"type": "tool_use", "id": "same", "name": "delete_all_files", "input": {}},
                {"type": "fallback", "from": {"model": "a"}, "to": {"model": "b"}},
                {"type": "tool_use", "id": "same", "name": "read_file", "input": {}},
            ],
            "stop_reason": "tool_use",
        }

        modified = withheld_response(
            "messages", response, _decisions(("same", ["content", 2], _outcome("allow", "same")))
        )

        assert modified is not None
        assert [block["type"] for block in modified["content"]] == ["fallback", "text"]
        assert "could not be matched" in modified["content"][-1]["text"]

    @pytest.mark.parametrize(
        "outputs",
        [
            [("call_0", _outcome("allow", "call_0")), ("call_0", _outcome("deny", "call_0"))],
            [
                ("call_0", _outcome("allow", "call_0")),
                ("call_0", {"status_code": 503, "detail": "x", "tool_use_id": "call_0"}),
            ],
            [("call_0", _outcome("allow", "call_0")), ("elsewhere", _outcome("allow", "elsewhere"))],
        ],
        ids=["duplicate-allow-deny", "duplicate-allow-error", "unknown-id"],
    )
    def test_inconsistent_decisions_withhold_every_call(self, outputs: list[tuple[str, dict[str, Any]]]) -> None:
        path: list[str | int] = ["choices", 0, "message", "tool_calls", 0]
        modified = withheld_response(
            "chat_completions", _chat_response("read"), _decisions(*[(i, path, o) for i, o in outputs])
        )

        assert modified is not None
        assert "tool_calls" not in modified["choices"][0]["message"]

    def test_calls_without_a_decision_are_withheld(self) -> None:
        """A call Watcher returned no decision for, such as one before an Anthropic fallback marker."""
        response = {
            "id": "msg",
            "content": [
                {"type": "tool_use", "id": "t0", "name": "rm", "input": {}},
                {"type": "fallback", "model": "other"},
                {"type": "tool_use", "id": "t2", "name": "ls", "input": {}},
            ],
            "stop_reason": "tool_use",
        }
        decisions = _decisions(("t2", ["content", 2], _outcome("allow", "t2")))

        modified = withheld_response("messages", response, decisions)

        assert modified is not None
        assert [block["type"] for block in modified["content"]] == ["fallback", "text"]
        assert "- t0: Watcher returned no decision for this call." in modified["content"][-1]["text"]

    def test_empty_results_with_client_calls_are_withheld(self) -> None:
        modified = withheld_response("chat_completions", _chat_response("rm"), _decisions())

        assert modified is not None
        assert "tool_calls" not in modified["choices"][0]["message"]

    def test_provider_run_items_do_not_need_decisions(self) -> None:
        response = {"id": "r", "output": [{"type": "web_search_call", "id": "ws"}, {"type": "message", "content": []}]}

        assert withheld_response("responses", response, _decisions()) is None

    def test_responses_client_call_types_are_inventoried(self) -> None:
        response = {
            "output": [
                {"type": "function_call", "call_id": "c1"},
                {"type": "custom_tool_call", "call_id": "c2"},
                {"type": "local_shell_call", "id": "c3"},
                {"type": "mcp_call", "id": "m"},
            ]
        }

        assert [call_id for _, call_id in client_calls("responses", response)] == ["c1", "c2", "c3"]

    def test_legacy_chat_function_call_is_withheld(self) -> None:
        response = _chat_response(content=None)
        response["choices"][0]["message"]["function_call"] = {"name": "rm", "arguments": "{}"}

        modified = withheld_response("chat_completions", response, _decisions())

        assert modified is not None
        assert "function_call" not in modified["choices"][0]["message"]

    def test_responses_items_are_removed_and_message_appended(self) -> None:
        response = {
            "id": "resp_1",
            "output": [
                {"type": "reasoning", "id": "r", "summary": []},
                {"type": "function_call", "call_id": "c1", "name": "rm", "arguments": "{}"},
            ],
        }
        decisions = _decisions(("c1", ["output", 1], _outcome("deny", "c1")))

        modified = withheld_response("responses", response, decisions)

        assert modified is not None
        assert [item["type"] for item in modified["output"]] == ["reasoning", "message"]
        assert modified["output"][1]["id"] == "msg_watcher_resp_1"


def _stub_client(handler: Any) -> Any:
    def factory() -> AsyncWatcherClient:
        transport = httpx.AsyncClient(base_url="http://watcher.test", transport=httpx.MockTransport(handler))
        return AsyncWatcherClient("http://watcher.test", api_key="k", httpx_client=transport)

    return factory


class _SentConversation(BaseModel):
    external_ids: dict[str, str] | None = None


class TestHooks:
    async def test_success_hook_forwards_client_request_and_releases(self) -> None:
        sent: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(json.loads(request.content))
            return httpx.Response(
                200,
                json=_payload(("call_0", ["choices", 0, "message", "tool_calls", 0], _outcome("allow", "call_0"))),
            )

        callback = WatcherCallback(_stub_client(handler))
        data = _proxy_data(
            "/v1/chat/completions",
            {"model": "m", "messages": [], "metadata": {"litellm": True}},
            {"User-Agent": "app/1", "X-Watcher-Session-Id": "s-1"},
        )
        response = litellm.ModelResponse(**_chat_response("read"))

        assert await callback.async_post_call_success_hook(data, USER, response) is response
        (body,) = sent
        assert body["request_body"] == {"model": "m", "messages": []}
        assert (body["url"], body["user_agent"], body["external_ids"], body["user"]) == (
            "/v1/chat/completions",
            "app/1",
            {"other": "litellm:s-1"},
            "dev@example.com",
        )
        assert body["provider"] == "litellm/m"

    @pytest.mark.parametrize("headers", [None, {"X-Watcher-Session-Id": ""}], ids=["absent", "empty"])
    async def test_requests_without_a_session_header_send_no_conversation_id(
        self, headers: dict[str, str] | None
    ) -> None:
        sent: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(json.loads(request.content))
            return httpx.Response(200, json=[])

        callback = WatcherCallback(_stub_client(handler))
        for _ in range(2):
            data = _proxy_data("/v1/chat/completions", {"model": "m", "messages": []}, headers)
            response = litellm.ModelResponse(**_chat_response(content="done"))
            assert await callback.async_post_call_success_hook(data, USER, response) is response

        assert len(sent) == 2
        assert all("external_ids" not in body for body in sent)

    async def test_session_header_that_already_has_the_prefix_is_sent_unchanged(self) -> None:
        sent: list[_SentConversation] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(_SentConversation.model_validate_json(request.content))
            return httpx.Response(200, json=[])

        callback = WatcherCallback(_stub_client(handler))
        headers = {"X-Watcher-Session-Id": "litellm:s-1"}
        data = _proxy_data("/v1/chat/completions", {"model": "m", "messages": []}, headers)
        response = litellm.ModelResponse(**_chat_response(content="done"))
        assert await callback.async_post_call_success_hook(data, USER, response) is response

        (body,) = sent
        assert body.external_ids == {"other": "litellm:s-1"}

    async def test_success_hook_returns_typed_replacement(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_payload(("call_0", ["choices", 0, "message", "tool_calls", 0], _outcome("deny", "call_0"))),
            )

        response = litellm.ModelResponse(**_chat_response("rm"))
        replaced = await WatcherCallback(_stub_client(handler)).async_post_call_success_hook(
            _proxy_data("/v1/chat/completions", {"model": "m"}), USER, response
        )

        assert isinstance(replaced, litellm.ModelResponse)
        assert replaced.to_dict()["choices"][0]["message"].get("tool_calls") is None

    async def test_success_hook_returns_dict_replacement_for_dict_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_payload(("t1", ["content", 0], _outcome("deny", "t1"))))

        response = {
            "id": "m",
            "content": [{"type": "tool_use", "id": "t1", "name": "rm", "input": {}}],
            "stop_reason": "tool_use",
        }
        replaced = await WatcherCallback(_stub_client(handler)).async_post_call_success_hook(
            _proxy_data("/v1/messages", {"model": "m"}), USER, response
        )

        assert replaced["content"][0]["type"] == "text"

    async def test_uncovered_routes_are_untouched(self) -> None:
        response = {"data": []}
        callback = WatcherCallback(_stub_client(lambda request: pytest.fail("Watcher must not be called")))

        assert (
            await callback.async_post_call_success_hook(_proxy_data("/v1/embeddings", {}), USER, response) is response
        )
        chunks = [
            item
            async for item in callback.async_post_call_streaming_iterator_hook(
                USER, _aiter([b"x"]), _proxy_data("/v1/audio", {})
            )
        ]
        assert chunks == [b"x"]

    @pytest.mark.parametrize(
        ("status", "body", "expected"),
        [
            (422, {"detail": [{"loc": ["body"], "msg": "malformed_exchange", "type": "value_error"}]}, 422),
            (422, {"detail": "not the validation shape"}, 422),
            (401, {"detail": "no"}, 422),
            (403, {"detail": "no"}, 422),
            (413, {"detail": "no"}, 422),
            (408, {"detail": "no"}, 503),
            (409, {"detail": "no"}, 503),
            (429, {"detail": "no"}, 503),
            (500, {"detail": "no"}, 503),
        ],
    )
    async def test_watcher_errors_withhold_the_response(self, status: int, body: dict[str, Any], expected: int) -> None:
        """Only a Watcher failure a retry could fix is retryable: clients retry by regenerating the whole response."""
        callback = WatcherCallback(_stub_client(lambda request: httpx.Response(status, json=body)))

        with pytest.raises(HTTPException) as refused:
            await callback.async_post_call_success_hook(
                _proxy_data("/v1/chat/completions", {}), USER, _chat_response("rm")
            )
        assert refused.value.status_code == expected

    async def test_unreachable_watcher_withholds_the_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down")

        with pytest.raises(HTTPException) as refused:
            await WatcherCallback(_stub_client(handler)).async_post_call_success_hook(
                _proxy_data("/v1/chat/completions", {}), USER, _chat_response("rm")
            )
        assert refused.value.status_code == 503

    async def test_default_client_reads_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WATCHER_API_URL", "http://127.0.0.1:9")
        monkeypatch.setenv("WATCHER_API_KEY", "k")

        with pytest.raises(HTTPException) as refused:
            await WatcherCallback(timeout_seconds=2).async_post_call_success_hook(
                _proxy_data("/v1/chat/completions", {}), USER, _chat_response("rm")
            )
        assert refused.value.status_code == 503

    async def test_text_only_stream_is_reencoded_not_replayed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_payload())

        chunks = _messages_stream_bytes(with_tool=False)
        callback = WatcherCallback(_stub_client(handler))
        out = [
            c
            async for c in callback.async_post_call_streaming_iterator_hook(
                USER, _aiter(chunks), _proxy_data("/v1/messages", {})
            )
        ]

        assert out != chunks
        assert assemble("messages", out) == assemble("messages", chunks)

    async def test_stream_with_released_tool_is_reencoded(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_payload(("t", ["content", 2], _outcome("allow", "t"))))

        chunks = _messages_stream_bytes()
        callback = WatcherCallback(_stub_client(handler))
        out = [
            c
            async for c in callback.async_post_call_streaming_iterator_hook(
                USER, _aiter(chunks), _proxy_data("/v1/messages", {})
            )
        ]

        assert out != chunks
        assert assemble("messages", out) == assemble("messages", chunks)

    async def test_stream_with_denied_tool_is_reencoded_without_it(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_payload(("t", ["content", 2], _outcome("deny", "t"))))

        callback = WatcherCallback(_stub_client(handler))
        out = [
            c
            async for c in callback.async_post_call_streaming_iterator_hook(
                USER, _aiter(_messages_stream_bytes()), _proxy_data("/v1/messages", {})
            )
        ]

        blocks = assemble("messages", out)["content"]
        assert "tool_use" not in [block["type"] for block in blocks]
        assert blocks[-1]["text"].startswith("Watcher withheld")

    async def test_responses_stream_is_never_replayed(self) -> None:
        """Events carrying a call absent from the completed body must not reach the client."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_payload())

        completed = {"id": "r", "status": "completed", "output": [{"type": "message", "id": "m", "content": []}]}
        chunks = [
            {"type": "response.created", "response": {**completed, "output": []}},
            {
                "type": "response.output_item.done",
                "item": {"type": "function_call", "call_id": "c", "name": "rm", "arguments": "{}"},
            },
            {"type": "response.completed", "response": completed},
        ]
        out = [
            c
            async for c in WatcherCallback(_stub_client(handler)).async_post_call_streaming_iterator_hook(
                USER, _aiter(chunks), _proxy_data("/v1/responses", {})
            )
        ]

        assert all(isinstance(c, bytes) for c in out)
        assert b"function_call" not in b"".join(out)

    async def test_stream_limits_and_incomplete_streams(self) -> None:
        callback = WatcherCallback(_stub_client(lambda request: pytest.fail("not evaluated")), max_stream_chunks=1)
        with pytest.raises(HTTPException) as too_long:
            _ = [
                c
                async for c in callback.async_post_call_streaming_iterator_hook(
                    USER, _aiter([b"a", b"b"]), _proxy_data("/v1/messages", {})
                )
            ]
        assert too_long.value.status_code == 413

    @pytest.mark.parametrize(
        ("events", "status"),
        [
            # Truncated before message_stop, or a provider error: a retry may succeed.
            ([b'event: message_start\ndata: {"type": "message_start", "message": {"content": []}}\n\n'], 502),
            ([b'event: error\ndata: {"type": "error", "error": {"type": "overloaded_error"}}\n\n'], 502),
            # A shape the example does not interpret: a retry would fail the same way.
            (
                [
                    b'event: message_start\ndata: {"type": "message_start", "message": {"content": []}}\n\n',
                    b'event: content_block_start\ndata: {"type": "content_block_start", "index": 0,'
                    b' "content_block": {"type": "text", "text": ""}}\n\n',
                    b'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0,'
                    b' "delta": {"type": "future_delta"}}\n\n',
                ],
                422,
            ),
            ([b"data: {}\n\n"], 422),
            (["not bytes"], 422),
        ],
        ids=["truncated", "provider-error", "unsupported-delta", "malformed-event", "unexpected-chunk"],
    )
    async def test_stream_failures_are_retryable_only_when_a_retry_could_succeed(
        self, events: list[Any], status: int
    ) -> None:
        with pytest.raises(HTTPException) as refused:
            _ = [
                c
                async for c in WatcherCallback().async_post_call_streaming_iterator_hook(
                    USER, _aiter(events), _proxy_data("/v1/messages", {})
                )
            ]
        assert refused.value.status_code == status


async def _aiter(items: list[Any]) -> AsyncIterator[Any]:
    for item in items:
        yield item


def _messages_stream_bytes(with_tool: bool = True) -> list[bytes]:
    response = {
        "id": "msg",
        "type": "message",
        "role": "assistant",
        "model": "m",
        "content": [
            {"type": "thinking", "thinking": "hmm", "signature": "sig"},
            {"type": "text", "text": "Hello", "citations": None},
            {"type": "tool_use", "id": "t", "name": "ls", "input": {"a": 1}},
            {"type": "redacted_thinking", "data": "xyz"},
        ],
        "stop_reason": "tool_use",
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }
    if not with_tool:
        response["content"] = [block for block in response["content"] if block["type"] != "tool_use"]
        response["stop_reason"] = "end_turn"
    encoded = b"".join(encode("messages", response))
    # Split at arbitrary byte boundaries, as LiteLLM delivers Messages streams.
    return [b'event: ping\ndata: {"type": "ping"}\n\n'] + [encoded[i : i + 37] for i in range(0, len(encoded), 37)]


class TestStreams:
    def test_messages_round_trip_through_encode_and_assemble(self) -> None:
        assembled = assemble("messages", _messages_stream_bytes())

        assert [block["type"] for block in assembled["content"]] == [
            "thinking",
            "text",
            "tool_use",
            "redacted_thinking",
        ]
        assert assembled["content"][0] == {"type": "thinking", "thinking": "hmm", "signature": "sig"}
        assert assembled["content"][2]["input"] == {"a": 1}
        assert assembled["stop_reason"] == "tool_use"
        assert assembled["usage"]["output_tokens"] == 2

    def test_messages_citations_accumulate(self) -> None:
        events = [
            {"type": "message_start", "message": {"id": "m", "content": [], "usage": {}}},
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": "", "citations": None},
            },
            {"type": "content_block_delta", "index": 0, "delta": {"type": "citations_delta", "citation": {"k": 1}}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}},
            {"type": "message_stop"},
        ]
        chunks = [f"data: {json.dumps(e)}\n\n".encode() for e in events]

        assert assemble("messages", chunks)["content"][0]["citations"] == [{"k": 1}]

    @pytest.mark.parametrize(
        ("events", "error"),
        [
            ([], IncompleteStream),
            ([{"type": "message_start", "message": {"content": []}}], IncompleteStream),
            ([{"type": "content_block_start", "index": 0, "content_block": {}}], IncompleteStream),
            ([{"type": "message_start", "message": {"content": []}}, {"type": "error", "error": {}}], IncompleteStream),
            (
                [
                    {"type": "message_start", "message": {"content": []}},
                    {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                    {"type": "content_block_delta", "index": 0, "delta": {"type": "mystery_delta"}},
                ],
                UnsupportedStream,
            ),
            (
                [
                    {"type": "message_start", "message": {"content": []}},
                    {
                        "type": "content_block_start",
                        "index": 0,
                        "content_block": {"type": "tool_use", "id": "t", "name": "rm", "input": {}},
                    },
                    {"type": "content_block_stop", "index": 0},
                    {"type": "message_start", "message": {"content": []}},
                    {"type": "message_stop"},
                ],
                UnsupportedStream,
            ),
            (
                [
                    {"type": "message_start", "message": {"content": []}},
                    {"type": "message_stop"},
                    {
                        "type": "content_block_start",
                        "index": 0,
                        "content_block": {"type": "tool_use", "id": "t", "name": "rm", "input": {}},
                    },
                ],
                UnsupportedStream,
            ),
        ],
    )
    def test_incomplete_or_unsupported_messages_streams_are_refused(
        self, events: list[dict[str, Any]], error: type[Exception]
    ) -> None:
        """Early ends and provider errors are incomplete (retryable); unexpected shapes are unsupported."""
        chunks = [f"data: {json.dumps(e)}\n\n".encode() for e in events]

        with pytest.raises(error):
            assemble("messages", chunks)

    def test_messages_stream_must_be_bytes(self) -> None:
        with pytest.raises(UnsupportedStream):
            assemble("messages", [{"type": "message_start"}])

    def test_responses_use_the_completed_event(self) -> None:
        completed = {"id": "r", "output": [], "status": "completed"}

        assert (
            assemble("responses", [{"type": "response.created"}, {"type": "response.completed", "response": completed}])
            == completed
        )
        with pytest.raises(IncompleteStream):
            assemble("responses", [{"type": "response.created"}])

    def test_responses_incomplete_at_the_output_limit_is_a_finished_response(self) -> None:
        """Like a non-streaming call, a response cut off by its token budget is evaluated, not retried."""
        incomplete = {
            "id": "r",
            "output": [],
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
        }

        assembled = assemble(
            "responses", [{"type": "response.created"}, {"type": "response.incomplete", "response": incomplete}]
        )
        terminal = [
            line for line in b"".join(encode("responses", assembled)).split(b"\n") if line.startswith(b"event:")
        ][-1]

        assert assembled == incomplete
        assert terminal == b"event: response.incomplete"

    def test_chat_needs_a_finish_reason(self) -> None:
        chunk = litellm.ModelResponseStream(id="c", model="m", choices=[{"index": 0, "delta": {"content": "hi"}}])

        with pytest.raises(IncompleteStream):
            assemble("chat_completions", [chunk])

    def test_chat_assembled_by_litellm(self) -> None:
        chunks = [
            litellm.ModelResponseStream(
                id="c", model="m", choices=[{"index": 0, "delta": {"role": "assistant", "content": "hi"}}]
            ),
            litellm.ModelResponseStream(
                id="c", model="m", choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}]
            ),
        ]

        assert assemble("chat_completions", chunks)["choices"][0]["message"]["content"] == "hi"

    def test_chat_builder_failure_is_unsupported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(litellm, "stream_chunk_builder", lambda chunks: None)
        chunk = litellm.ModelResponseStream(
            id="c", model="m", choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}]
        )

        with pytest.raises(UnsupportedStream):
            assemble("chat_completions", [chunk])

    def test_empty_stream(self) -> None:
        with pytest.raises(IncompleteStream):
            assemble("responses", [])

    def test_chat_encoding_carries_calls_reasoning_and_usage(self) -> None:
        response = _chat_response("a", "b", content="x")
        response["choices"][0]["message"]["reasoning_content"] = "why"

        events = [json.loads(chunk.decode().removeprefix("data: ")) for chunk in encode("chat_completions", response)]

        assert events[0]["choices"][0]["delta"] == {"role": "assistant", "content": "x", "reasoning_content": "why"}
        assert [e["choices"][0]["delta"]["tool_calls"][0]["id"] for e in events[1:3]] == ["call_0", "call_1"]
        assert events[-1]["choices"][0]["finish_reason"] == "tool_calls" and events[-1]["usage"]["total_tokens"] == 2

    def test_chat_refusal_and_annotations_survive_assembly_and_encoding(self) -> None:
        annotation = {
            "type": "url_citation",
            "url_citation": {"url": "https://example.com", "title": "t", "start_index": 0, "end_index": 2},
        }
        chunks = [
            litellm.ModelResponseStream(
                id="c", model="m", choices=[{"index": 0, "delta": {"role": "assistant", "refusal": "I can"}}]
            ),
            litellm.ModelResponseStream(id="c", model="m", choices=[{"index": 0, "delta": {"refusal": "not help."}}]),
            litellm.ModelResponseStream(
                id="c", model="m", choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}]
            ),
        ]
        assembled = assemble("chat_completions", chunks)
        assembled["choices"][0]["message"]["annotations"] = [annotation]

        state = ChatCompletionStreamState()
        for chunk in encode("chat_completions", assembled):
            state.handle_chunk(ChatCompletionChunk.model_validate_json(chunk.decode().removeprefix("data: ")))
        message = state.get_final_completion().choices[0].message

        assert message.refusal == "I cannot help."
        assert [a.url_citation.url for a in message.annotations or []] == ["https://example.com"]

    def test_messages_stop_details_survive_the_official_client(self) -> None:
        response = {
            "id": "msg",
            "type": "message",
            "role": "assistant",
            "model": "m",
            "content": [{"type": "text", "text": "No."}],
            "stop_reason": "refusal",
            "stop_sequence": None,
            "stop_details": {"type": "refusal", "category": "cyber", "explanation": "declined"},
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        snapshot = None
        for chunk in encode("messages", response):
            event = RAW_MESSAGE_EVENT.validate_json(chunk.decode().split("data: ", 1)[1])
            snapshot = accumulate_event(event=event, current_snapshot=snapshot)

        assert snapshot is not None and snapshot.stop_reason == "refusal"
        stop_details = snapshot.to_dict()["stop_details"]
        assert isinstance(stop_details, dict)
        assert stop_details["category"] == "cyber"

    def test_responses_encoding_orders_events(self) -> None:
        response = {
            "id": "r",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "id": "m",
                    "content": [{"type": "output_text", "text": "hi"}, {"type": "refusal", "refusal": "no"}],
                },
                {"type": "function_call", "id": "f", "call_id": "c", "name": "n", "arguments": "{}"},
            ],
        }

        events = [json.loads(chunk.decode().split("data: ", 1)[1]) for chunk in encode("responses", response)]

        assert [event["type"] for event in events] == [
            "response.created",
            "response.output_item.added",
            "response.content_part.added",
            "response.output_text.delta",
            "response.output_text.done",
            "response.content_part.done",
            "response.content_part.added",
            "response.content_part.done",
            "response.output_item.done",
            "response.output_item.added",
            "response.output_item.done",
            "response.completed",
        ]
        assert events[1]["item"]["content"] == [] and events[2]["part"]["text"] == ""
        assert [event["sequence_number"] for event in events] == list(range(len(events)))

    def test_responses_encoding_parses_with_the_openai_sdk_without_duplicated_text(self) -> None:
        from openai.lib.streaming.responses._responses import ResponseStreamState
        from openai.types.responses import ResponseStreamEvent

        response = {
            "id": "r",
            "object": "response",
            "created_at": 1,
            "model": "m",
            "status": "completed",
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            "output": [
                {
                    "type": "message",
                    "id": "m",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "Hello", "annotations": []}],
                }
            ],
        }
        adapter: TypeAdapter[Any] = TypeAdapter(ResponseStreamEvent)
        state = ResponseStreamState(input_tools=[], text_format=openai.NOT_GIVEN)
        snapshots = []
        for chunk in encode("responses", response):
            for event in state.handle_event(adapter.validate_json(chunk.decode().split("data: ", 1)[1])):
                if event.type == "response.output_text.delta":
                    snapshots.append(event.snapshot)

        assert snapshots == ["Hello"]


class TestPackaging:
    def test_config_command_prints_the_callback_configuration(self, capsys: pytest.CaptureFixture[str]) -> None:
        main()

        config = yaml.safe_load(capsys.readouterr().out)
        assert config["litellm_settings"]["callbacks"] == "watcher_litellm.callback.watcher_callback"
        assert config["model_list"][0]["litellm_params"]["api_key"] == "os.environ/PROVIDER_API_KEY"
