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
    Gateway,
    marker_key,
    recover,
    sign_marker,
    verify_marker,
)
from watcher_agent_router.exchange import (
    Denial,
    Evaluation,
    UnsupportedExchange,
    alternative_message,
    compose,
    operation_key,
)
from watcher_agent_router.notices import ALTERNATIVE_FAILED, continuation, stop_notice

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
    assert denied["content"] == (
        "WATCHER NOTICE: Watcher blocked this call. Reason: Too risky. The call did not run. Continue the user's "
        "task another way; Watcher checks every call, so you do not need permission to try a different approach."
    )
    assert cancelled["tool_call_id"] == "call-2"
    assert cancelled["content"] == "This call did not run because Watcher refused another call in the same response."


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


async def test_approved_alternative_is_graded_in_the_clients_session():
    """Watcher already holds the refused calls' decisions there, so their refusal receipts are not taken as runs."""
    alternative = completion(("call-9", "read_file", {}), content="Reading instead")
    fakes = Fakes([alternative], [[outcome("call-9", "allow")]])
    recovery = await fakes.recover()
    assert recovery.alternative == alternative and len(recovery.notices) == 1
    assert recovery.withheld_ids == ["call-1", "call-2"]
    [sent] = fakes.gateway_requests
    assert sent.url.path == "/v1/chat/completions" and sent.headers["x-api-key"] == "gateway-key"
    assert verify_marker(KEY, sent.headers[ALTERNATIVE_HEADER], sent.content)
    asked = json.loads(sent.content)
    assert asked == continuation(REQUEST, ORIGINAL, REFUSED)
    [hook] = fakes.hooks
    assert hook["external_ids"]["other"] == CONVERSATION and hook["withholds_refused_calls"] is True
    assert hook["request_body"] == asked and hook["response_body"] == alternative
    assert hook["user_agent"] == "fixture/1.0"


@pytest.mark.parametrize(
    "content,reason",
    [(None, "stop"), ("", "stop"), (" \t\n", "stop"), ("Partial ans", "length"), ("Hidden", "content_filter")],
)
async def test_text_only_alternative_that_asks_nothing_ends_with_the_question(content, reason):
    fakes = Fakes([completion(content=content, reason=reason)], [[]])
    recovery = await fakes.recover()
    choice = recovery.alternative["choices"][0]
    assert choice["finish_reason"] == "stop" and "tool_calls" not in choice["message"]
    expected = f"{content}\n\n{ALTERNATIVE_FAILED}" if content else ALTERNATIVE_FAILED
    assert choice["message"]["content"] == expected and recovery.question == ALTERNATIVE_FAILED


async def test_complete_text_only_alternative_is_delivered_as_it_is():
    answer = completion(content="I can't do that safely; shall I skip it?")
    fakes = Fakes([answer], [[]])
    recovery = await fakes.recover()
    assert recovery.alternative == answer


async def test_alternative_with_another_success_status_is_graded():
    alternative = completion(("call-9", "read_file", {}))
    fakes = Fakes([httpx.Response(201, json=alternative)], [[outcome("call-9", "allow")]])
    recovery = await fakes.recover()
    assert recovery.alternative == alternative and len(fakes.hooks) == 1


FINAL = completion(content="Several approaches were blocked. A. skip it, B. something else?")


def outcome_from(tool_use_id: str, value: str, source: str) -> dict:
    return {**outcome(tool_use_id, value), "decision_source": source}


async def test_three_blocked_proposals_end_with_one_final_text_only_reply():
    first = completion(("call-5", "read_file", {"n": 1}))
    second = completion(("call-6", "read_file", {"n": 2}))
    fakes = Fakes([first, second, FINAL], [[outcome("call-5", "deny")], [outcome("call-6", "deny")]])
    recovery = await fakes.recover()
    assert recovery.alternative == FINAL and len(recovery.notices) == 3
    assert 'Watcher blocked `read_file {"n": 1}`' in recovery.notices[1]
    assert 'Watcher blocked `read_file {"n": 2}`' in recovery.notices[2]
    # Four model calls in all: the client's and three through the gateway; only two alternatives were graded.
    asked = [json.loads(request.content) for request in fakes.gateway_requests]
    assert len(asked) == 3 and len(fakes.hooks) == 2
    assert [request["tool_choice"] for request in asked] == ["auto", "auto", "none"]
    assert asked[1]["messages"][-1]["content"].endswith("so you do not need permission to try a different approach.")
    assert asked[2]["messages"][-1]["content"].endswith("tell the user what was blocked and ask how to proceed.")
    assert asked[2]["messages"][-2]["tool_calls"][0]["id"] == "call-6"
    assert {hook["external_ids"]["other"] for hook in fakes.hooks} == {CONVERSATION}
    assert recovery.withheld_ids == ["call-1", "call-2", "call-5", "call-6"]


@pytest.mark.parametrize(
    "source,can_approve",
    [("policy_gateway", True), ("triage", True), ("rule", False), ("threshold", False), ("grading_error", False)],
)
async def test_escalation_is_not_retried_and_asks_the_user_with_the_right_options(source, can_approve):
    escalation = Evaluation(
        verified=True,
        denials=[
            Denial(
                tool_use_id="call-1",
                tool_name="write_file",
                tool_input={"path": "a"},
                reason="Needs review",
                is_escalation=True,
                user_can_approve=can_approve,
            )
        ],
    )
    fakes = Fakes([FINAL])
    recovery = await fakes.recover(evaluation=escalation)
    assert recovery.alternative == FINAL and fakes.hooks == []
    [asked] = [json.loads(request.content) for request in fakes.gateway_requests]
    assert asked["tool_choice"] == "none"
    escalated, sibling = asked["messages"][-2:]
    assert sibling["content"] == "This call did not run because Watcher refused another call in the same response."
    if can_approve:
        assert escalated["content"].endswith("A. allow this call, B. skip it, C. do something else.")
        assert "needs the user's decision" in recovery.notices[0]
    else:
        assert escalated["content"].endswith(
            "A. skip it, B. do something else, C. ask an administrator to change the policy."
        )
        assert "allow" not in escalated["content"] and "cannot be approved in this conversation" in recovery.notices[0]


async def test_escalated_alternative_goes_straight_to_the_final_reply():
    alternative = completion(("call-5", "deploy", {}))
    fakes = Fakes([alternative, FINAL], [[outcome_from("call-5", "escalate", "triage")]])
    recovery = await fakes.recover()
    assert recovery.alternative == FINAL and len(fakes.gateway_requests) == 2 and len(fakes.hooks) == 1
    assert json.loads(fakes.gateway_requests[1].content)["tool_choice"] == "none"
    assert "WATCHER ESCALATION" in recovery.notices[1]


@pytest.mark.parametrize("can_approve,expected", [(True, "Reply A to allow"), (False, "ask an administrator")])
async def test_final_reply_that_proposes_calls_anyway_is_withheld_without_grading(can_approve, expected):
    escalation = Evaluation(
        verified=True,
        denials=[REFUSED.denials[0].model_copy(update={"is_escalation": True, "user_can_approve": can_approve})],
    )
    disobeying = completion(("call-9", "write_file", {"path": "a"}), content="Trying anyway.")
    fakes = Fakes([disobeying])
    recovery = await fakes.recover(evaluation=escalation)
    assert fakes.hooks == [], "calls proposed after the stop request are never sent to Watcher"
    message = recovery.alternative["choices"][0]["message"]
    assert "tool_calls" not in message and recovery.alternative["choices"][0]["finish_reason"] == "stop"
    assert message["content"].startswith("Trying anyway.\n\nWATCHER ESCALATION (added by Watcher")
    assert expected in message["content"]


async def test_final_reply_after_three_denials_that_proposes_calls_gets_the_cap_notice():
    fakes = Fakes(
        [completion(("c5", "t", {"n": 1})), completion(("c6", "t", {"n": 2})), completion(("c7", "t", {"n": 3}))],
        [[outcome("c5", "deny")], [outcome("c6", "deny")]],
    )
    recovery = await fakes.recover()
    assert len(fakes.hooks) == 2
    content = recovery.alternative["choices"][0]["message"]["content"]
    assert content.startswith("WATCHER NOTICE (added by Watcher") and "blocked three proposals in a row" in content


async def test_final_reply_without_tools_sends_no_tool_choice():
    request = {key: value for key, value in REQUEST.items() if key not in ("tools", "tool_choice")}
    escalation = Evaluation(verified=True, denials=[REFUSED.denials[0].model_copy(update={"is_escalation": True})])
    fakes = Fakes([FINAL])
    await fakes.recover(request=request, evaluation=escalation)
    assert "tool_choice" not in json.loads(fakes.gateway_requests[0].content)


async def test_forced_tool_choice_is_kept_for_alternatives_and_narrowed_only_for_the_final_reply():
    forced = {"type": "function", "function": {"name": "write_file"}}
    request = {**REQUEST, "tool_choice": forced, "parallel_tool_calls": False}
    fakes = Fakes(
        [completion(("c5", "write_file", {"n": 1})), completion(("c6", "write_file", {"n": 2})), FINAL],
        [[outcome("c5", "deny")], [outcome("c6", "deny")]],
    )
    await fakes.recover(request=request)
    asked = [json.loads(request.content) for request in fakes.gateway_requests]
    assert [request["tool_choice"] for request in asked] == [forced, forced, "none"]
    assert all(request["parallel_tool_calls"] is False for request in asked)


@pytest.mark.parametrize(
    "reply,reason",
    [
        (httpx.Response(502, json={}), "the provider did not return an alternative"),
        (completion(content=[{"type": "text", "text": "x"}]), "the gateway cannot verify the reply"),
    ],
)
async def test_failed_final_reply_still_puts_the_question_to_the_user(reply, reason):
    escalation = Evaluation(verified=True, denials=[REFUSED.denials[0].model_copy(update={"is_escalation": True})])
    fakes = Fakes([reply])
    recovery = await fakes.recover(evaluation=escalation)
    assert recovery.alternative is None and fakes.hooks == []
    assert recovery.notices[-2] == f"No final reply was delivered because {reason}."
    assert "Reply A to skip it" in recovery.notices[-1]


async def test_repeat_refused_from_memory_counts_toward_the_proposal_cap():
    first = completion(("call-5", "deploy", {}))
    repeat = completion(("call-6", "deploy", {}))
    fakes = Fakes([first, repeat, FINAL], [[outcome_from("call-5", "deny", "rule")]])
    # call-5 is denied; its repeat under a new ID is refused without grading and is the third refused proposal.
    recovery = await fakes.recover()
    assert len(fakes.hooks) == 1 and recovery.alternative == FINAL
    assert json.loads(fakes.gateway_requests[2].content)["tool_choice"] == "none"


async def test_repeated_refused_operation_is_refused_without_grading():
    repeat = completion(("call-7", "write_file", {"path": "a"}), ("call-8", "read_file", {}))
    approved = completion(content="I will stop here.")
    fakes = Fakes([repeat, approved], [[]])
    with structlog.testing.capture_logs() as logs:
        recovery = await fakes.recover()
    assert recovery.alternative == approved and len(fakes.hooks) == 1
    assert [entry["event"] for entry in logs] == ["alternative_repeated", "alternative_evaluated"]
    # The model sees the repeat and its refusal receipts; Watcher, which never
    # graded the repeat, does not, so it cannot record those calls as run.
    asked = json.loads(fakes.gateway_requests[1].content)
    [hook] = fakes.hooks
    assert [m.get("tool_call_id") for m in asked["messages"][-3:]] == [None, "call-7", "call-8"]
    assert hook["request_body"]["messages"] == asked["messages"][:-3]
    assert hook["external_ids"]["other"] == CONVERSATION
    assert recovery.withheld_ids == ["call-1", "call-2", "call-7", "call-8"]
    assert 'Watcher blocked `write_file {"path": "a"}`. Reason: Too risky.' in recovery.notices[1]
    assert "`read_file {}` did not run because Watcher refused another call" in recovery.notices[1]


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
    assert recovery.notices[-2:] == [f"No alternative was delivered because {reason}.", ALTERNATIVE_FAILED]


async def test_continuation_too_large_to_send_is_not_sent():
    fakes = Fakes([])
    recovery = await fakes.recover(max_body=100)
    assert fakes.gateway_requests == []
    assert recovery.notices[-2].endswith("because the conversation is too long to ask for an alternative.")


async def test_alternatives_share_the_remaining_time_limit():
    fakes = Fakes([completion(content="late")])
    fakes.delay = 5
    recovery = await fakes.recover(deadline_in=0.05)
    assert recovery.notices[-2:] == [
        "No alternative was delivered because the time limit was reached.",
        ALTERNATIVE_FAILED,
    ]
    assert recovery.question == ALTERNATIVE_FAILED


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
    assert recovery.notices[-2:] == [f"No alternative was delivered because {reason}.", ALTERNATIVE_FAILED]
    # Watcher may have recorded the alternative's call; it never reaches the client.
    assert recovery.withheld_ids == ["call-1", "call-2", "call-9"]


async def test_final_reply_shares_the_remaining_time_limit():
    escalation = Evaluation(verified=True, denials=[REFUSED.denials[0].model_copy(update={"is_escalation": True})])
    fakes = Fakes([FINAL])
    fakes.delay = 5
    recovery = await fakes.recover(evaluation=escalation, deadline_in=0.05)
    assert recovery.alternative is None
    assert recovery.notices[-2] == "No final reply was delivered because the time limit was reached."


@pytest.mark.parametrize(
    "final",
    [
        completion(content=None),
        completion(content=""),
        completion(content="Should I", reason="length"),
        completion(content="Should I", reason="content_filter"),
    ],
    ids=["no-text", "empty", "cut-off", "filtered"],
)
async def test_final_reply_that_asks_nothing_gets_the_fixed_question(final):
    escalation = Evaluation(
        verified=True,
        denials=[REFUSED.denials[0].model_copy(update={"is_escalation": True, "user_can_approve": True})],
    )
    fakes = Fakes([final])
    recovery = await fakes.recover(evaluation=escalation)
    choice = recovery.alternative["choices"][0]
    assert choice["finish_reason"] == "stop" and fakes.hooks == []
    assert choice["message"]["content"].endswith("B to skip it, or C to do something else.")


async def test_complete_final_reply_without_a_question_gets_the_fixed_question():
    """A final reply that only reports what happened would end the turn without asking the user anything."""
    report = completion(content="Two approaches were blocked, so I stopped.", reason="stop")
    first = completion(("call-5", "read_file", {"n": 1}))
    second = completion(("call-6", "read_file", {"n": 2}))
    fakes = Fakes([first, second, report], [[outcome("call-5", "deny")], [outcome("call-6", "deny")]])
    recovery = await fakes.recover()
    choice = recovery.alternative["choices"][0]
    assert choice["finish_reason"] == "stop" and "tool_calls" not in choice["message"]
    assert choice["message"]["content"] == (
        "Two approaches were blocked, so I stopped.\n\n" + stop_notice(REFUSED.denials)
    )


async def test_complete_final_reply_that_already_asks_is_left_unchanged():
    """A reply that puts its own question to the user is not asked twice."""
    asking = completion(content="Both reads were blocked. Should I skip them or try another file?", reason="stop")
    first = completion(("call-5", "read_file", {"n": 1}))
    second = completion(("call-6", "read_file", {"n": 2}))
    fakes = Fakes([first, second, asking], [[outcome("call-5", "deny")], [outcome("call-6", "deny")]])
    recovery = await fakes.recover()
    assert recovery.alternative == asking
