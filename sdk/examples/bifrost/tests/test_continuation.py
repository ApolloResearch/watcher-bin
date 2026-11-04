"""Denial continuation: notices, alternatives through the gateway, final generation and failures.

Each test drives ``respond`` (the bridge's ``/evaluate`` logic) with a scripted
provider behind a mock of Bifrost's listener and a scripted Watcher behind the
public SDK, and counts the calls each one receives.
"""

import asyncio
import base64
import json
import time
from collections.abc import Callable, Sequence
from typing import Any

import httpx
import pytest
import structlog.testing
from watcher_bifrost.alternatives import ALTERNATIVE_HEADER, Gateway, MarkerLedger, marker_key
from watcher_bifrost.bridge import (
    FORWARDED_HEADERS,
    MAX_BODY,
    Delivery,
    UnsupportedExchange,
    alternative_headers,
    record_delivery,
    respond,
    validate,
)
from watcher_bifrost.replan import (
    _ASK_APPROVAL,
    _ASK_FIXED,
    _CONTINUE,
    _STOP_AFTER_CAP,
    ALTERNATIVE_FAILED,
)
from watcher_bifrost.system_notice import SYSTEM_NOTICE, with_system_notice

from watcher_sdk import AsyncWatcherClient, WatcherAPIError

KEY = marker_key("fixture-key")
PARAGRAPH = "\n\n"
WRITE = {"name": "Write", "arguments": '{"file_path":"a.txt","content":"x"}'}
READ = {"name": "Read", "arguments": '{"file_path":"a.txt"}'}


def completion(content: str | None, calls: Sequence[tuple[str, dict]] = (), finish: str | None = None) -> dict:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = [{"id": i, "type": "function", "function": dict(f)} for i, f in calls]
    return {
        "id": "completion-original",
        "object": "chat.completion",
        "created": 7,
        "model": "fixture",
        "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        "choices": [{"index": 0, "message": message, "finish_reason": finish or ("tool_calls" if calls else "stop")}],
    }


def client_request(**extra: Any) -> dict:
    request = {
        "model": "fixture",
        "messages": [{"role": "system", "content": "Be careful."}, {"role": "user", "content": "do it"}],
        "tools": [
            {"type": "function", "function": {"name": "Write"}},
            {"type": "function", "function": {"name": "Read"}},
        ],
        **extra,
    }
    noticed = with_system_notice(request)
    assert noticed is not None
    return noticed


def outcome(call_id: str, decision: str, source: str = "rule", reason: str = "Fixture reason") -> dict:
    value = {
        "tool_use_id": call_id,
        "decision": decision,
        "judged_decision": decision,
        "decision_source": source,
        "enforcement_mode": "enforce",
        "verdict": {"explanation": reason},
        "latency_ms": 1,
    }
    if source == "grading_error":
        value["grading_error"] = {"code": "timeout", "message": "Grader timed out"}
    return value


class Harness:
    """A scripted provider behind a mock gateway listener and a scripted Watcher."""

    def __init__(self, provider: Callable[[dict], Any], watcher: Callable[[dict], Any]) -> None:
        self.provider = provider
        self.watcher = watcher
        self.provider_requests: list[dict] = []
        self.provider_headers: list[httpx.Headers] = []
        self.watcher_requests: list[dict] = []
        self.verifier = MarkerLedger(KEY)
        self.delivery: Delivery | None = None

    async def _gateway(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        self.provider_headers.append(request.headers)
        # The nested pass verifies the marker against the exact bytes, once.
        assert self.verifier.accept(request.headers[ALTERNATIVE_HEADER], body)
        assert request.url.path == "/openai/v1/chat/completions"
        payload = json.loads(body)
        self.provider_requests.append(payload)
        result = self.provider(payload)
        if asyncio.iscoroutine(result):
            result = await result
        return result if isinstance(result, httpx.Response) else httpx.Response(200, json=result)

    def _watcher(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.watcher_requests.append(body)
        result = self.watcher(body)
        return result if isinstance(result, httpx.Response) else httpx.Response(200, json=result)

    async def run(
        self,
        request: dict,
        response: dict,
        *,
        timeout: float = 30,
        credentials: dict[str, str] | None = None,
        forwarded: frozenset[str] = FORWARDED_HEADERS,
        max_body: int = MAX_BODY,
    ) -> dict:
        """Answer one ``/evaluate`` envelope and keep its ``Delivery`` (None unless replaced) in ``self.delivery``."""
        envelope = {
            "request": request,
            "response": response,
            "metadata": {
                "watcher_conversation_id": "bifrost:parent",
                "watcher_url": "/openai/v1/chat/completions",
                "watcher_provider": "openai",
                "watcher_user_agent": "fixture/1",
            },
            "credentials": credentials if credentials is not None else {"Authorization": "Bearer client-key"},
        }
        async with (
            AsyncWatcherClient(
                "http://watcher.invalid",
                httpx_client=httpx.AsyncClient(
                    base_url="http://watcher.invalid", transport=httpx.MockTransport(self._watcher)
                ),
            ) as watcher,
            httpx.AsyncClient(
                base_url="http://gateway.invalid", transport=httpx.MockTransport(self._gateway)
            ) as client,
        ):
            gateway = Gateway(client=client, ledger=MarkerLedger(KEY), max_body=max_body)
            deadline = asyncio.get_running_loop().time() + timeout
            reply, self.delivery = await respond(
                watcher, gateway, envelope, allow_stream=True, deadline=deadline, forwarded=forwarded
            )
            return reply

    async def record(self) -> dict:
        """Record ``self.delivery`` as the bridge does after replying; return the last Watcher request it sent."""
        assert self.delivery is not None
        sent = len(self.watcher_requests)
        async with AsyncWatcherClient(
            "http://watcher.invalid",
            httpx_client=httpx.AsyncClient(
                base_url="http://watcher.invalid", transport=httpx.MockTransport(self._watcher)
            ),
        ) as watcher:
            await record_delivery(watcher, self.delivery)
        assert len(self.watcher_requests) > sent
        return self.watcher_requests[-1]


def calls_in(body: dict) -> list[dict]:
    return body["response_body"]["choices"][0]["message"].get("tool_calls") or []


def deny_ids(*denied: str, decision: str = "deny", source: str = "rule") -> Callable[[dict], list]:
    """Refuse the named call IDs and allow every other call."""
    return lambda body: [
        outcome(call["id"], decision if call["id"] in denied else "allow", source) for call in calls_in(body)
    ]


def tool_messages(request: dict) -> list[dict]:
    return [message for message in request["messages"] if message["role"] == "tool"]


async def test_denial_then_allowed_alternative_is_delivered_with_notices():
    forced = {"type": "function", "function": {"name": "Write"}}
    request = client_request(tool_choice=forced, parallel_tool_calls=False, stream=True, stream_options={"x": 1})
    original = completion("I will write.", [("call-1", WRITE)])
    harness = Harness(lambda _: completion("Reading instead.", [("call-2", READ)]), deny_ids("call-1"))
    reply = await harness.run(request, original)

    assert reply["action"] == "replace"
    delivered = reply["response"]
    message = delivered["choices"][0]["message"]
    assert message["tool_calls"] == [{"id": "call-2", "type": "function", "function": READ}]
    assert delivered["choices"][0]["finish_reason"] == "tool_calls"
    assert {key: delivered[key] for key in ("id", "created", "model", "usage")} == {
        key: original[key] for key in ("id", "created", "model", "usage")
    }
    parts = message["content"].split("\n\n")
    assert parts[0] == "I will write."
    assert parts[1].startswith(
        "WATCHER NOTICE (added by Watcher, not written by the assistant): Watcher blocked `Write"
    )
    assert "Reason: Fixture reason. The call did not run." in parts[1]
    assert parts[2] == "Reading instead."

    (continuation,) = harness.provider_requests
    assert continuation["tool_choice"] == forced and continuation["parallel_tool_calls"] is False
    assert continuation["stream"] is False and "stream_options" not in continuation
    assert continuation["messages"][:-2] == request["messages"]
    assert continuation["messages"][-2] == original["choices"][0]["message"]
    (result,) = tool_messages(continuation)
    assert result["tool_call_id"] == "call-1" and result["content"].endswith(_CONTINUE)
    assert harness.provider_headers[0]["authorization"] == "Bearer client-key"

    assert len(harness.watcher_requests) == 2
    first, second = harness.watcher_requests
    assert first["request_body"] == request and first["external_ids"] == {"other": "bifrost:parent"}
    # The alternative is graded in the client's own session, so Watcher already
    # holds the refused call's decision when it reads the synthetic result.
    assert second["request_body"] == continuation and second["external_ids"] == {"other": "bifrost:parent"}
    assert second["user_agent"] == "fixture/1"
    assert first["withholds_refused_calls"] is True and second["withholds_refused_calls"] is True
    assert "withheld_tool_use_ids" not in first and "withheld_tool_use_ids" not in second


@pytest.mark.parametrize("tools", [True, False])
async def test_repeated_denials_stop_after_three_proposals_with_one_final_text_generation(tools):
    request = client_request()
    if not tools:
        del request["tools"]
    counter = iter(range(100))

    def provider(body: dict) -> dict:
        # Without tools there is no tool choice to set; the stop instruction marks the final generation.
        if body.get("tool_choice") == "none" or tool_messages(body)[-1]["content"].endswith(_STOP_AFTER_CAP):
            return completion("Several approaches were blocked. A. skip B. something else?")
        index = next(counter)
        call = {"name": "Write", "arguments": json.dumps({"file_path": f"{index}.txt"})}
        return completion(None, [(f"alt-{index}", call)])

    harness = Harness(provider, lambda body: [outcome(call["id"], "deny") for call in calls_in(body)])
    reply = await harness.run(request, completion(None, [("call-1", WRITE)]))

    # The client's proposal plus three gateway generations: two alternatives and the final text.
    assert len(harness.provider_requests) == 3
    assert len(harness.watcher_requests) == 3
    final = harness.provider_requests[-1]
    if tools:
        assert [body.get("tool_choice") for body in harness.provider_requests] == [None, None, "none"]
    else:
        assert all("tool_choice" not in body for body in harness.provider_requests)
    assert tool_messages(final)[-1]["content"].endswith(_STOP_AFTER_CAP)
    message = reply["response"]["choices"][0]["message"]
    assert "tool_calls" not in message and reply["response"]["choices"][0]["finish_reason"] == "stop"
    assert message["content"].count("WATCHER NOTICE") == 3
    assert message["content"].endswith("A. skip B. something else?")


@pytest.mark.parametrize(
    "source,can_approve",
    [("policy_gateway", True), ("triage", True), ("rule", False), ("threshold", False), ("grading_error", False)],
)
async def test_escalation_goes_straight_to_the_final_generation(source, can_approve):
    request = client_request()
    harness = Harness(
        lambda _: completion("Should I proceed? A. allow B. skip C. other"),
        deny_ids("call-1", decision="escalate", source=source),
    )
    reply = await harness.run(request, completion(None, [("call-1", WRITE)]))

    assert len(harness.provider_requests) == 1 and len(harness.watcher_requests) == 1
    (final,) = harness.provider_requests
    assert final["tool_choice"] == "none"
    (result,) = tool_messages(final)
    content = reply["response"]["choices"][0]["message"]["content"]
    assert content.startswith("WATCHER ESCALATION (added by Watcher, not written by the assistant): ")
    if can_approve:
        assert result["content"].endswith(_ASK_APPROVAL)
        assert "needs the user's decision before it can run" in content
    else:
        assert result["content"].endswith(_ASK_FIXED)
        assert "A. skip it, B. do something else, C. ask an administrator" in result["content"]
        assert "allow this call" not in result["content"]
        assert "cannot be approved in this conversation" in content
    assert "tool_calls" not in reply["response"]["choices"][0]["message"]


async def test_escalation_without_tools_leaves_tool_choice_absent():
    request = client_request()
    del request["tools"]
    harness = Harness(
        lambda _: completion("Allow it? A. yes B. no"), deny_ids("call-1", decision="escalate", source="triage")
    )
    await harness.run(request, completion(None, [("call-1", WRITE)]))
    assert "tool_choice" not in harness.provider_requests[0]


@pytest.mark.parametrize("source,allow_offered", [("policy_gateway", True), ("rule", False)])
async def test_final_generation_calls_are_withheld_without_grading(source, allow_offered):
    harness = Harness(
        lambda _: completion("Trying anyway.", [("call-final", READ)]),
        deny_ids("call-1", decision="escalate", source=source),
    )
    reply = await harness.run(client_request(), completion(None, [("call-1", WRITE)]))

    assert len(harness.watcher_requests) == 1, "Watcher must not see the final generation's calls"
    choice = reply["response"]["choices"][0]
    assert "tool_calls" not in choice["message"] and choice["finish_reason"] == "stop"
    assert "call-final" not in json.dumps(reply)
    content = choice["message"]["content"]
    assert "Trying anyway." in content
    assert content.split("\n\n")[-1].startswith(
        "WATCHER ESCALATION (added by Watcher, not written by the assistant): Watcher withheld further tool calls"
    )
    assert ("Reply A to allow the escalated call" in content) is allow_offered


async def test_repeated_refused_operation_under_new_id_is_refused_without_grading():
    replies = iter(
        [
            completion(None, [("call-renamed", WRITE)]),
            completion("Read it.", [("call-read", READ)]),
        ]
    )
    harness = Harness(lambda _: next(replies), deny_ids("call-1"))
    reply = await harness.run(client_request(), completion(None, [("call-1", WRITE)]))

    assert len(harness.provider_requests) == 2
    graded = [call["id"] for body in harness.watcher_requests for call in calls_in(body)]
    assert graded == ["call-1", "call-read"]
    message = reply["response"]["choices"][0]["message"]
    assert message["tool_calls"][0]["id"] == "call-read"
    assert message["content"].count("Reason: Fixture reason. The call did not run.") == 2
    assert tool_messages(harness.provider_requests[1])[-1]["tool_call_id"] == "call-renamed"
    # Watcher never evaluated the repeat, so its turn is left out of the history it grades.
    graded_history = harness.watcher_requests[1]["request_body"]["messages"]
    assert graded_history == harness.provider_requests[0]["messages"]
    assert not any(message.get("tool_call_id") == "call-renamed" for message in graded_history)


async def test_mixed_siblings_withhold_both_calls_with_a_sibling_line():
    original = completion(None, [("call-write", WRITE), ("call-read", READ)])
    harness = Harness(lambda _: completion("Done another way."), deny_ids("call-write"))
    reply = await harness.run(client_request(), original)

    message = reply["response"]["choices"][0]["message"]
    assert "tool_calls" not in message
    lines = message["content"].split("\n\n")
    assert "Watcher blocked `Write" in lines[0]
    assert lines[1] == (
        'WATCHER NOTICE (added by Watcher, not written by the assistant): `Read {"file_path": "a.txt"}` '
        "did not run because Watcher refused another call in the same response."
    )
    results = {message["tool_call_id"]: message["content"] for message in tool_messages(harness.provider_requests[0])}
    assert results["call-read"] == "This call did not run because Watcher refused another call in the same response."
    assert results["call-write"].startswith("WATCHER NOTICE: Watcher blocked this call.")


async def test_observe_mode_releases_without_notice():
    def watcher(body: dict) -> list:
        return [
            {**outcome(call["id"], "deferred"), "enforcement_mode": "observe", "judged_decision": "deny"}
            for call in calls_in(body)
        ]

    harness = Harness(lambda _: pytest.fail("no alternative in observe mode"), watcher)
    assert await harness.run(client_request(), completion(None, [("call-1", WRITE)])) == {"action": "release"}


async def test_unmatched_original_decision_withholds():
    harness = Harness(lambda _: pytest.fail("no alternative"), lambda _: [outcome("other", "deny")])
    assert await harness.run(client_request(), completion(None, [("call-1", WRITE)])) == {"action": "withhold"}


async def test_deadline_exhaustion_delivers_notice_and_fixed_sentence():
    async def slow(_: dict) -> dict:
        await asyncio.sleep(5)
        return completion("late", [("late-call", READ)])

    harness = Harness(slow, deny_ids("call-1"))
    reply = await harness.run(client_request(), completion(None, [("call-1", WRITE)]), timeout=0.3)
    message = reply["response"]["choices"][0]["message"]
    assert "tool_calls" not in message and "late" not in message["content"]
    assert message["content"].endswith(
        "No alternative was delivered because the time limit was reached." + PARAGRAPH + ALTERNATIVE_FAILED
    )


@pytest.mark.parametrize(
    "failure,sentence",
    [
        ("provider", "No alternative was delivered because the provider did not return an alternative."),
        ("unreachable", "No alternative was delivered because the gateway could not be reached."),
        ("compressed", "No alternative was delivered because the provider returned a compressed alternative."),
        ("invalid-json", "No alternative was delivered because the provider did not return an alternative."),
        ("watcher", "No alternative was delivered because Watcher did not evaluate the alternative."),
        ("mismatch", "No alternative was delivered because Watcher's decisions do not match the alternative."),
        ("unmergeable", "No alternative was delivered because the gateway cannot verify the alternative."),
        ("malformed", "No alternative was delivered because the gateway cannot verify the alternative."),
    ],
)
async def test_failure_mid_recovery_releases_no_call(failure, sentence):
    def provider(_: dict) -> Any:
        if failure == "provider":
            return httpx.Response(500, json={"error": "upstream"})
        if failure == "unreachable":
            raise httpx.ConnectError("gateway down")
        if failure == "compressed":
            return httpx.Response(200, content=b"x", headers={"content-encoding": "gzip"})
        if failure == "invalid-json":
            return httpx.Response(200, content=b"{not json")
        alternative = completion("alt", [("call-2", READ)])
        if failure == "unmergeable":
            alternative["choices"][0]["message"]["audio"] = {"id": "a"}
        if failure == "malformed":
            alternative["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = "[]"
        return alternative

    def watcher(body: dict) -> Any:
        if calls_in(body)[0]["id"] == "call-1":
            return [outcome("call-1", "deny")]
        if failure == "watcher":
            return httpx.Response(400, json={"detail": "bad"})
        return [outcome("unknown", "allow")]

    harness = Harness(provider, watcher)
    reply = await harness.run(client_request(), completion("Original.", [("call-1", WRITE)]))
    message = reply["response"]["choices"][0]["message"]
    assert "tool_calls" not in message and "call-2" not in json.dumps(reply)
    assert reply["response"]["choices"][0]["finish_reason"] == "stop"
    assert message["content"].startswith("Original.\n\nWATCHER NOTICE")
    assert message["content"].split(PARAGRAPH)[-2:] == [sentence, ALTERNATIVE_FAILED]


@pytest.mark.parametrize(
    "max_body,sentence",
    [
        # With a 100-byte limit even the failure reply is too long, so the short notice replaces it.
        (100, "The full explanation would exceed the gateway's response size limit."),
        (6000, "No alternative was delivered because the alternative exceeds the size limit."),
    ],
)
async def test_alternative_over_the_size_limit_ends_with_the_question(max_body, sentence):
    harness = Harness(lambda _: completion("x" * 10_000), deny_ids("call-1"))
    reply = await harness.run(client_request(), completion(None, [("call-1", WRITE)]), max_body=max_body)
    message = reply["response"]["choices"][0]["message"]
    assert "tool_calls" not in message and "xxxx" not in message["content"]
    *_, before, last = message["content"].split(PARAGRAPH)
    assert before.endswith(sentence) and last == ALTERNATIVE_FAILED
    assert len(harness.provider_requests) == (0 if max_body == 100 else 1)


async def test_replacement_over_the_body_limit_is_shortened_and_still_asks():
    harness = Harness(lambda _: pytest.fail("the continuation is too long to send"), deny_ids("call-1"))
    original = completion("x" * MAX_BODY, [("call-1", WRITE)])
    reply = await harness.run(client_request(), original)
    assert reply["action"] == "replace" and len(json.dumps(reply["response"])) < 4096
    choice = reply["response"]["choices"][0]
    assert choice["finish_reason"] == "stop" and "tool_calls" not in choice["message"]
    assert choice["message"]["content"].startswith("WATCHER NOTICE (added by Watcher")
    assert "xxxx" not in choice["message"]["content"] and choice["message"]["content"].endswith(ALTERNATIVE_FAILED)


@pytest.mark.parametrize("outcome", ["approved", "final"])
async def test_composed_reply_over_the_body_limit_is_shortened_and_still_asks(outcome):
    # Each response fits on its own; only the composed reply exceeds the limit.
    calls = [("call-2", READ)] if outcome == "approved" else []
    reply_text = "y" * 5000
    watcher = deny_ids("call-1", decision="deny" if outcome == "approved" else "escalate")
    harness = Harness(lambda _: completion(reply_text, calls), watcher)
    original = completion("x" * 3000, [("call-1", WRITE)])
    reply = await harness.run(client_request(), original, max_body=7000)
    assert len(harness.provider_requests) == 1
    message = reply["response"]["choices"][0]["message"]
    assert "tool_calls" not in message and "xxxx" not in message["content"] and "yyyy" not in message["content"]
    if outcome == "approved":
        assert message["content"].endswith(ALTERNATIVE_FAILED)
    else:
        assert "WATCHER ESCALATION" in message["content"].split(PARAGRAPH)[-1]
    # An approved call the size limit dropped never reached the client, so it is named as withheld.
    assert harness.delivery is not None
    assert harness.delivery.withheld == (["call-1", "call-2"] if outcome == "approved" else ["call-1"])


def test_system_notice_follows_leading_instructions_and_is_idempotent():
    request = {
        "model": "m",
        "messages": [
            {"role": "system", "content": "a"},
            {"role": "developer", "content": "b"},
            {"role": "user", "content": "c"},
            {"role": "system", "content": "late"},
        ],
    }
    noticed = with_system_notice(request)
    assert noticed is not None
    assert [message["content"] for message in noticed["messages"]] == ["a", "b", SYSTEM_NOTICE, "c", "late"]
    assert request["messages"][2]["content"] == "c", "the input must not be mutated"
    assert with_system_notice(noticed) is None
    assert with_system_notice({"messages": "not a list"}) is None
    bare = with_system_notice({"messages": [{"role": "user", "content": "hi"}]})
    assert bare is not None and bare["messages"][0] == {"role": "system", "content": SYSTEM_NOTICE}


async def test_notice_reaches_provider_body_watcher_snapshot_and_continuation():
    body = json.dumps(
        {
            "model": "fixture",
            "messages": [{"role": "user", "content": "go"}],
            "tools": [{"type": "function", "function": {"name": "Write"}}],
        }
    ).encode()
    status, reply = validate({"body": base64.b64encode(body).decode()}, MarkerLedger(KEY), allow_stream=False)
    assert status == 200 and reply["action"] == "grade"
    installed = reply["request"]
    assert installed["messages"][0] == {"role": "system", "content": SYSTEM_NOTICE}
    status, again = validate(
        {"body": base64.b64encode(json.dumps(installed).encode()).decode()}, MarkerLedger(KEY), allow_stream=False
    )
    assert again == {"action": "grade"}, "an already noticed request is sent unchanged"

    harness = Harness(lambda _: completion("ok"), deny_ids("call-1"))
    await harness.run(installed, completion(None, [("call-1", WRITE)]))
    assert harness.watcher_requests[0]["request_body"]["messages"][0]["content"] == SYSTEM_NOTICE
    continuation = harness.provider_requests[0]
    assert [message.get("content") for message in continuation["messages"]].count(SYSTEM_NOTICE) == 1


def _compact_request(size: int) -> bytes:
    """A compact client request of exactly ``size`` bytes, made of many short messages."""
    filler = [{"role": "user", "content": ""}] * ((size - 4096) // 29)
    request = {"model": "fixture", "messages": [*filler, {"role": "user", "content": ""}]}
    padding = size - len(json.dumps(request, separators=(",", ":")).encode())
    request["messages"][-1]["content"] = "x" * padding
    body = json.dumps(request, separators=(",", ":")).encode()
    assert len(body) == size
    return body


def _bridge_handler(monkeypatch: pytest.MonkeyPatch) -> Callable[[str, bytes], tuple[int, bytes]]:
    """Start ``serve`` against fakes and return a function posting one raw body to its handler."""
    import io
    from types import SimpleNamespace

    import watcher_bifrost.bridge as bridge

    handlers = []

    def server(_address: object, handler: object) -> SimpleNamespace:
        handlers.append(handler)
        return SimpleNamespace(serve_forever=lambda: None)

    monkeypatch.setattr(bridge, "ThreadingHTTPServer", server)
    monkeypatch.setattr(
        bridge,
        "AsyncWatcherClient",
        lambda *args, **kwargs: AsyncWatcherClient(
            "http://watcher.invalid",
            httpx_client=httpx.AsyncClient(
                base_url="http://watcher.invalid",
                transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"granted": True, "missing": []})),
            ),
        ),
    )
    monkeypatch.setenv("WATCHER_BRIDGE_TOKEN", "fixture-token")
    monkeypatch.setenv("WATCHER_BASE_URL", "http://watcher.invalid")
    monkeypatch.setenv("WATCHER_API_KEY", "fixture-key")
    monkeypatch.setenv("WATCHER_GATEWAY_URL", "http://127.0.0.1:8080")
    bridge.serve("127.0.0.1", 0)

    def post(path: str, payload: bytes) -> tuple[int, bytes]:
        raw = (
            f"POST {path} HTTP/1.0\r\nAuthorization: Bearer fixture-token\r\nContent-Length: {len(payload)}\r\n\r\n"
        ).encode() + payload
        sent = bytearray()
        connection = SimpleNamespace(makefile=lambda *_: io.BytesIO(raw), sendall=sent.extend)
        handlers[0](connection, ("127.0.0.1", 1234), SimpleNamespace())
        head, body = bytes(sent).split(b"\r\n\r\n", 1)
        return int(head.split(b" ")[1]), body

    return post


def test_noticed_request_near_the_limit_still_fits_because_it_is_sent_compact(monkeypatch):
    client_body = _compact_request(MAX_BODY - 4096)
    noticed = with_system_notice(json.loads(client_body))
    assert noticed is not None
    assert len(json.dumps(noticed).encode()) > MAX_BODY, "default separators would push this request over the limit"

    post = _bridge_handler(monkeypatch)
    envelope = json.dumps({"body": base64.b64encode(client_body).decode(), "marker": ""}).encode()
    status, reply = post("/validate", envelope)

    # The plugin installs the reply's "request" value byte for byte and checks it against the limit.
    prefix = b'{"action":"grade","request":'
    assert status == 200 and reply.startswith(prefix) and reply.endswith(b"}")
    upstream = reply[len(prefix) : -1]
    assert json.loads(upstream) == noticed
    assert upstream == json.dumps(noticed, ensure_ascii=False, separators=(",", ":")).encode()
    assert len(upstream) <= MAX_BODY


@pytest.mark.parametrize("missing", ["request", "response"])
def test_exchange_without_a_request_or_response_object_is_withheld(monkeypatch, missing):
    exchange: dict[str, Any] = {
        "request": client_request(),
        "response": completion(None, [("call-1", WRITE)]),
        "metadata": {"watcher_conversation_id": "bifrost:parent"},
    }
    exchange[missing] = None
    status, reply = _bridge_handler(monkeypatch)("/evaluate", json.dumps(exchange).encode())
    assert (status, json.loads(reply)) == (200, {"action": "withhold"})


def test_request_the_notice_would_push_past_the_limit_is_refused():
    body = _compact_request(MAX_BODY - 100)
    with pytest.raises(UnsupportedExchange, match="system notice exceeds"):
        validate({"body": base64.b64encode(body).decode()}, MarkerLedger(KEY), allow_stream=False)


def test_marker_must_match_exact_body_once_and_unexpired():
    ledger = MarkerLedger(KEY)
    body = json.dumps({"model": "fixture", "messages": [{"role": "user", "content": "x"}], "stream": False}).encode()
    encoded = base64.b64encode(body).decode()
    expiry = int(time.time()) + 60
    marker = ledger.sign(body, expiry)

    def check(value: str, payload: str = encoded) -> tuple[int, dict]:
        return validate({"body": payload, "marker": value}, ledger, allow_stream=False)

    assert check(marker) == (200, {"action": "passthrough"})
    assert check(marker) == (403, {"action": "reject"}), "a marker is accepted once"
    for zeros in ("0", "00"):
        assert check(zeros + marker) == (403, {"action": "reject"}), "a re-spelled expiry is not a new marker"
    respelled = ledger.sign(body, expiry + 2)
    assert check("0" + respelled)[0] == 403, "non-canonical expiry is malformed even when unused"
    assert check(respelled) == (200, {"action": "passthrough"})
    other = json.dumps({"model": "fixture", "messages": [{"role": "user", "content": "y"}]}).encode()
    fresh = ledger.sign(body, expiry + 1)
    assert check(fresh, base64.b64encode(other).decode())[0] == 403, "wrong body"
    assert check(MarkerLedger(marker_key("client-guess")).sign(body, expiry))[0] == 403, "forged key"
    assert check(ledger.sign(body, int(time.time()) - 1))[0] == 403, "expired"
    for malformed in ("1", "x.y", f"{expiry}.{'0' * 63}", f"{expiry}.{'A' * 64}", f"-1.{'0' * 64}"):
        assert check(malformed)[0] == 403
    streamed = json.dumps({"model": "fixture", "messages": [{"role": "user", "content": "x"}], "stream": True}).encode()
    with pytest.raises(UnsupportedExchange):
        validate(
            {"body": base64.b64encode(streamed).decode(), "marker": ledger.sign(streamed, expiry)},
            ledger,
            allow_stream=True,
        )


async def test_credentials_outside_the_authentication_headers_are_refused():
    harness = Harness(lambda _: pytest.fail("no alternative"), deny_ids("call-1"))
    envelope_request = client_request()
    async with (
        AsyncWatcherClient(
            "http://watcher.invalid",
            httpx_client=httpx.AsyncClient(
                base_url="http://watcher.invalid", transport=httpx.MockTransport(harness._watcher)
            ),
        ) as watcher,
        httpx.AsyncClient(base_url="http://gateway.invalid") as client,
    ):
        with pytest.raises(UnsupportedExchange):
            await respond(
                watcher,
                Gateway(client=client, ledger=MarkerLedger(KEY), max_body=MAX_BODY),
                {
                    "request": envelope_request,
                    "response": completion(None, [("call-1", WRITE)]),
                    "metadata": {
                        "watcher_conversation_id": "bifrost:parent",
                        "watcher_url": "/x",
                        "watcher_provider": "openai",
                    },
                    "credentials": {"Cookie": "session"},
                },
                allow_stream=False,
                deadline=asyncio.get_running_loop().time() + 5,
            )
    assert harness.watcher_requests == []


@pytest.mark.parametrize(
    "final",
    [
        completion(None),
        completion(""),
        completion(" \t\n"),
        completion("Should I", finish="length"),
        completion("Should I", finish="content_filter"),
        completion("Both writes were blocked, so I stopped."),
    ],
    ids=["null", "empty", "blank", "cut-off", "filtered", "no-question"],
)
async def test_final_generation_without_a_reliable_question_gets_the_stop_notice(final):
    harness = Harness(lambda _: final, deny_ids("call-1", decision="escalate", source="triage"))
    reply = await harness.run(client_request(), completion(None, [("call-1", WRITE)]))
    choice = reply["response"]["choices"][0]
    assert choice["finish_reason"] == "stop" and "tool_calls" not in choice["message"]
    assert (
        choice["message"]["content"]
        .split("\n\n")[-1]
        .strip()
        .startswith(
            "WATCHER ESCALATION (added by Watcher, not written by the assistant): Watcher withheld further tool calls"
        )
    )
    assert len(harness.watcher_requests) == 1


async def test_complete_final_generation_that_asks_is_delivered_without_the_stop_notice():
    """A final reply that puts its own question to the user is not asked twice."""
    asking = "Both writes were blocked. Should I skip them or try another file?"
    harness = Harness(lambda _: completion(asking), deny_ids("call-1", decision="escalate", source="triage"))
    reply = await harness.run(client_request(), completion(None, [("call-1", WRITE)]))
    choice = reply["response"]["choices"][0]
    assert choice["finish_reason"] == "stop" and choice["message"]["content"].endswith(asking)
    assert "Watcher withheld further tool calls" not in choice["message"]["content"]


async def test_key_selection_and_configured_headers_reach_every_alternative():
    forwarded = alternative_headers("X-Team-Project")
    credentials = {
        "Authorization": "Bearer direct-provider-key",
        "X-Bf-Direct-Key": "true",
        "X-Bf-Api-Key": "selected",
        "X-Bf-Api-Key-Id": "key-7",
        "X-Team-Project": "alpha",
        "X-Bf-Session-Id": "session-explicit",
        "X-Claude-Code-Session-Id": "session-harness",
        "session_id": "codex-session",
    }
    replies = iter(
        [completion(None, [("call-2", READ)]), completion("Read it.", [("call-3", READ | {"arguments": "{}"})])]
    )
    harness = Harness(lambda _: next(replies), deny_ids("call-1", "call-2"))
    reply = await harness.run(
        client_request(), completion(None, [("call-1", WRITE)]), credentials=credentials, forwarded=forwarded
    )
    assert reply["response"]["choices"][0]["message"]["tool_calls"][0]["id"] == "call-3"
    assert len(harness.provider_headers) == 2
    for headers in harness.provider_headers:
        assert {name: headers[name] for name in map(str.lower, credentials)} == {
            name.lower(): value for name, value in credentials.items()
        }


def test_forwarded_headers_reject_unlisted_reserved_and_malformed_names():
    assert alternative_headers("") == FORWARDED_HEADERS
    assert "x-team" in alternative_headers(" X-Team ,, ")
    for bad in ("Content-Length", "x-watcher-alternative", "Host", "bad header", "x:y"):
        with pytest.raises(ValueError):
            alternative_headers(bad)


@pytest.mark.parametrize("granted", [True, False])
def test_serve_reports_missing_permission_before_missing_gateway_url(monkeypatch, granted):
    import watcher_bifrost.bridge as bridge

    def transport(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"granted": granted, "missing": [] if granted else ["sessions:ingest"]})

    monkeypatch.setattr(
        bridge,
        "AsyncWatcherClient",
        lambda *args, **kwargs: AsyncWatcherClient(
            "http://watcher.invalid",
            httpx_client=httpx.AsyncClient(base_url="http://watcher.invalid", transport=httpx.MockTransport(transport)),
        ),
    )
    monkeypatch.setattr(bridge, "ThreadingHTTPServer", lambda *_: pytest.fail("bridge must not serve"))
    monkeypatch.setenv("WATCHER_BRIDGE_TOKEN", "token")
    monkeypatch.setenv("WATCHER_BASE_URL", "http://watcher.invalid")
    monkeypatch.setenv("WATCHER_API_KEY", "key")
    monkeypatch.delenv("WATCHER_GATEWAY_URL", raising=False)
    with pytest.raises(UnsupportedExchange if granted else PermissionError):
        bridge.serve("127.0.0.1", 0)


def _final_call(body: dict) -> bool:
    """Whether a provider request is the final, text-only generation."""
    return body.get("tool_choice") == "none"


def _always_deny(body: dict) -> list:
    return [outcome(call["id"], "deny") for call in calls_in(body)]


@pytest.mark.parametrize("failure", ["http-500", "timeout", "invalid-json", "unmergeable"])
@pytest.mark.parametrize("route", ["escalation", "three-denials"])
async def test_failed_final_generation_still_asks_the_user(failure, route):
    counter = iter(range(100))

    async def provider(body: dict) -> Any:
        if not _final_call(body):
            index = next(counter)
            return completion(None, [(f"alt-{index}", {"name": "Write", "arguments": json.dumps({"n": index})})])
        if failure == "http-500":
            return httpx.Response(500, json={"error": "upstream"})
        if failure == "timeout":
            await asyncio.sleep(5)
        if failure == "invalid-json":
            return httpx.Response(200, content=b"{not json")
        final = completion("Ask")
        final["choices"][0]["message"]["audio"] = {"id": "a"}
        return final

    watcher = (
        deny_ids("call-1", decision="escalate", source="policy_gateway") if route == "escalation" else _always_deny
    )
    harness = Harness(provider, watcher)
    reply = await harness.run(client_request(), completion(None, [("call-1", WRITE)]), timeout=1.5)

    choice = reply["response"]["choices"][0]
    assert choice["finish_reason"] == "stop" and "tool_calls" not in choice["message"]
    parts = choice["message"]["content"].split(PARAGRAPH)
    assert parts[-2].startswith("No final reply was delivered because ")
    expected_stop = "WATCHER ESCALATION" if route == "escalation" else "WATCHER NOTICE"
    assert parts[-1].startswith(expected_stop + " (added by Watcher, not written by the assistant): Watcher ")
    assert ("Reply A to allow" in parts[-1]) is (route == "escalation")
    assert len(harness.watcher_requests) == (1 if route == "escalation" else 3)
    assert _final_call(harness.provider_requests[-1])


async def test_cut_off_final_with_partial_call_is_withheld_unparsed():
    final = completion("Should I", [("call-final", {"name": "Write", "arguments": '{"file_path":'})], finish="length")
    harness = Harness(lambda _: final, deny_ids("call-1", decision="escalate", source="triage"))
    reply = await harness.run(client_request(), completion(None, [("call-1", WRITE)]))

    choice = reply["response"]["choices"][0]
    assert choice["finish_reason"] == "stop" and "tool_calls" not in choice["message"]
    assert "call-final" not in json.dumps(reply)
    parts = choice["message"]["content"].split(PARAGRAPH)
    assert parts[-2] == "Should I"
    assert parts[-1].startswith("WATCHER ESCALATION (added by Watcher, not written by the assistant): Watcher withheld")
    assert len(harness.watcher_requests) == 1


@pytest.mark.parametrize(
    "response_format,structured",
    [
        ({"type": "json_object"}, True),
        ({"type": "json_schema", "json_schema": {"name": "r", "schema": {"type": "object"}}}, True),
        ({"type": "text"}, False),
        (None, False),
    ],
)
async def test_structured_output_refusal_is_an_explicit_error(response_format, structured):
    request = client_request() if response_format is None else client_request(response_format=response_format)
    harness = Harness(lambda _: completion("Done another way."), deny_ids("call-1"))
    reply = await harness.run(request, completion(None, [("call-1", WRITE)]))
    if structured:
        assert reply == {"action": "structured_refusal"}
        assert harness.provider_requests == []
    else:
        assert reply["action"] == "replace"
        assert "WATCHER NOTICE" in reply["response"]["choices"][0]["message"]["content"]
    # The text-only alternative is graded too when the notice can be delivered.
    assert len(harness.watcher_requests) == (1 if structured else 2)


def test_denial_notice_is_bounded_and_counts_what_it_leaves_out():
    from watcher_bifrost.replan import ToolCall, ToolDenial, denial_notice

    big = ToolDenial(
        tool_use_id="a", tool_name="t" * 1000, tool_input={"text": "é" * 20_000}, reason="r" * 9000, is_escalation=False
    )
    single = denial_notice([big])
    assert len(single) < 9000 and "… (arguments shortened)" in single and "r" * 4096 + "." in single
    denials = [
        ToolDenial(
            tool_use_id=f"d{n}", tool_name="Write", tool_input={"x": "y" * 3000}, reason="No", is_escalation=False
        )
        for n in range(40)
    ]
    siblings = [ToolCall(tool_use_id=f"s{n}", tool_name="Read", tool_input={"x": "y" * 4000}) for n in range(100)]
    text = denial_notice(denials, cancelled=siblings)
    assert len(text.encode()) <= 64 * 1024
    assert text.endswith("more refused calls and 100 more withheld calls did not run.")
    text = denial_notice(denials[:1], cancelled=siblings)
    assert len(text.encode()) <= 64 * 1024
    assert text.endswith("more withheld calls did not run.")
    wide = [ToolCall(tool_use_id=f"w{n}", tool_name="Read", tool_input={"x": "😀" * 4000}) for n in range(100)]
    text = denial_notice(denials[:1], cancelled=wide)
    shown = text.count("did not run because Watcher refused another call")
    assert len(text.encode()) <= 64 * 1024
    assert text.endswith(f": 0 more refused calls and {100 - shown} more withheld calls did not run.")


@pytest.mark.parametrize(
    "content,finish",
    [(None, "stop"), ("", "stop"), (" \t\n", "stop"), ("Partial ans", "length"), ("Hidden", "content_filter")],
)
async def test_text_only_alternative_that_asks_nothing_ends_with_the_question(content, finish):
    harness = Harness(lambda _: completion(content, finish=finish), deny_ids("call-1"))
    reply = await harness.run(client_request(), completion("Writing.", [("call-1", WRITE)]))
    choice = reply["response"]["choices"][0]
    assert choice["finish_reason"] == "stop" and "tool_calls" not in choice["message"]
    assert choice["message"]["content"].endswith((f"{content}{PARAGRAPH}" if content else "") + ALTERNATIVE_FAILED)


async def test_complete_text_only_alternative_is_delivered_without_the_question():
    harness = Harness(lambda _: completion("I can't do that safely; shall I skip it?"), deny_ids("call-1"))
    reply = await harness.run(client_request(), completion("Writing.", [("call-1", WRITE)]))
    content = reply["response"]["choices"][0]["message"]["content"]
    assert content.endswith("shall I skip it?") and ALTERNATIVE_FAILED not in content


async def test_recorded_delivery_moves_released_calls_into_history_and_names_withheld_calls():
    """The client's reply is recorded in its session with nothing graded again, naming every withheld call."""
    request = client_request()
    original = completion(None, [("call-write", WRITE), ("call-sibling", READ)])
    alternative = completion("Reading a copy.", [("call-copy", {"name": "Read", "arguments": '{"file_path":"b"}'})])
    harness = Harness(lambda _: alternative, deny_ids("call-write"))
    reply = await harness.run(request, original)

    assert harness.delivery is not None and harness.delivery.withheld == ["call-write", "call-sibling"]
    recorded = await harness.record()
    delivered = reply["response"]["choices"][0]["message"]
    assert recorded["external_ids"] == {"other": "bifrost:parent"} and recorded["withholds_refused_calls"] is True
    assert recorded["withheld_tool_use_ids"] == ["call-write", "call-sibling"]
    assert recorded["request_body"]["messages"] == [*request["messages"], delivered]
    assert recorded["response_body"]["choices"][0]["message"] == {"role": "assistant", "content": None}
    assert recorded["response_body"]["choices"][0]["finish_reason"] == "stop"


async def test_recorded_text_reply_is_the_response_itself():
    request = client_request()
    harness = Harness(lambda _: completion("Done another way."), deny_ids("call-write"))
    reply = await harness.run(request, completion(None, [("call-write", WRITE)]))

    recorded = await harness.record()
    assert recorded["request_body"] == request and recorded["response_body"] == reply["response"]
    assert recorded["withheld_tool_use_ids"] == ["call-write"]


async def test_withheld_calls_include_local_repeats_but_never_a_delivered_call():
    """A repeat refused without grading is withheld too; an ID the delivered reply reuses is not named."""
    replies = iter(
        [
            completion(None, [("call-renamed", WRITE)]),
            completion("Read it.", [("call-1", READ)]),
        ]
    )

    def deny_writes(body: dict) -> list:
        return [
            outcome(call["id"], "deny" if call["function"]["name"] == "Write" else "allow") for call in calls_in(body)
        ]

    harness = Harness(lambda _: next(replies), deny_writes)
    reply = await harness.run(client_request(), completion(None, [("call-1", WRITE)]))

    assert reply["response"]["choices"][0]["message"]["tool_calls"][0]["id"] == "call-1"
    assert harness.delivery is not None and harness.delivery.withheld == ["call-renamed"]


async def test_failed_recovery_is_recorded_and_unreplaced_answers_record_nothing():
    harness = Harness(lambda _: httpx.Response(500, json={}), deny_ids("call-1"))
    reply = await harness.run(client_request(), completion(None, [("call-1", WRITE)]))
    assert reply["action"] == "replace" and harness.delivery is not None
    assert harness.delivery.withheld == ["call-1"]

    released = Harness(lambda _: pytest.fail("no alternative"), deny_ids())
    assert await released.run(client_request(), completion(None, [("call-1", WRITE)])) == {"action": "release"}
    assert released.delivery is None


def older_server(body: dict) -> httpx.Response | list:
    """A Watcher that predates the gateway fields: it forbids them as unknown."""
    extra = [field for field in ("withholds_refused_calls", "withheld_tool_use_ids") if field in body]
    if extra:
        detail = [{"type": "extra_forbidden", "loc": ["body", field], "msg": "Extra inputs"} for field in extra]
        return httpx.Response(422, json={"detail": detail})
    return deny_ids("call-1")(body)


async def test_older_watcher_gets_each_exchange_again_without_the_gateway_fields():
    harness = Harness(lambda _: completion("Done another way."), older_server)
    reply = await harness.run(client_request(), completion(None, [("call-1", WRITE)]))

    assert reply["action"] == "replace"
    # The original and the alternative are each sent once with the flag and once without.
    flagged = ["withholds_refused_calls" in body for body in harness.watcher_requests]
    assert flagged == [True, False, True, False]
    await harness.record()
    assert "withheld_tool_use_ids" in harness.watcher_requests[4]
    assert not {"withheld_tool_use_ids", "withholds_refused_calls"} & set(harness.watcher_requests[5])


@pytest.mark.parametrize(
    "rejection",
    [
        httpx.Response(422, json={"detail": [{"type": "missing", "loc": ["body", "withholds_refused_calls"]}]}),
        httpx.Response(422, json={"detail": "plain"}),
        httpx.Response(400, json={"detail": [{"type": "extra_forbidden", "loc": ["body", "withheld_tool_use_ids"]}]}),
    ],
    ids=["other-validation-error", "unstructured", "not-422"],
)
async def test_other_watcher_rejections_are_not_retried(rejection):
    harness = Harness(lambda _: pytest.fail("no alternative"), lambda _: rejection)
    with pytest.raises(WatcherAPIError):
        await harness.run(client_request(), completion(None, [("call-1", WRITE)]))
    assert len(harness.watcher_requests) == 1


async def test_failed_recording_is_logged_not_raised():
    harness = Harness(lambda _: completion("Done another way."), deny_ids("call-1"))
    await harness.run(client_request(), completion(None, [("call-1", WRITE)]))
    harness.watcher = lambda _: httpx.Response(503, json={"detail": "down"})
    with structlog.testing.capture_logs() as logs:
        await harness.record()
    assert [entry["event"] for entry in logs] == ["delivery_not_recorded"]
