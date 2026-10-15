"""Send gateway traffic through a real Watcher API and read it back with the SDK.

Set ``AIGW_BIN`` and ``WATCHER_LIVE_BASE_URL`` to run; ``WATCHER_LIVE_API_KEY``
may be empty for a local development server that accepts unauthenticated
requests. The model provider is still a local simulation, and grading follows
the server's own policy and models, so the test checks that delivery matches
the decision Watcher stored rather than requiring a particular decision.
"""

import asyncio
import os
import sys
from collections.abc import Iterator

import openai
import pytest
from aigw_support import AIGW, DANGEROUS, Fixture, Provider, ask, client, running_gateway

from watcher_sdk import AsyncWatcherClient, TrajectoryView

LIVE_URL = os.environ.get("WATCHER_LIVE_BASE_URL")
pytestmark = pytest.mark.skipif(
    not (AIGW and LIVE_URL), reason="Set AIGW_BIN and WATCHER_LIVE_BASE_URL to test against a real Watcher API"
)


@pytest.fixture(scope="module")
def live_stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict]:
    """Run the gateway against a real Watcher API named by ``WATCHER_LIVE_BASE_URL``.

    ``WATCHER_LIVE_API_KEY`` may be empty for a local development server that
    accepts unauthenticated requests; the processor is then started directly
    because the CLI requires a key.
    """
    key = os.environ.get("WATCHER_LIVE_API_KEY", "")
    serve = [
        sys.executable,
        "-c",
        "import asyncio, os, sys; from watcher_agent_router import processor; asyncio.run(processor._serve("
        "sys.argv[1], os.environ['WATCHER_BASE_URL'], os.environ['WATCHER_API_KEY'],"
        " os.environ['GATEWAY_API_KEY'], asyncio.Event()))",
    ]
    provider = Fixture(Provider)
    try:
        with running_gateway(tmp_path_factory.mktemp("live"), provider, LIVE_URL, key, serve) as urls:
            yield {**urls, "key": key}
    finally:
        provider.shutdown()


async def _stored(stack: dict, conversation: str, decision_id: str | None = None) -> tuple[dict, dict]:
    """Poll the public API until the session, trajectory and any named decision are readable.

    Watcher records after acknowledging the hook, so a readable trajectory can
    precede its decision record.
    """
    async with AsyncWatcherClient(str(LIVE_URL), api_key=stack["key"] or None) as watcher:
        for _ in range(60):
            found = (await watcher.search_sessions(external_ids={"other": [conversation]})).to_dict()
            if found["sessions"] and found["sessions"][0]["latest_trajectory_id"]:
                session = found["sessions"][0]
                trajectory = await watcher.get_trajectory(
                    session["session_id"], session["latest_trajectory_id"], view=TrajectoryView.EXTENDED
                )
                stored = trajectory.to_dict()
                if decision_id is None or decision_id in (stored.get("tool_call_decisions") or {}):
                    return session, stored
            await asyncio.sleep(1)
    pytest.fail(f"Watcher never stored {conversation}")


async def test_live_text_exchange_is_stored_as_a_gateway_session(live_stack: dict) -> None:
    raw = client(live_stack).chat.completions.with_raw_response.create(
        model="fixture-model", messages=[{"role": "user", "content": "hello there"}]
    )
    session, trajectory = await _stored(live_stack, raw.headers["x-watcher-conversation-id"])
    assert session["sources"] == ["watcher-gateway"]
    assert [message["role"] for message in trajectory["messages"]] == ["user", "assistant"]


async def test_live_delivery_matches_the_stored_decision(live_stack: dict) -> None:
    """A dangerous call is delivered only if the real backend stored an allowing decision."""
    raw = ask(live_stack, "danger please clean up my machine")
    conversation = raw.headers["x-watcher-conversation-id"]
    message = raw.parse().choices[0].message
    delivered = bool(message.tool_calls)
    if not delivered:
        assert message.content.startswith("Watcher did not approve")
    _session, trajectory = await _stored(live_stack, conversation, "call-danger")
    decision = trajectory["tool_call_decisions"]["call-danger"]
    assert decision["raw_tool_call"]["tool_input"] == {"command": DANGEROUS}
    assert delivered == (decision["applied_decision"] in {"allow", "deferred"}), decision["applied_decision"]


async def test_live_streamed_delivery_matches_the_stored_decision(live_stack: dict) -> None:
    """A streamed tool call reaches the client only if the real backend stored an allowing decision."""
    received: list = []
    try:
        stream = client(live_stack).chat.completions.with_raw_response.create(
            model="fixture-model",
            messages=[{"role": "user", "content": "stream tool request"}],
            tools=[{"type": "function", "function": {"name": "delete_file", "parameters": {"type": "object"}}}],
            stream=True,
        )
        conversation = stream.headers["x-watcher-conversation-id"]
        received.extend(stream.parse())
    except openai.APIError:
        pass
    delivered = any(item.choices and item.choices[0].delta.tool_calls for item in received)
    _session, trajectory = await _stored(live_stack, conversation, "call-stream")
    decision = trajectory["tool_call_decisions"]["call-stream"]
    assert decision["raw_tool_call"]["tool_input"] == {"path": "notes.txt"}
    assert delivered == (decision["applied_decision"] in {"allow", "deferred"}), decision["applied_decision"]
