"""Ask for alternatives through a running ``aigw`` gateway after Watcher refuses a proposal.

Set ``AIGW_BIN`` to run. Runs in its own module because the processor here has
``GATEWAY_URL`` set, and only one ``aigw`` gateway can run at a time. The
simulated Watcher reads its verdicts from the prompt's words: the first for the
client's exchange, the next for each alternative.
"""

import sys
from collections.abc import Iterator

import openai
import pytest
from aigw_support import AIGW, Fixture, Provider, SimulatedWatcher, ask, client, running_gateway, wait_for_recording
from watcher_agent_router.notices import ALTERNATIVE_FAILED, SYSTEM_NOTICE

pytestmark = pytest.mark.skipif(not AIGW, reason="Set AIGW_BIN to an aigw binary to run native gateway tests")


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict]:
    provider, watcher = Fixture(Provider), Fixture(SimulatedWatcher)
    serve = [sys.executable, "-m", "watcher_agent_router.processor", "serve", "--address"]
    watcher_url = f"http://127.0.0.1:{watcher.server_port}"
    try:
        with running_gateway(
            tmp_path_factory.mktemp("aigw"), provider, watcher_url, "fixture-key", serve, alternatives=True
        ) as urls:
            yield {**urls, "provider": provider, "watcher": watcher}
    finally:
        provider.shutdown()
        watcher.shutdown()


def test_refused_proposal_is_replaced_by_an_approved_alternative(stack: dict) -> None:
    hooks_before, provider_before = len(stack["watcher"].requests), len(stack["provider"].requests)
    raw = ask(stack, "deny allow tool request")
    choice = raw.parse().choices[0]
    assert choice.finish_reason == "tool_calls"
    [call] = choice.message.tool_calls
    assert call.id == "call-alternative-1" and call.function.arguments == '{"attempt": 1}'
    content = choice.message.content
    assert content.startswith("WATCHER NOTICE (added by Watcher, not written by the assistant): Watcher blocked")
    assert content.endswith("\n\nAlternative 1.")
    original, alternative = (hook for _path, _headers, hook in stack["watcher"].requests[hooks_before:])
    # Both are graded in the client request's session, where the refused call already has its decision.
    conversation = {"other": raw.headers["x-watcher-conversation-id"]}
    assert original["external_ids"] == alternative["external_ids"] == conversation
    assert original["withholds_refused_calls"] is alternative["withholds_refused_calls"] is True
    # The delivered reply is recorded afterwards, naming the refused proposal's call.
    recording = wait_for_recording(stack, conversation)
    assert recording["withheld_tool_use_ids"] == ["call-deny"]
    assert recording["request_body"]["messages"][-1]["tool_calls"][0]["id"] == "call-alternative-1"
    # The provider and Watcher both saw the client's request with Watcher's notice ahead of it.
    [(_, _, first), (_, headers, body)] = stack["provider"].requests[provider_before:]
    assert first["messages"][0] == {"role": "system", "content": SYSTEM_NOTICE}
    assert original["request_body"] == first
    roles = [message["role"] for message in alternative["request_body"]["messages"]]
    assert roles == ["system", "user", "assistant", "tool"] and alternative["request_body"]["stream"] is False
    assert alternative["request_body"]["messages"][-1]["content"].endswith("try a different approach.")
    # The alternative reached the provider like any client request, without the processor's marker.
    lowered = {key.lower(): value for key, value in headers.items()}
    assert body == alternative["request_body"]
    assert lowered["authorization"] == "Bearer fixture-provider-key"
    assert "x-watcher-alternative" not in lowered and "x-api-key" not in lowered


def test_three_blocked_proposals_end_with_one_final_text_reply(stack: dict) -> None:
    hooks_before, provider_before = len(stack["watcher"].requests), len(stack["provider"].requests)
    choice = ask(stack, "deny deny deny tool request").parse().choices[0]
    assert choice.finish_reason == "stop" and not choice.message.tool_calls
    assert choice.message.content.count("WATCHER NOTICE (added by Watcher") == 3
    assert choice.message.content.endswith("Blocked. A. skip it, B. something else?")
    asked = [body for _path, _headers, body in stack["provider"].requests[provider_before:]]
    assert len(asked) == 4, "the client's call, two alternatives and the final reply"
    assert [request.get("tool_choice") for request in asked] == [None, None, None, "none"]
    assert len(stack["watcher"].requests) == hooks_before + 3, "the final reply is not graded"


@pytest.mark.parametrize(
    "verdict,offer",
    [("graded", "A. allow this call"), ("escalate", "A. skip it, B. do something else, C. ask an administrator")],
)
def test_escalation_is_not_retried_and_the_final_reply_asks_the_user(stack: dict, verdict: str, offer: str) -> None:
    hooks_before, provider_before = len(stack["watcher"].requests), len(stack["provider"].requests)
    choice = ask(stack, f"{verdict} tool request").parse().choices[0]
    assert choice.finish_reason == "stop" and not choice.message.tool_calls
    assert choice.message.content.startswith("WATCHER ESCALATION (added by Watcher")
    assert choice.message.content.endswith("Blocked. A. skip it, B. something else?")
    asked = [body for _path, _headers, body in stack["provider"].requests[provider_before:]]
    assert len(asked) == 2 and asked[1]["tool_choice"] == "none"
    assert offer in asked[1]["messages"][-1]["content"]
    assert len(stack["watcher"].requests) == hooks_before + 1


def test_final_reply_that_proposes_a_call_anyway_is_withheld(stack: dict) -> None:
    hooks_before = len(stack["watcher"].requests)
    choice = ask(stack, "escalate disobey tool request").parse().choices[0]
    assert choice.finish_reason == "stop" and not choice.message.tool_calls
    assert choice.message.content.endswith("C to ask an administrator to change the policy.")
    assert len(stack["watcher"].requests) == hooks_before + 1, "the withheld call was never graded"


def test_streamed_refusal_continues_with_an_approved_alternative(stack: dict) -> None:
    stream = client(stack).chat.completions.create(
        model="fixture-model",
        messages=[{"role": "user", "content": "deny allow tool request"}],
        tools=[{"type": "function", "function": {"name": "delete_file", "parameters": {"type": "object"}}}],
        stream=True,
    )
    chunks = [item for item in stream if item.choices]
    text = "".join(item.choices[0].delta.content or "" for item in chunks)
    assert text.startswith("Working on it. \n\nWATCHER NOTICE (added by Watcher") and text.endswith(
        "\n\nAlternative 1."
    )
    calls = [call for item in chunks for call in item.choices[0].delta.tool_calls or []]
    assert [call.id for call in calls] == ["call-alternative-1"]
    assert chunks[-1].choices[0].finish_reason == "tool_calls"


def test_streamed_escalation_ends_with_the_final_reply(stack: dict) -> None:
    stream = client(stack).chat.completions.create(
        model="fixture-model",
        messages=[{"role": "user", "content": "graded tool request"}],
        tools=[{"type": "function", "function": {"name": "delete_file", "parameters": {"type": "object"}}}],
        stream=True,
    )
    chunks = [item for item in stream if item.choices]
    text = "".join(item.choices[0].delta.content or "" for item in chunks)
    assert text.startswith("Working on it. \n\nWATCHER ESCALATION (added by Watcher")
    assert text.endswith("Blocked. A. skip it, B. something else?")
    assert not [call for item in chunks for call in item.choices[0].delta.tool_calls or []]
    assert chunks[-1].choices[0].finish_reason == "stop"


def test_client_cannot_skip_grading_with_a_marker(stack: dict) -> None:
    before = len(stack["provider"].requests)
    forged = client(stack).with_options(
        default_headers={"x-api-key": "fixture-gateway-key", "x-watcher-alternative": "9999999999.00"}
    )
    with pytest.raises(openai.PermissionDeniedError):
        forged.chat.completions.create(
            model="fixture-model", messages=[{"role": "user", "content": "allow tool request"}]
        )
    assert len(stack["provider"].requests) == before


def test_compressed_alternative_is_refused_before_agent_router_decodes_it(stack: dict) -> None:
    before = len(stack["watcher"].requests)
    choice = ask(stack, "deny zipped tool request").parse().choices[0]
    assert choice.finish_reason == "stop" and not choice.message.tool_calls
    assert choice.message.content.endswith(
        "No alternative was delivered because the provider did not return an alternative.\n\n" + ALTERNATIVE_FAILED
    )
    assert len(stack["watcher"].requests) == before + 1, "the compressed alternative was never graded"
