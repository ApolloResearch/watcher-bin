"""Exercise the public SDK contract the processor applies to each exchange."""

import copy
import json

import httpx
import pytest
from watcher_agent_router.exchange import (
    Denial,
    Evaluation,
    UnsupportedExchange,
    compose,
    decode_json,
    evaluate,
    refused,
    releasable,
    validate_request,
    withheld_notice,
)

from watcher_sdk import AsyncWatcherClient

CONVERSATION = "agent-router:fixture-exchange"


def watcher(handler) -> AsyncWatcherClient:
    """Return an SDK client whose HTTP requests go to ``handler`` instead of a server."""
    return AsyncWatcherClient(
        "http://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="http://watcher.invalid", transport=httpx.MockTransport(handler)),
    )


@pytest.fixture
async def forbidden_watcher():
    """Fail any test whose invalid input reaches the Watcher API."""
    async with watcher(lambda request: pytest.fail("Invalid input reached Watcher")) as client:
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


def outcome(mode: str = "enforce", decision: str = "allow", judged: str | None = "allow", **extra) -> dict:
    return {
        "tool_use_id": "native-call-1",
        "decision": decision,
        "judged_decision": judged,
        "decision_source": "bypass" if mode == "paused" else "rule",
        "enforcement_mode": mode,
        "verdict": {},
        "latency_ms": 1,
        **extra,
    }


@pytest.mark.parametrize(
    "mode,decision,judged,expected",
    [
        ("enforce", "allow", "allow", True),
        ("enforce", "deny", "deny", False),
        ("enforce", "escalate", "escalate", False),
        ("observe", "deferred", "deny", True),
        ("paused", "deferred", None, True),
    ],
)
async def test_raw_exchange_and_decisions(exchange, mode, decision, judged, expected):
    """Send the original bodies unchanged and apply the server's decision."""
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        assert request.url.path == "/v1/hooks/pre-tool-use"
        assert body["format"] == "raw" and body["url"] == "/v1/chat/completions" and body["provider"] == "openai"
        assert body["request_body"] == exchange[0] and body["response_body"] == exchange[1]
        assert body["external_ids"] == {"other": CONVERSATION}
        assert body["user_agent"] == "fixture-agent/1.0"
        assert body.get("settings_overrides") is None
        arguments = json.loads(body["response_body"]["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])
        assert type(arguments["number"]) is int and type(arguments["float"]) is float
        return httpx.Response(200, json=[outcome(mode, decision, judged)])

    async with watcher(handler) as client:
        result = await evaluate(client, *exchange, conversation_id=CONVERSATION, user_agent="fixture-agent/1.0")
    assert result.verified and (not result.denials) is expected and len(seen) == 1
    if not expected:
        [denial] = result.denials
        assert denial.tool_use_id == "native-call-1" and denial.tool_name == "write_file"
        assert denial.tool_input == {"number": 1, "float": 1.0, "boolean": True, "null": None}
        assert denial.is_escalation is (decision == "escalate")


@pytest.mark.parametrize(
    "result",
    [
        [],
        [outcome(tool_use_id="other")],
        [outcome(), outcome()],
        [{"status_code": 503, "detail": "unavailable", "tool_use_id": "native-call-1"}],
    ],
)
async def test_missing_mismatched_duplicate_or_error_outcome_withholds(exchange, result):
    async with watcher(lambda _: httpx.Response(200, json=result)) as client:
        assert not (await evaluate(client, *exchange, conversation_id=CONVERSATION)).verified


async def test_text_only_response_is_submitted_and_released(exchange):
    request, _ = exchange
    response = {"choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}]}
    async with watcher(lambda _: httpx.Response(200, json=[])) as client:
        result = await evaluate(client, request, response, conversation_id=CONVERSATION)
        assert result.verified and not result.denials


async def test_non_list_result_withholds(exchange, monkeypatch):
    async with watcher(lambda _: pytest.fail("not called")) as client:

        async def single(**_kwargs):
            return object()

        monkeypatch.setattr(client, "pre_tool_use_hook", single)
        assert not (await evaluate(client, *exchange, conversation_id=CONVERSATION)).verified


@pytest.mark.parametrize(
    "value,expected",
    [
        (outcome(), True),
        (outcome(decision="deferred"), False),
        (outcome(decision_source="unknown"), False),
        (outcome("observe", "deferred", None), False),
        (outcome("paused", "deferred", "allow"), False),
        (outcome(grading_error={"code": "timeout", "message": "slow"}), False),
        (outcome(decision_source="grading_error", grading_error={"code": "timeout", "message": "slow"}), True),
        (outcome(decision_source="grading_error", grading_error={"code": "invented", "message": "x"}), False),
        (outcome(decision_source="grading_error", grading_error=None), False),
    ],
)
def test_releasable_requires_consistent_provenance(value, expected):
    assert releasable(value) is expected


@pytest.mark.parametrize(
    "change",
    [
        {"model": ""},
        {"stream": "false"},
        {"n": 2},
        {"n": True},
        {"functions": []},
        {"previous_response_id": "hidden"},
        {"modalities": ["text", "audio"]},
        {"modalities": 1},
        {"modalities": "audio"},
        {"tools": [{"type": "custom"}]},
        {"tools": {}},
        {"messages": []},
        {"messages": ["not an object"]},
    ],
)
def test_unsupported_requests_rejected_before_provider(exchange, change):
    request, _ = exchange
    request.update(change)
    with pytest.raises(UnsupportedExchange):
        validate_request(request)


def test_null_options_are_accepted(exchange):
    request, _ = exchange
    request.update(modalities=None, tools=[], stream=False)
    validate_request(request)


def test_non_object_request_rejected():
    with pytest.raises(UnsupportedExchange):
        validate_request([])


def _withhold(response: dict, evaluation: Evaluation) -> dict:
    """The response a client receives for a refusal with no alternative."""
    return compose(response, withheld_notice(response, evaluation), None)


def _call(response: dict) -> dict:
    return response["choices"][0]["message"]["tool_calls"][0]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(choices=[]),
        lambda r: r.update(choices=["text"]),
        lambda r: r["choices"][0].update(index=1),
        lambda r: r["choices"][0].update(message={"role": "user"}),
        lambda r: r["choices"][0]["message"].update(function_call={"name": "x"}),
        lambda r: r["choices"][0]["message"].update(tool_calls={}),
        lambda r: r["choices"][0].update(finish_reason="length"),
        lambda r: r["choices"][0].update(finish_reason="unknown"),
        lambda r: _call(r).update(type="custom"),
        lambda r: _call(r).update(id=""),
        lambda r: _call(r).update(id=1),
        lambda r: _call(r).update(function="write_file"),
        lambda r: _call(r)["function"].update(name=""),
        lambda r: _call(r)["function"].update(arguments={"already": "parsed"}),
        lambda r: _call(r)["function"].update(arguments='{"x":1,"x":2}'),
        lambda r: _call(r)["function"].update(arguments='{"x":NaN}'),
        lambda r: _call(r)["function"].update(arguments="[]"),
        lambda r: _call(r)["function"].update(arguments="not json"),
        lambda r: r["choices"][0]["message"]["tool_calls"].append(copy.deepcopy(_call(r))),
    ],
)
async def test_unverifiable_responses_never_reach_watcher(exchange, mutate, forbidden_watcher):
    request, response = exchange
    mutate(response)
    with pytest.raises(UnsupportedExchange):
        await evaluate(forbidden_watcher, request, response, conversation_id=CONVERSATION)


@pytest.mark.parametrize("identifier", ["fixture", "agent-router:", "Agent-Router:x", "kong:exchange", None])
async def test_conversation_id_requires_documented_prefix(exchange, identifier, forbidden_watcher):
    with pytest.raises(UnsupportedExchange):
        await evaluate(forbidden_watcher, *exchange, conversation_id=identifier)


@pytest.mark.parametrize("value", ['{"a":1,"a":2}', b"\xff", "{", '{"n": ' + "9" * 5000 + "}"])
def test_decode_json_rejects_ambiguous_or_invalid_input(value):
    with pytest.raises(UnsupportedExchange):
        decode_json(value)


def test_decode_json_translates_recursion_errors(monkeypatch):
    """Nesting deep enough to exhaust the interpreter's recursion limit is invalid input, not a crash.

    How deep that is depends on the interpreter and its stack size, so the
    decoder is made to fail directly rather than with a fixed nesting depth.
    """

    def too_deep(*_args, **_kwargs):
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(json, "loads", too_deep)
    with pytest.raises(UnsupportedExchange) as raised:
        decode_json("[[]]")
    assert isinstance(raised.value.__cause__, RecursionError)


@pytest.mark.parametrize(
    "value,expected",
    [
        (outcome(decision="deny", judged="deny"), True),
        (outcome(decision="escalate", judged="escalate"), True),
        (outcome(decision="deny", judged="allow"), False),
        (outcome("observe", "deferred", "deny"), False),
        (outcome(decision="deny", judged="deny", decision_source="unknown"), False),
        (outcome(decision="deny", judged="deny", grading_error={"code": "timeout", "message": "x"}), False),
        (
            outcome(
                decision="deny",
                judged="deny",
                decision_source="grading_error",
                grading_error={"code": "timeout", "message": "Grading timed out"},
            ),
            True,
        ),
    ],
)
def test_refused_requires_a_consistent_enforced_refusal(value, expected):
    assert refused(value) is expected


@pytest.mark.parametrize(
    "extra,reason",
    [
        ({"verdict": {"explanation": "Deletes user data", "summary": "risky"}}, "Deletes user data"),
        ({"verdict": {"summary": "risky"}}, "risky"),
        ({"verdict": {}}, "Watcher did not give a reason."),
        (
            {"decision_source": "grading_error", "grading_error": {"code": "timeout", "message": "Grading timed out"}},
            "Grading timed out",
        ),
    ],
)
async def test_denial_reason_is_watchers_public_explanation(exchange, extra, reason):
    value = outcome(decision="deny", judged="deny") | extra
    async with watcher(lambda _: httpx.Response(200, json=[value])) as client:
        result = await evaluate(client, *exchange, conversation_id=CONVERSATION)
    assert result.denials[0].reason == reason


def test_withheld_response_removes_every_call_and_explains_in_text(exchange):
    _, response = exchange
    response["choices"][0]["message"]["content"] = "Let me write it."
    response["choices"][0]["message"]["tool_calls"].append(
        {"type": "function", "id": "native-call-2", "function": {"name": "read_file", "arguments": "{}"}}
    )
    denial = Denial(
        tool_use_id="native-call-1", tool_name="write_file", tool_input={}, reason="No", is_escalation=False
    )
    withheld = _withhold(response, Evaluation(verified=True, denials=[denial]))
    choice = withheld["choices"][0]
    assert choice["finish_reason"] == "stop" and "tool_calls" not in choice["message"]
    content = choice["message"]["content"]
    assert content.startswith("Let me write it.\n\nWatcher did not approve")
    assert '"reason": "No"' in content and '["native-call-2"]' in content
    assert response["choices"][0]["message"]["tool_calls"], "the original response is not modified"


def test_withheld_response_without_prior_text(exchange):
    _, response = exchange
    denial = Denial(tool_use_id="native-call-1", tool_name="write_file", tool_input={}, reason="No", is_escalation=True)
    content = _withhold(response, Evaluation(verified=True, denials=[denial]))["choices"][0]["message"]["content"]
    assert content.startswith("Watcher did not approve") and "were withheld because" not in content


async def test_inconsistent_outcome_is_neither_released_nor_refused(exchange):
    value = outcome(decision="deny", judged="allow")
    async with watcher(lambda _: httpx.Response(200, json=[value])) as client:
        assert not (await evaluate(client, *exchange, conversation_id=CONVERSATION)).verified


def two_call_exchange(exchange):
    request, response = exchange
    response["choices"][0]["message"]["tool_calls"].append(
        {"type": "function", "id": "native-call-2", "function": {"name": "read_file", "arguments": "{}"}}
    )
    return request, response


async def test_one_refused_call_withholds_its_allowed_sibling(exchange):
    request, response = two_call_exchange(exchange)
    decisions = [outcome(decision="deny", judged="deny"), outcome(tool_use_id="native-call-2")]
    async with watcher(lambda _: httpx.Response(200, json=decisions)) as client:
        result = await evaluate(client, request, response, conversation_id=CONVERSATION)
    assert result.verified and [denial.tool_use_id for denial in result.denials] == ["native-call-1"]
    message = _withhold(response, result)["choices"][0]["message"]
    assert "tool_calls" not in message and '["native-call-2"]' in message["content"]


async def test_refusal_with_a_missing_sibling_decision_is_unverified(exchange):
    request, response = two_call_exchange(exchange)
    async with watcher(lambda _: httpx.Response(200, json=[outcome(decision="deny", judged="deny")])) as client:
        assert not (await evaluate(client, request, response, conversation_id=CONVERSATION)).verified


def test_long_arguments_and_reasons_are_shortened_in_the_notice():
    from watcher_agent_router.exchange import denial_notice

    big = Denial(
        tool_use_id="a", tool_name="t", tool_input={"text": "é" * 20_000}, reason="r" * 9000, is_escalation=False
    )
    notice = denial_notice([big], [])
    shown = json.loads(notice.split("\n\n", 1)[1])[0]
    assert (
        set(shown["tool_input"]) == {"truncated_arguments"} and len(shown["tool_input"]["truncated_arguments"]) == 4096
    )
    assert len(shown["reason"]) == 4096


def test_notice_counts_calls_past_its_size_limit():
    from watcher_agent_router.exchange import denial_notice

    denials = [
        Denial(tool_use_id=f"id-{index}", tool_name="t", tool_input={"x": "y" * 3000}, reason="no", is_escalation=False)
        for index in range(40)
    ]
    notice = denial_notice(denials, [f"c-{index}" for index in range(150)])
    assert len(notice.encode()) < 80 * 1024
    assert "more refused tool calls were withheld." in notice and "and 50 more." in notice
