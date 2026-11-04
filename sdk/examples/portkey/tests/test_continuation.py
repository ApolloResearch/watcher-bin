"""Exercise denial continuation: notices, alternatives, the final question and failure handling.

A mock Watcher transport decides each proposed call by a test policy, and a
mock gateway transport plays the provider behind the launcher's loopback
route. The original provider call happens before the bridge runs, so the
gateway mock sees only the recovery calls: at most three, the last of which is
the final text-only generation.
"""

import asyncio
import hashlib
import hmac
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from structlog.testing import capture_logs
from watcher_portkey.alternatives import (
    ALTERNATIVE_HEADER,
    Delivery,
    Gateway,
    StructuredOutputRefused,
    marker_key,
    record_delivery,
    respond,
    sign_marker,
)
from watcher_portkey.exchange import UnverifiedDecision
from watcher_portkey.replan import ALTERNATIVE_FAILED, ToolCall, ToolDenial, compose, stop_notice
from watcher_portkey.system_notice import SYSTEM_NOTICE, with_system_notice

from watcher_sdk import AsyncWatcherClient

TOKEN = "fixture-bridge-token"
NOTICE_PREFIX = "WATCHER NOTICE (added by Watcher, not written by the assistant)"
ESCALATION_PREFIX = "WATCHER ESCALATION (added by Watcher, not written by the assistant)"
CONTINUE = "Continue the user's task another way"
STOP_AFTER_CAP = "Several different approaches have now been blocked, so stop"
ASK_APPROVAL = "A. allow this call, B. skip it, C. do something else."
ASK_FIXED = "A. skip it, B. do something else, C. ask an administrator to change the policy."
SIBLING = "This call did not run because Watcher refused another call in the same response."

Policy = Callable[[dict], dict]


def call(identifier: str, content: str) -> dict:
    return {
        "id": identifier,
        "type": "function",
        "function": {"name": "Write", "arguments": json.dumps({"file_path": "out.txt", "content": content})},
    }


def completion(*calls: dict, content: str | None = None, finish: str | None = None) -> dict:
    message: dict[str, Any] = {"role": "assistant", "content": content, "refusal": None, "annotations": []}
    if calls:
        message["tool_calls"] = list(calls)
    return {
        "id": "chatcmpl-original",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "fixture-model",
        "choices": [
            {
                "index": 0,
                "message": message,
                "logprobs": None,
                "finish_reason": finish or ("tool_calls" if calls else "stop"),
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def client_request(**changes: Any) -> dict:
    request = {
        "model": "fixture-model",
        "messages": [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Write the file"}],
        "tools": [{"type": "function", "function": {"name": "Write", "parameters": {"type": "object"}}}],
    }
    request.update(changes)
    noticed = with_system_notice(request)
    assert noticed is not None
    return noticed


def outcome(decision: str, source: str = "rule", explanation: str = "Fixture policy blocks this write") -> dict:
    value: dict[str, Any] = {
        "decision": decision,
        "judged_decision": decision,
        "decision_source": source,
        "enforcement_mode": "enforce",
        "verdict": {"explanation": explanation},
        "latency_ms": 1,
    }
    if source == "grading_error":
        value["grading_error"] = {"code": "timeout", "message": "Fixture timeout"}
    return value


def deny_content(*refused: str) -> Policy:
    """Deny calls whose content is listed; allow every other call."""
    return lambda proposed: outcome(
        "deny" if json.loads(proposed["function"]["arguments"])["content"] in refused else "allow"
    )


class Harness:
    """Run ``respond`` against mock Watcher and gateway transports and keep what each received."""

    def __init__(
        self,
        policy: Policy,
        alternatives: list[dict | httpx.Response | Exception],
        watcher_status: list[int] | None = None,
        max_body: int = 1024 * 1024,
    ):
        self.policy = policy
        self.max_body = max_body
        self.alternatives = list(alternatives)
        self.watcher_status = list(watcher_status or [])
        self.watcher: list[dict] = []
        self.gateway: list[httpx.Request] = []
        self.delivery: Delivery | None = None

    def watcher_reply(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.watcher.append(body)
        if self.watcher_status and (status := self.watcher_status.pop(0)) != 200:
            return httpx.Response(status, json={"detail": "fixture failure"})
        calls = body["response_body"]["choices"][0]["message"].get("tool_calls") or []
        return httpx.Response(
            200, json=[{**self.policy(proposed), "tool_use_id": proposed["id"]} for proposed in calls]
        )

    async def gateway_reply(self, request: httpx.Request) -> httpx.Response:
        self.gateway.append(request)
        reply = self.alternatives.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, httpx.Response):
            return reply
        if reply.get("sleep"):
            await asyncio.sleep(reply["sleep"])
        return httpx.Response(200, json=reply)

    def gateway_bodies(self) -> list[dict]:
        return [json.loads(request.content) for request in self.gateway]

    async def run(self, request: dict, response: dict, *, seconds: float = 30) -> dict | None:
        """Run ``respond`` and return the delivered completion, keeping the whole ``Delivery``."""
        gateway = Gateway(
            url="http://gateway.invalid/v1/chat/completions",
            client_key="fixture-client",
            marker_key=marker_key(TOKEN),
            max_body=self.max_body,
            transport=httpx.MockTransport(self.gateway_reply),
        )
        async with AsyncWatcherClient(
            "http://watcher.invalid",
            httpx_client=httpx.AsyncClient(
                base_url="http://watcher.invalid", transport=httpx.MockTransport(self.watcher_reply)
            ),
        ) as watcher:
            self.delivery = await respond(
                watcher,
                gateway,
                request,
                response,
                conversation_id="portkey:client-exchange",
                url="/v1/chat/completions",
                provider="openai",
                user_agent="ordinary-client/1",
                deadline=asyncio.get_running_loop().time() + seconds,
            )
        return self.delivery.response if self.delivery is not None else None


def choice(result: dict | None) -> dict:
    assert result is not None
    return result["choices"][0]


def message(result: dict | None) -> dict:
    return choice(result)["message"]


def tool_results(body: dict) -> list[dict]:
    return [item for item in body["messages"] if item["role"] == "tool"]


async def test_allowed_response_is_released_unchanged():
    harness = Harness(lambda _: outcome("allow"), [])
    assert await harness.run(client_request(), completion(call("call-a", "a"))) is None
    assert harness.gateway == []


async def test_observe_and_paused_release_without_notice():
    for value in (
        {**outcome("deferred"), "judged_decision": "deny", "enforcement_mode": "observe"},
        {**outcome("deferred", "bypass"), "judged_decision": None, "enforcement_mode": "paused"},
    ):
        harness = Harness(lambda _, value=value: value, [])
        assert await harness.run(client_request(), completion(call("call-a", "a"))) is None
        assert harness.gateway == []


async def test_denial_then_allowed_alternative_is_delivered_with_notices():
    request = client_request()
    original = completion(call("call-a", "secret"), content="Writing now.")
    harness = Harness(deny_content("secret"), [completion(call("call-b", "safe"), content="Trying another way.")])
    result = await harness.run(request, original)

    delivered = message(result)
    assert [item["id"] for item in delivered["tool_calls"]] == ["call-b"]
    parts = delivered["content"].split("\n\n")
    assert parts[0] == "Writing now."
    assert parts[1].startswith(NOTICE_PREFIX + ": Watcher blocked `Write ")
    assert "Reason: Fixture policy blocks this write. The call did not run." in parts[1]
    assert parts[2] == "Trying another way."
    assert choice(result)["finish_reason"] == "tool_calls"
    assert result is not None
    for key in ("id", "created", "model", "usage"):
        assert result[key] == original[key]
    assert "secret" not in json.dumps(delivered["tool_calls"])

    (body,) = harness.gateway_bodies()
    assert body["messages"][: len(request["messages"])] == request["messages"]
    assert body["messages"][len(request["messages"])] == original["choices"][0]["message"]
    (result_message,) = tool_results(body)
    assert result_message["tool_call_id"] == "call-a" and CONTINUE in result_message["content"]
    assert "tool_choice" not in body and body["tools"] == request["tools"]
    assert sum(item.get("content") == SYSTEM_NOTICE for item in body["messages"]) == 1

    assert len(harness.watcher) == 2
    first, second = harness.watcher
    # The alternative is graded in the client's own conversation, where Watcher
    # already holds a decision for every call the continuation carries.
    assert first["external_ids"] == second["external_ids"] == {"other": "portkey:client-exchange"}
    assert first["withholds_refused_calls"] is second["withholds_refused_calls"] is True
    assert "withheld_tool_use_ids" not in first and "withheld_tool_use_ids" not in second
    assert second["request_body"] == body
    assert harness.delivery is not None and harness.delivery.withheld_ids == ["call-a"]
    assert any(item.get("content") == SYSTEM_NOTICE for item in second["request_body"]["messages"])


@pytest.mark.parametrize(
    "content,finish,kept",
    [
        (None, "stop", None),
        ("", "stop", None),
        (" \t\n", "stop", " \t\n"),
        ("Partial ans", "length", "Partial ans"),
        ("Hidden", "content_filter", "Hidden"),
    ],
)
async def test_text_only_alternative_that_asks_nothing_ends_with_the_question(content, finish, kept):
    original = completion(call("call-a", "secret"), content="Writing now.")
    harness = Harness(deny_content("secret"), [completion(content=content, finish=finish)])
    result = await harness.run(client_request(), original)
    delivered = message(result)
    assert "tool_calls" not in delivered and choice(result)["finish_reason"] == "stop"
    assert delivered["content"].endswith(ALTERNATIVE_FAILED)
    assert (kept in delivered["content"]) if kept else delivered["content"].count("\n\n") == 2


async def test_complete_text_only_alternative_is_delivered_without_the_question():
    original = completion(call("call-a", "secret"), content="Writing now.")
    harness = Harness(deny_content("secret"), [completion(content="I can't do that safely; shall I skip it?")])
    result = await harness.run(client_request(), original)
    delivered = message(result)
    assert delivered["content"].endswith("shall I skip it?") and choice(result)["finish_reason"] == "stop"


async def test_alternative_request_carries_a_marker_for_its_exact_body_and_client_key():
    harness = Harness(deny_content("secret"), [completion(call("call-b", "safe"))])
    await harness.run(client_request(), completion(call("call-a", "secret")))
    (sent,) = harness.gateway
    assert sent.headers["authorization"] == "Bearer fixture-client"
    marker = sent.headers[ALTERNATIVE_HEADER]
    expiry, nonce, mac = marker.split(".")
    assert expiry[0] != "0" and len(nonce) == 32 and len(mac) == 64
    assert sign_marker(marker_key(TOKEN), sent.content, int(expiry), nonce) == marker
    signed = f"{expiry}.{nonce}.".encode() + hashlib.sha256(sent.content).digest()
    assert mac == hmac.new(marker_key(TOKEN), signed, "sha256").hexdigest()
    assert mac != hmac.new(marker_key("another-token"), signed, "sha256").hexdigest()
    assert sign_marker(marker_key(TOKEN), sent.content + b" ", int(expiry), nonce) != marker


async def test_identical_continuations_get_distinct_markers():
    # Two client requests refused the same way produce byte-identical
    # continuations; the launcher accepts each marker once, so both
    # recoveries need their own.
    markers, bodies = [], []
    for _ in range(2):
        harness = Harness(deny_content("secret"), [completion(call("call-b", "safe"))])
        result = await harness.run(client_request(), completion(call("call-a", "secret")))
        assert [item["id"] for item in message(result)["tool_calls"]] == ["call-b"]
        (sent,) = harness.gateway
        markers.append(sent.headers[ALTERNATIVE_HEADER])
        bodies.append(sent.content)
    assert bodies[0] == bodies[1] and markers[0] != markers[1]


@pytest.mark.parametrize("tools", [True, False])
async def test_three_refused_proposals_then_one_final_text_generation(tools):
    request = client_request() if tools else client_request(tools=None)
    if not tools:
        del request["tools"]
    harness = Harness(
        lambda _: outcome("deny"),
        [
            completion(call("call-b", "b")),
            completion(call("call-c", "c")),
            completion(content="I could not write the file. How should I proceed? A. skip, B. other."),
        ],
    )
    result = await harness.run(request, completion(call("call-a", "a")))

    bodies = harness.gateway_bodies()
    assert len(bodies) == 3  # with the client's original call: four model calls
    assert len(harness.watcher) == 3  # the final generation is never graded
    for body in bodies[:2]:
        assert "tool_choice" not in body
    if tools:
        assert bodies[2]["tool_choice"] == "none"
    else:
        assert "tool_choice" not in bodies[2] and "tools" not in bodies[2]
    assert STOP_AFTER_CAP in tool_results(bodies[2])[-1]["content"]
    assert all(CONTINUE in item["content"] for item in tool_results(bodies[1]))
    delivered = message(result)
    assert "tool_calls" not in delivered
    assert delivered["content"].count(NOTICE_PREFIX) == 3
    assert delivered["content"].endswith("How should I proceed? A. skip, B. other.")
    assert choice(result)["finish_reason"] == "stop"


@pytest.mark.parametrize(
    "source,approvable",
    [("policy_gateway", True), ("triage", True), ("rule", False), ("threshold", False), ("grading_error", False)],
)
async def test_escalation_goes_straight_to_the_final_question(source, approvable):
    harness = Harness(
        lambda _: outcome("escalate", source),
        [completion(content="Watcher needs your decision. Should I A. allow, B. skip, or C. do something else?")],
    )
    result = await harness.run(client_request(), completion(call("call-a", "a")))

    (body,) = harness.gateway_bodies()
    assert len(harness.watcher) == 1
    assert body["tool_choice"] == "none"
    (result_message,) = tool_results(body)
    delivered = message(result)
    assert delivered["content"].count(ESCALATION_PREFIX) == 1
    if approvable:
        assert ASK_APPROVAL in result_message["content"]
        assert "needs the user's decision before it can run" in delivered["content"]
    else:
        assert ASK_FIXED in result_message["content"] and "allow this call" not in result_message["content"]
        assert "cannot be approved in this conversation" in delivered["content"]
    assert "tool_calls" not in delivered and choice(result)["finish_reason"] == "stop"


@pytest.mark.parametrize("source,approvable", [("policy_gateway", True), ("rule", False)])
async def test_final_generation_calls_are_withheld_unevaluated(source, approvable):
    harness = Harness(
        lambda _: outcome("escalate", source),
        [completion(call("call-z", "anyway"), content="Let me try anyway.")],
    )
    result = await harness.run(client_request(), completion(call("call-a", "a")))

    assert len(harness.watcher) == 1
    assert all(
        proposed["id"] != "call-z"
        for submission in harness.watcher
        for proposed in submission["response_body"]["choices"][0]["message"].get("tool_calls") or []
    )
    delivered = message(result)
    assert "tool_calls" not in delivered and choice(result)["finish_reason"] == "stop"
    denial = ToolDenial(
        tool_use_id="call-a",
        tool_name="Write",
        tool_input={"file_path": "out.txt", "content": "a"},
        reason="Fixture policy blocks this write",
        is_escalation=True,
        user_can_approve=approvable,
    )
    assert delivered["content"].endswith("Let me try anyway.\n\n" + stop_notice([denial]))
    assert ("Reply A to allow" in delivered["content"]) is approvable


@pytest.mark.parametrize(
    "final",
    [
        completion(content=None),
        completion(content=""),
        completion(content=" \t\n"),
        completion(content="Should I", finish="length"),
        completion(content="Should I", finish="content_filter"),
        completion(content="Both writes were blocked, so I stopped."),
    ],
    ids=["no-text", "empty", "blank", "cut-off", "filtered", "no-question"],
)
async def test_final_reply_that_asks_nothing_gets_the_fixed_question(final):
    harness = Harness(lambda _: outcome("escalate", "policy_gateway"), [final])
    result = await harness.run(client_request(), completion(call("call-a", "a")))
    assert len(harness.watcher) == 1
    delivered = message(result)
    assert "tool_calls" not in delivered and choice(result)["finish_reason"] == "stop"
    assert delivered["content"].endswith("B to skip it, or C to do something else.")


async def test_complete_final_reply_that_asks_is_delivered_without_the_fixed_question():
    """A final reply that puts its own question to the user is not asked twice."""
    asking = "Both writes were blocked. Should I skip them or try another file?"
    harness = Harness(lambda _: outcome("escalate", "policy_gateway"), [completion(content=asking)])
    result = await harness.run(client_request(), completion(call("call-a", "a")))
    delivered = message(result)
    assert delivered["content"].endswith(asking) and choice(result)["finish_reason"] == "stop"
    assert "Watcher withheld further tool calls" not in delivered["content"]


APPROVABLE_CLOSE = "B to skip it, or C to do something else."
HELD_CLOSE = "C to ask an administrator to change the policy."
CAP_CLOSE = "None of the blocked calls ran. How would you like to proceed?"


@pytest.mark.parametrize("finish", ["length", "tool_calls"])
async def test_final_reply_cut_off_mid_call_keeps_its_text_and_asks(finish):
    truncated = completion(content="Partial question", finish=finish)
    truncated["choices"][0]["message"]["tool_calls"] = [
        {"id": "call-cut", "type": "function", "function": {"name": "Write", "arguments": '{"file_path":'}}
    ]
    harness = Harness(lambda _: outcome("escalate", "policy_gateway"), [truncated])
    result = await harness.run(client_request(), completion(call("call-a", "a")))
    assert len(harness.watcher) == 1 and len(harness.gateway) == 1
    delivered = message(result)
    assert "tool_calls" not in delivered and choice(result)["finish_reason"] == "stop"
    assert "\n\nPartial question\n\n" in delivered["content"]
    assert delivered["content"].endswith(APPROVABLE_CLOSE)
    assert "No final reply was delivered" not in delivered["content"]


def _failure(kind: str) -> dict | httpx.Response:
    if kind == "provider-error":
        return httpx.Response(500, json={"error": "upstream"})
    if kind == "unreadable":
        return httpx.Response(200, content=b"not json", headers={"content-type": "application/json"})
    return {"sleep": 5}


@pytest.mark.parametrize("kind", ["provider-error", "timeout", "unreadable"])
@pytest.mark.parametrize(
    "route,closing",
    [
        ("escalate-policy_gateway", APPROVABLE_CLOSE),
        ("escalate-triage", APPROVABLE_CLOSE),
        ("escalate-rule", HELD_CLOSE),
        ("three-denials", CAP_CLOSE),
    ],
)
async def test_failed_final_generation_still_asks_the_user(kind, route, closing):
    reason = {
        "provider-error": "the provider did not return a usable reply",
        "unreadable": "the provider did not return a usable reply",
        "timeout": "the time limit was reached",
    }[kind]
    if route == "three-denials":
        earlier = [completion(call("call-b", "b")), completion(call("call-c", "c"))]
        harness = Harness(lambda _: outcome("deny"), [*earlier, _failure(kind)])
    else:
        source = route.removeprefix("escalate-")
        earlier = []
        harness = Harness(lambda _: outcome("escalate", source), [_failure(kind)])
    result = await harness.run(
        client_request(), completion(call("call-a", "a")), seconds=1 if kind == "timeout" else 30
    )
    assert len(harness.gateway) == len(earlier) + 1 and len(harness.watcher) == len(earlier) + 1
    assert harness.alternatives == []
    delivered = message(result)
    assert "tool_calls" not in delivered and choice(result)["finish_reason"] == "stop"
    sentence = f"No final reply was delivered because {reason}."
    assert sentence + "\n\n" in delivered["content"] and delivered["content"].endswith(closing)


@pytest.mark.parametrize(
    "response_format",
    [{"type": "json_object"}, {"type": "json_schema", "json_schema": {"name": "out", "schema": {"type": "object"}}}],
)
async def test_structured_output_refusal_is_an_error_without_alternative(response_format):
    harness = Harness(deny_content("secret"), [completion(call("call-b", "safe"))])
    with pytest.raises(StructuredOutputRefused):
        await harness.run(client_request(response_format=response_format), completion(call("call-a", "secret")))
    assert harness.gateway == [] and len(harness.watcher) == 1


async def test_text_response_format_still_gets_notices():
    harness = Harness(deny_content("secret"), [completion(call("call-b", "safe"))])
    result = await harness.run(client_request(response_format={"type": "text"}), completion(call("call-a", "secret")))
    assert NOTICE_PREFIX in message(result)["content"] and len(harness.gateway) == 1


async def test_structured_output_allowed_response_is_released():
    harness = Harness(lambda _: outcome("allow"), [])
    request = client_request(response_format={"type": "json_object"})
    assert await harness.run(request, completion(call("call-a", "a"))) is None


async def test_repeated_refused_operation_under_new_id_is_refused_without_grading():
    harness = Harness(
        deny_content("secret"),
        [completion(call("call-renamed", "secret")), completion(call("call-c", "safe"))],
    )
    result = await harness.run(client_request(), completion(call("call-a", "secret")))

    assert len(harness.watcher) == 2  # the original and the genuinely new alternative
    graded = [s["response_body"]["choices"][0]["message"]["tool_calls"][0]["id"] for s in harness.watcher]
    assert graded == ["call-a", "call-c"]
    delivered = message(result)
    assert [item["id"] for item in delivered["tool_calls"]] == ["call-c"]
    assert delivered["content"].count("Reason: Fixture policy blocks this write.") == 2
    # The model sees the repeat and its refusal; Watcher, which never graded it,
    # gets the same history without them, so it cannot record them as having run.
    asked = harness.gateway_bodies()[-1]["messages"]
    shown = harness.watcher[-1]["request_body"]["messages"]

    def ids(messages: list[dict]) -> list[str]:
        """The call IDs of proposals and results, in order."""
        return [
            item["tool_call_id"] if item["role"] == "tool" else item["tool_calls"][0]["id"]
            for item in messages
            if item["role"] == "tool" or item.get("tool_calls")
        ]

    assert ids(asked) == ["call-a", "call-a", "call-renamed", "call-renamed"]
    assert ids(shown) == ["call-a", "call-a"]
    assert shown == [item for item in asked if "call-renamed" not in json.dumps(item)]


async def test_mixed_siblings_are_withheld_together():
    harness = Harness(deny_content("secret"), [completion(call("call-c", "safe"))])
    result = await harness.run(client_request(), completion(call("call-a", "secret"), call("call-b", "fine")))

    delivered = message(result)
    assert [item["id"] for item in delivered["tool_calls"]] == ["call-c"]
    assert (
        '"content": "fine"' in delivered["content"]
        and "did not run because Watcher refused another call" in delivered["content"]
    )
    (body,) = harness.gateway_bodies()
    results = {item["tool_call_id"]: item["content"] for item in tool_results(body)}
    assert CONTINUE in results["call-a"] and results["call-b"] == SIBLING


async def test_forced_tool_choice_is_kept_until_the_final_generation():
    forced = {"type": "function", "function": {"name": "Write"}}
    request = client_request(tool_choice=forced, parallel_tool_calls=False, temperature=0.2)
    harness = Harness(
        lambda _: outcome("deny"),
        [completion(call("call-b", "b")), completion(call("call-c", "c")), completion(content="Stopping.")],
    )
    await harness.run(request, completion(call("call-a", "a")))
    bodies = harness.gateway_bodies()
    for body in bodies[:2]:
        assert body["tool_choice"] == forced
    assert bodies[2]["tool_choice"] == "none"
    assert all(body["parallel_tool_calls"] is False and body["temperature"] == 0.2 for body in bodies)


async def test_reasoning_history_is_carried_into_the_continuation():
    original = completion(call("call-a", "secret"), content="Plan")
    original["choices"][0]["message"]["reasoning_content"] = "private chain"
    harness = Harness(deny_content("secret"), [completion(call("call-b", "safe"))])
    await harness.run(client_request(), original)
    (body,) = harness.gateway_bodies()
    assert body["messages"][-2]["reasoning_content"] == "private chain"


def ends_asking_after_failure(result: dict | None, reason: str) -> bool:
    """Whether the reply ends with why no alternative followed, then the fixed question to the user."""
    return message(result)["content"].endswith(
        f"No alternative was delivered because {reason}.\n\n{ALTERNATIVE_FAILED}"
    )


def test_failed_alternative_question_is_the_shared_wording():
    assert ALTERNATIVE_FAILED == (
        "WATCHER NOTICE (added by Watcher, not written by the assistant): Watcher blocked the assistant's tool "
        "calls, and the gateway could not get another approach from the assistant, so it delivered no further "
        "tool calls. None of the blocked calls ran. How would you like to proceed?"
    )


async def test_deadline_exhaustion_ends_with_the_fixed_sentence_and_question():
    harness = Harness(deny_content("secret"), [{"sleep": 5}])
    result = await harness.run(client_request(), completion(call("call-a", "secret")), seconds=0.5)
    assert "tool_calls" not in message(result)
    assert ends_asking_after_failure(result, "the time limit was reached")


@pytest.mark.parametrize(
    "alternative,watcher_status,expected",
    [
        (httpx.Response(500, json={"error": "upstream"}), [], "the provider did not return an alternative"),
        (httpx.Response(403, json={"error": "marker"}), [], "the provider did not return an alternative"),
        (httpx.Response(200, content=b"not json"), [], "the provider did not return an alternative"),
        (httpx.Response(200, json=["not", "a", "completion"]), [], "the provider did not return an alternative"),
        (
            httpx.Response(200, headers={"content-encoding": "gzip"}, content=b"\x1f\x8b"),
            [],
            "the provider returned a compressed alternative",
        ),
        (
            completion(call("call-b", "x" * (2 * 1024 * 1024))),
            [],
            "the alternative exceeds the size limit",
        ),
        (httpx.ConnectError("refused"), [], "the gateway could not be reached"),
        (completion(call("call-b", "safe")), [200, 500], "Watcher did not evaluate the alternative"),
        ({"choices": []}, [], "the gateway cannot verify the alternative"),
    ],
)
async def test_failure_mid_recovery_releases_no_call_and_asks_the_user(alternative, watcher_status, expected):
    harness = Harness(deny_content("secret"), [alternative], watcher_status)
    result = await harness.run(client_request(), completion(call("call-a", "secret")))
    delivered = message(result)
    assert "tool_calls" not in delivered and choice(result)["finish_reason"] == "stop"
    assert ends_asking_after_failure(result, expected)
    assert delivered["content"].count(NOTICE_PREFIX) == 2


async def test_conversation_too_long_for_an_alternative_asks_the_user_without_sending():
    harness = Harness(deny_content("secret"), [], max_body=100)
    result = await harness.run(client_request(), completion(call("call-a", "secret")))
    assert harness.gateway == [] and "tool_calls" not in message(result)
    assert ends_asking_after_failure(result, "the conversation is too long to ask for an alternative")


async def test_unexpected_grading_error_on_an_alternative_asks_the_user():
    class BrokenWatcher(Harness):
        """Fail unexpectedly while grading the alternative, the second proposal Watcher sees."""

        def watcher_reply(self, request: httpx.Request) -> httpx.Response:
            reply = super().watcher_reply(request)
            if len(self.watcher) == 2:
                raise RuntimeError("fixture failure")
            return reply

    harness = BrokenWatcher(deny_content("secret"), [completion(call("call-b", "safe"))])
    result = await harness.run(client_request(), completion(call("call-a", "secret")))
    assert "tool_calls" not in message(result)
    assert ends_asking_after_failure(result, "Watcher did not evaluate the alternative")


async def test_unmatched_alternative_decision_releases_no_call():
    class MissingOutcome(Harness):
        """Return no outcome for the alternative, the second proposal Watcher sees."""

        def watcher_reply(self, request: httpx.Request) -> httpx.Response:
            reply = super().watcher_reply(request)
            return httpx.Response(200, json=[]) if len(self.watcher) == 2 else reply

    harness = MissingOutcome(deny_content("secret"), [completion(call("call-b", "safe"))])
    result = await harness.run(client_request(), completion(call("call-a", "secret")))
    assert ends_asking_after_failure(result, "Watcher's decisions do not match the alternative")
    assert "tool_calls" not in message(result)


async def test_unverifiable_original_decision_withholds_the_response():
    harness = Harness(lambda _: {**outcome("allow"), "judged_decision": None}, [])
    with pytest.raises(UnverifiedDecision):
        await harness.run(client_request(), completion(call("call-a", "a")))
    assert harness.gateway == []


def test_system_notice_follows_leading_instructions_once():
    request = {
        "model": "m",
        "messages": [
            {"role": "system", "content": "One"},
            {"role": "developer", "content": "Two"},
            {"role": "user", "content": "Hi"},
            {"role": "system", "content": "Late"},
        ],
    }
    snapshot = json.loads(json.dumps(request))
    noticed = with_system_notice(request)
    assert noticed is not None and request == snapshot
    assert [item["content"] for item in noticed["messages"]] == ["One", "Two", SYSTEM_NOTICE, "Hi", "Late"]
    assert with_system_notice(noticed) is None
    first = with_system_notice({"model": "m", "messages": [{"role": "user", "content": "Hi"}]})
    assert first is not None and first["messages"][0] == {"role": "system", "content": SYSTEM_NOTICE}
    embedded = {
        "model": "m",
        "messages": [{"role": "system", "content": "Managed: " + SYSTEM_NOTICE}, {"role": "user"}],
    }
    assert with_system_notice(embedded) is None
    for malformed in ({"model": "m", "messages": "text"}, {"model": "m"}, None):
        assert with_system_notice(malformed) is None


def test_compose_without_alternative_keeps_identity_and_drops_logprobs():
    original = completion(call("call-a", "a"), content="Original")
    original["choices"][0]["logprobs"] = {"content": []}
    result = compose(original, None, "Notice", closing="Closing")
    assert message(result)["content"] == "Original\n\nNotice\n\nClosing"
    assert "logprobs" not in result["choices"][0] and "tool_calls" not in message(result)
    assert original["choices"][0]["message"]["tool_calls"]


def test_compose_rejects_unmergeable_message_fields():
    original = completion(call("call-a", "a"))
    original["choices"][0]["message"]["audio"] = {"id": "x"}
    with pytest.raises(ValueError):
        compose(original, None, "Notice")


def test_denial_notice_never_tells_the_model_to_give_up():
    from watcher_portkey.replan import denial_notice

    denial = ToolDenial(tool_use_id="a", tool_name="Write", tool_input={"x": 1}, reason="No", is_escalation=False)
    text = denial_notice([denial], cancelled=[ToolCall(tool_use_id="b", tool_name="Read", tool_input={})])
    assert "work around" not in text and "another route" not in text
    assert text.count("WATCHER NOTICE") == 2


def test_denial_notice_is_bounded_and_counts_what_it_leaves_out():
    from watcher_portkey.replan import denial_notice

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
    assert len(text.encode()) <= 64 * 1024
    shown = text.count("did not run because Watcher refused another call")
    assert text.endswith(f": 0 more refused calls and {100 - shown} more withheld calls did not run.")


async def test_withheld_ids_cover_refused_proposals_and_their_siblings_but_not_released_calls():
    """Every call of a refused proposal is withheld, including a locally refused repeat."""
    harness = Harness(
        deny_content("secret"),
        [completion(call("call-renamed", "secret")), completion(call("call-c", "safe"))],
    )
    await harness.run(client_request(), completion(call("call-a", "secret"), call("call-s", "sibling")))
    assert harness.delivery is not None and harness.delivery.withheld_ids == ["call-a", "call-s", "call-renamed"]


async def test_a_released_call_is_never_named_as_withheld_even_under_a_reused_id():
    harness = Harness(deny_content("secret"), [completion(call("call-s", "safe"))])
    await harness.run(client_request(), completion(call("call-a", "secret"), call("call-s", "sibling")))
    assert harness.delivery is not None and harness.delivery.withheld_ids == ["call-a"]


async def test_final_generation_calls_are_not_named_as_withheld():
    """Watcher never evaluated the final generation's calls, so they are not named."""
    final = completion(call("call-final", "x"), content="Should I continue?")
    harness = Harness(lambda _: outcome("escalate", "policy_gateway"), [final])
    await harness.run(client_request(), completion(call("call-a", "a")))
    assert harness.delivery is not None and harness.delivery.withheld_ids == ["call-a"]


async def record(delivery: Delivery, status: int = 200) -> list[dict]:
    """Run ``record_delivery`` against a mock Watcher and return the bodies it received."""
    sent: list[dict] = []

    def reply(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(status, json=[] if status == 200 else {"detail": "fixture failure"})

    async with AsyncWatcherClient(
        "http://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="http://watcher.invalid", transport=httpx.MockTransport(reply)),
    ) as watcher:
        await record_delivery(
            watcher,
            client_request(),
            delivery,
            conversation_id="portkey:client-exchange",
            url="/v1/chat/completions",
            provider="openai",
            user_agent="ordinary-client/1",
            timeout=5,
        )
    return sent


async def test_recording_moves_delivered_calls_into_history_so_nothing_is_graded_again():
    delivered = completion(call("call-c", "safe"), content="Notice.\n\nTrying another way.")
    (body,) = await record(Delivery(delivered, ["call-a", "call-s"]))
    assert body["request_body"]["messages"][:-1] == client_request()["messages"]
    assert body["request_body"]["messages"][-1] == delivered["choices"][0]["message"]
    reply = body["response_body"]["choices"][0]
    assert reply["message"] == {"role": "assistant", "content": None} and reply["finish_reason"] == "stop"
    assert body["external_ids"] == {"other": "portkey:client-exchange"}
    assert body["withheld_tool_use_ids"] == ["call-a", "call-s"] and body["withholds_refused_calls"] is True


async def test_recording_a_text_only_reply_sends_it_as_the_response():
    delivered = completion(content="Watcher blocked that. Shall I skip it?")
    (body,) = await record(Delivery(delivered, []))
    assert body["request_body"] == client_request() and body["response_body"] == delivered
    assert "withheld_tool_use_ids" not in body


async def test_a_failed_recording_is_logged_and_never_raised():
    with capture_logs() as logs:
        await record(Delivery(completion(content="Shall I skip it?"), ["call-a"]), status=503)
    assert [entry["event"] for entry in logs] == ["delivery_not_recorded"]
    assert logs[0]["error_type"] == "WatcherAPIError"
