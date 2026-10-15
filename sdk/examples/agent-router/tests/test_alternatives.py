"""Ask for alternatives after a refusal, through a fake gateway listener and a fake Watcher API."""

import asyncio
import copy
import gzip
import json

import httpx
import pytest
import structlog
from watcher_agent_router.alternatives import (
    ALTERNATIVE_HEADER,
    STOPPED,
    Gateway,
    marker_key,
    recover,
    sign_marker,
    verify_marker,
)
from watcher_agent_router.exchange import (
    RETRY_INSTRUCTION,
    Denial,
    Evaluation,
    UnsupportedExchange,
    alternative_message,
    compose,
    continuation,
    operation_key,
)

from watcher_sdk import AsyncWatcherClient

KEY = marker_key("fixture-watcher-key")
CONVERSATION = "agent-router:original"
REQUEST = {
    "model": "fixture",
    "stream": True,
    "stream_options": {"include_usage": True},
    "tool_choice": "auto",
    "messages": [{"role": "user", "content": "fixture marker"}],
    "tools": [{"type": "function", "function": {"name": "write_file"}}],
}


def completion(*calls: tuple[str, str, dict], content: object = None, reason: str | None = None) -> dict:
    """A buffered completion proposing ``calls`` as (ID, name, arguments)."""
    message: dict = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = [
            {"type": "function", "id": i, "function": {"name": n, "arguments": json.dumps(a)}} for i, n, a in calls
        ]
    return {
        "id": "chatcmpl-1",
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        "choices": [{"index": 0, "message": message, "finish_reason": reason or ("tool_calls" if calls else "stop")}],
    }


ORIGINAL = completion(("call-1", "write_file", {"path": "a"}), ("call-2", "write_file", {"path": "b"}), content="Hi")
REFUSED = Evaluation(
    verified=True,
    denials=[
        Denial(
            tool_use_id="call-1",
            tool_name="write_file",
            tool_input={"path": "a"},
            reason="Too risky",
            is_escalation=False,
        )
    ],
)


async def _chunks(data: bytes, count: int):
    """A streamed body, read incrementally rather than buffered by the fake transport."""
    for _ in range(count):
        yield data


def outcome(tool_use_id: str, value: str) -> dict:
    return {
        "tool_use_id": tool_use_id,
        "decision": value,
        "judged_decision": value,
        "decision_source": "rule",
        "enforcement_mode": "enforce",
        "verdict": {"explanation": f"{value} {tool_use_id}"},
        "latency_ms": 1,
    }


def client(base: str, handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base, transport=httpx.MockTransport(handler))


class Fakes:
    """A gateway that returns queued alternatives and a Watcher that returns queued decisions."""

    def __init__(self, alternatives: list, decisions: list | None = None) -> None:
        self.alternatives = list(alternatives)
        self.decisions = list(decisions or [])
        self.gateway_requests: list[httpx.Request] = []
        self.hooks: list[dict] = []
        self.delay = 0.0

    async def gateway(self, request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(self.delay)
        self.gateway_requests.append(request)
        reply = self.alternatives.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, httpx.Response) else httpx.Response(200, json=reply)

    def watcher(self, request: httpx.Request) -> httpx.Response:
        self.hooks.append(json.loads(request.content))
        reply = self.decisions.pop(0)
        return reply if isinstance(reply, httpx.Response) else httpx.Response(200, json=reply)

    async def recover(self, *, deadline_in: float = 30, gateway: bool = True, max_body: int = 1 << 20, **kwargs):
        watcher = AsyncWatcherClient(
            "http://watcher.invalid", httpx_client=client("http://watcher.invalid", self.watcher)
        )
        async with watcher, client("http://gateway.invalid", self.gateway) as http:
            listener = Gateway(client=http, client_key="gateway-key", marker_key=KEY, max_body=max_body)
            return await recover(
                watcher,
                listener if gateway else None,
                kwargs.get("request", REQUEST),
                kwargs.get("response", ORIGINAL),
                kwargs.get("evaluation", REFUSED),
                conversation_id=CONVERSATION,
                user_agent="fixture/1.0",
                deadline=asyncio.get_running_loop().time() + deadline_in,
            )


def test_marker_binds_the_exact_body_until_it_expires():
    marker = sign_marker(KEY, b"{}", expiry=2_000)
    assert verify_marker(KEY, marker, b"{}", now=1_999)
    assert not verify_marker(KEY, marker, b"{} ", now=1_999)
    assert not verify_marker(KEY, marker, b"{}", now=2_001)
    assert not verify_marker(marker_key("other"), marker, b"{}", now=1_999)
    assert not verify_marker(KEY, "not-a-marker", b"{}", now=0)
    assert not verify_marker(KEY, f"2000.{'0' * 64}", b"{}", now=0)
    assert verify_marker(KEY, sign_marker(KEY, b"{}", expiry=10**10), b"{}")


@pytest.mark.parametrize(
    "marker",
    ["9" * 5000 + "." + "0" * 64, "9999999999." + "é" * 64, "9999999999." + "A" * 64, "9999999999.", ".", ""],
)
def test_malformed_markers_are_rejected_without_raising(marker):
    assert not verify_marker(KEY, marker, b"{}", now=0)


def test_continuation_explains_each_call_without_changing_the_request():
    original = copy.deepcopy(REQUEST)
    result = continuation(REQUEST, ORIGINAL, REFUSED)
    assert original == REQUEST, "the client's request is not modified"
    assert result["stream"] is False and "stream_options" not in result and result["tool_choice"] == "auto"
    assistant, denied, cancelled = result["messages"][1:]
    assert assistant == ORIGINAL["choices"][0]["message"]
    assert denied["role"] == "tool" and denied["tool_call_id"] == "call-1"
    assert '"reason": "Too risky"' in denied["content"] and denied["content"].endswith(RETRY_INSTRUCTION)
    assert cancelled["tool_call_id"] == "call-2" and "was not run" in cancelled["content"]


def test_compose_puts_notices_between_the_original_text_and_the_alternative():
    alternative = completion(("call-9", "read_file", {}), content="Reading instead")
    alternative["choices"][0]["message"]["reasoning_content"] = " then read"
    original = copy.deepcopy(ORIGINAL)
    original["choices"][0]["logprobs"] = {"content": []}
    original["choices"][0]["message"]["reasoning_content"] = "Write"
    delivered = compose(original, "NOTICE", alternative)
    choice = delivered["choices"][0]
    assert choice["message"]["content"] == "Hi\n\nNOTICE\n\nReading instead"
    assert choice["message"]["tool_calls"] == alternative["choices"][0]["message"]["tool_calls"]
    assert choice["message"]["reasoning_content"] == "Write then read"
    assert choice["finish_reason"] == "tool_calls" and "logprobs" not in choice
    assert delivered["usage"] == ORIGINAL["usage"] and delivered["id"] == "chatcmpl-1"
    text_only = compose(original, "NOTICE", completion(content="Cannot", reason="length"))["choices"][0]
    assert "tool_calls" not in text_only["message"] and text_only["finish_reason"] == "length"
    alone = compose(original, "NOTICE", None)["choices"][0]
    assert alone["message"]["content"] == "Hi\n\nNOTICE" and alone["finish_reason"] == "stop"


def test_compose_keeps_content_parts_and_unmergeable_text_fields():
    original = copy.deepcopy(ORIGINAL)
    original["choices"][0]["message"]["content"] = [{"type": "text", "text": "Hi"}]
    original["choices"][0]["message"]["reasoning_content"] = [{"text": "opaque"}]
    alternative = completion(content="Instead")
    alternative["choices"][0]["message"]["reasoning_content"] = "more"
    message = compose(original, "NOTICE", alternative)["choices"][0]["message"]
    assert message["content"] == [
        {"type": "text", "text": "Hi"},
        {"type": "text", "text": "NOTICE"},
        {"type": "text", "text": "Instead"},
    ]
    assert message["reasoning_content"] == [{"text": "opaque"}]
    original["choices"][0]["message"]["content"] = 7
    assert compose(original, "NOTICE", None)["choices"][0]["message"]["content"] == "NOTICE"


@pytest.mark.parametrize(
    "change,accepted",
    [
        ({"annotations": [], "refusal": None}, True),
        ({"audio": None}, True),
        ({"annotations": [{"type": "url_citation"}]}, False),
        ({"audio": {"id": "a"}}, False),
        ({"content": [{"type": "text", "text": "x"}]}, False),
        ({"reasoning_content": {"text": "x"}}, False),
    ],
)
def test_alternative_message_refuses_fields_it_cannot_merge(change, accepted):
    response = completion(content="ok")
    response["choices"][0]["message"].update(change)
    if accepted:
        assert alternative_message(response)["content"] == response["choices"][0]["message"]["content"]
    else:
        with pytest.raises(UnsupportedExchange):
            alternative_message(response)


def test_operation_key_ignores_call_ids_but_not_json_types():
    assert operation_key("t", {"b": 1, "a": True}) == operation_key("t", {"a": True, "b": 1})
    assert operation_key("t", {"a": True}) != operation_key("t", {"a": 1})


async def test_without_a_gateway_only_the_refusal_is_explained():
    fakes = Fakes([])
    recovery = await fakes.recover(gateway=False)
    assert recovery.alternative is None and len(recovery.notices) == 1 and fakes.gateway_requests == []


async def test_approved_alternative_is_graded_as_its_own_session():
    alternative = completion(("call-9", "read_file", {}), content="Reading instead")
    fakes = Fakes([alternative], [[outcome("call-9", "allow")]])
    recovery = await fakes.recover()
    assert recovery.alternative == alternative and len(recovery.notices) == 1
    [sent] = fakes.gateway_requests
    assert sent.url.path == "/v1/chat/completions" and sent.headers["x-api-key"] == "gateway-key"
    assert verify_marker(KEY, sent.headers[ALTERNATIVE_HEADER], sent.content)
    asked = json.loads(sent.content)
    assert asked == continuation(REQUEST, ORIGINAL, REFUSED)
    [hook] = fakes.hooks
    session = hook["external_ids"]["other"]
    assert session.startswith("agent-router:") and session != CONVERSATION
    assert hook["request_body"] == asked and hook["response_body"] == alternative
    assert hook["user_agent"] == "fixture/1.0"


async def test_alternative_with_another_success_status_is_graded():
    alternative = completion(("call-9", "read_file", {}))
    fakes = Fakes([httpx.Response(201, json=alternative)], [[outcome("call-9", "allow")]])
    recovery = await fakes.recover()
    assert recovery.alternative == alternative and len(fakes.hooks) == 1


async def test_three_blocked_proposals_stop_with_every_notice():
    first = completion(("call-5", "read_file", {"n": 1}))
    second = completion(("call-6", "read_file", {"n": 2}))
    fakes = Fakes([first, second], [[outcome("call-5", "deny")], [outcome("call-6", "escalate")]])
    recovery = await fakes.recover()
    assert recovery.alternative is None and len(recovery.notices) == 4 and recovery.notices[-1] == STOPPED
    assert "deny call-5" in recovery.notices[1] and "escalate call-6" in recovery.notices[2]
    # The second request carries the first alternative and its refusal.
    history = json.loads(fakes.gateway_requests[1].content)["messages"]
    assert history[-2]["tool_calls"][0]["id"] == "call-5" and history[-1]["tool_call_id"] == "call-5"
    assert len({hook["external_ids"]["other"] for hook in fakes.hooks}) == 2


async def test_repeated_refused_operation_is_refused_without_grading():
    repeat = completion(("call-7", "write_file", {"path": "a"}), ("call-8", "read_file", {}))
    approved = completion(content="I will stop here.")
    fakes = Fakes([repeat, approved], [[]])
    with structlog.testing.capture_logs() as logs:
        recovery = await fakes.recover()
    assert recovery.alternative == approved and len(fakes.hooks) == 1
    # Only the submitted alternative is logged with a session ID.
    events = [(entry["event"], entry.get("alternative_conversation_id")) for entry in logs]
    assert events == [
        ("alternative_repeated", None),
        ("alternative_evaluated", fakes.hooks[0]["external_ids"]["other"]),
    ]
    assert '"tool_use_id": "call-7"' in recovery.notices[1] and "Too risky" in recovery.notices[1]
    assert '["call-8"]' in recovery.notices[1]


@pytest.mark.parametrize(
    "reply,reason",
    [
        (httpx.Response(502, json={"error": {}}), "the provider did not return an alternative"),
        (httpx.Response(200, content=b"not json"), "the provider did not return an alternative"),
        (httpx.Response(200, json=[]), "the provider did not return an alternative"),
        (httpx.Response(200, content=b"x" * 2_000_000), "the alternative exceeds the size limit"),
        (httpx.ConnectError("refused"), "the gateway could not be reached"),
        (
            httpx.Response(200, content=gzip.compress(b"{}" * 10), headers={"content-encoding": "gzip"}),
            "the provider returned a compressed alternative",
        ),
        (httpx.Response(200, content=_chunks(b"x" * 600_000, 4)), "the alternative exceeds the size limit"),
        (completion(("c", "t", {}), reason="length"), "the gateway cannot verify the alternative"),
        (completion(content=[{"type": "text", "text": "x"}]), "the gateway cannot verify the alternative"),
    ],
)
async def test_failed_alternative_explains_why_and_releases_nothing(reply, reason):
    fakes = Fakes([reply])
    recovery = await fakes.recover()
    assert recovery.alternative is None and fakes.hooks == []
    assert recovery.notices[-1] == f"No alternative was delivered because {reason}."


async def test_continuation_too_large_to_send_is_not_sent():
    fakes = Fakes([])
    recovery = await fakes.recover(max_body=100)
    assert fakes.gateway_requests == []
    assert recovery.notices[-1].endswith("because the conversation is too long to ask for an alternative.")


async def test_alternatives_share_the_remaining_time_limit():
    fakes = Fakes([completion(content="late")])
    fakes.delay = 5
    recovery = await fakes.recover(deadline_in=0.05)
    assert recovery.notices[-1] == "No alternative was delivered because the time limit was reached."


@pytest.mark.parametrize(
    "decisions,reason",
    [
        ([httpx.Response(422, json={"detail": "bad"})], "Watcher did not evaluate the alternative"),
        ([httpx.Response(200, content=b"{")], "Watcher did not evaluate the alternative"),
        ([[outcome("other", "allow")]], "Watcher's decisions do not match the alternative"),
    ],
)
async def test_unevaluated_alternative_is_never_released(decisions, reason):
    fakes = Fakes([completion(("call-9", "read_file", {}))], decisions)
    recovery = await fakes.recover()
    assert recovery.alternative is None
    assert recovery.notices[-1] == f"No alternative was delivered because {reason}."
