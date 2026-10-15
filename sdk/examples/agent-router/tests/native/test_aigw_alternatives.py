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
from aigw_support import AIGW, Fixture, Provider, SimulatedWatcher, ask, client, running_gateway

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
    assert content.startswith("Watcher did not approve") and content.endswith("\n\nAlternative 1.")
    assert '"tool_use_id": "call-deny"' in content
    original, alternative = (hook for _path, _headers, hook in stack["watcher"].requests[hooks_before:])
    assert original["external_ids"] == {"other": raw.headers["x-watcher-conversation-id"]}
    assert alternative["external_ids"]["other"].startswith("agent-router:")
    assert alternative["external_ids"]["other"] != original["external_ids"]["other"]
    roles = [message["role"] for message in alternative["request_body"]["messages"]]
    assert roles == ["user", "assistant", "tool"] and alternative["request_body"]["stream"] is False
    # The alternative reached the provider like any client request, without the processor's marker.
    _path, headers, body = stack["provider"].requests[-1]
    lowered = {key.lower(): value for key, value in headers.items()}
    assert len(stack["provider"].requests) == provider_before + 2 and body == alternative["request_body"]
    assert lowered["authorization"] == "Bearer fixture-provider-key"
    assert "x-watcher-alternative" not in lowered and "x-api-key" not in lowered


def test_three_blocked_proposals_end_with_the_notices(stack: dict) -> None:
    before = len(stack["watcher"].requests)
    choice = ask(stack, "deny deny escalate tool request").parse().choices[0]
    assert choice.finish_reason == "stop" and not choice.message.tool_calls
    assert choice.message.content.endswith("Watcher stopped after three blocked proposals.")
    for identifier in ("call-deny", "call-alternative-1", "call-alternative-2"):
        assert f'"tool_use_id": "{identifier}"' in choice.message.content
    assert len(stack["watcher"].requests) == before + 3


def test_streamed_refusal_continues_with_an_approved_alternative(stack: dict) -> None:
    stream = client(stack).chat.completions.create(
        model="fixture-model",
        messages=[{"role": "user", "content": "deny allow tool request"}],
        tools=[{"type": "function", "function": {"name": "delete_file", "parameters": {"type": "object"}}}],
        stream=True,
    )
    chunks = [item for item in stream if item.choices]
    text = "".join(item.choices[0].delta.content or "" for item in chunks)
    assert text.startswith("Working on it. \n\nWatcher did not approve") and text.endswith("\n\nAlternative 1.")
    calls = [call for item in chunks for call in item.choices[0].delta.tool_calls or []]
    assert [call.id for call in calls] == ["call-alternative-1"]
    assert chunks[-1].choices[0].finish_reason == "tool_calls"


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
        "No alternative was delivered because the provider did not return an alternative."
    )
    assert len(stack["watcher"].requests) == before + 1, "the compressed alternative was never graded"
