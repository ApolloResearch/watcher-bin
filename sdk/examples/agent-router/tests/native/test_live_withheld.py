"""Check what a real Watcher API records about calls the processor withheld after a refusal.

Set ``AIGW_BIN`` and ``WATCHER_LIVE_BASE_URL`` to run, as for ``test_live_api``.
The organization's command rules are replaced for the module, so decisions are
deterministic and need no model: ``write_file`` is always denied and
``read_file`` always allowed. The previous settings are restored afterwards.

After a refusal the processor asks the model for an alternative, whose request
repeats the refused proposal with the processor's refusal receipts as tool
results. Watcher records a call it first sees with a result as having run,
unless the session already holds a decision for it. These tests read every
session stored during the case and require that neither the refused call, its
withheld sibling, nor a locally refused repeat was recorded as having run.
"""

import asyncio
import json
import os
import sys
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler
from uuid import uuid4

import pytest
from aigw_support import AIGW, Fixture, client, read_json, reply, running_gateway
from openai.types.chat import ChatCompletion
from watcher_agent_router.exchange import submit

from watcher_sdk import AsyncWatcherClient, TrajectoryView

LIVE_URL = os.environ.get("WATCHER_LIVE_BASE_URL")
pytestmark = pytest.mark.skipif(
    not (AIGW and LIVE_URL), reason="Set AIGW_BIN and WATCHER_LIVE_BASE_URL to test against a real Watcher API"
)

SETTINGS = """\
enforcement:
  permission: locked
  mode: enforce
command_rules:
  rules:
  - id: fixture-deny-write
    tool_name: write_file
    name: Deny fixture writes
    category: file_directory
    regex: .*
    decision: deny
    priority: 1
  - id: fixture-allow-read
    tool_name: read_file
    name: Allow fixture reads
    category: file_directory
    regex: .*
    decision: allow
    priority: 2
"""
HISTORY_ONLY = "history_only"


def _call(call_id: str, name: str, arguments: dict) -> dict:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


class WithheldProvider(BaseHTTPRequestHandler):
    """OpenAI-compatible fixture for the withheld-call cases; the first user message holds the case token.

    The client's request is answered with a refused ``write_file`` call and a
    ``read_file`` sibling. The first alternative is an allowed ``read_file``
    call, or, when the token contains ``repeat``, the refused write again under
    new call IDs, which the processor refuses without asking Watcher; the next
    alternative is then a question in text.
    """

    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *_args: object) -> None:
        pass

    def do_POST(self) -> None:
        request = read_json(self)
        token = next(message for message in request["messages"] if message["role"] == "user")["content"]
        proposals = sum(message["role"] == "assistant" for message in request["messages"])
        if proposals == 0:
            calls = [_call(f"{token}-refused", "write_file", {"path": "a"}), _call(f"{token}-sibling", "read_file", {})]
        elif proposals == 1 and "repeat" in token:
            calls = [
                _call(f"{token}-repeat", "write_file", {"path": "a"}),
                _call(f"{token}-repeat-sibling", "read_file", {}),
            ]
        elif proposals == 1:
            calls = [_call(f"{token}-alternative", "read_file", {"path": "b"})]
        else:
            calls = []
        message: dict = {"role": "assistant", "content": "Shall I stop here?" if not calls else None}
        if calls:
            message["tool_calls"] = calls
        choice = {"index": 0, "message": message, "finish_reason": "tool_calls" if calls else "stop"}
        reply(self, 200, {"id": "chatcmpl-withheld", "object": "chat.completion", "choices": [choice]})


async def _await_rules(key: str | None) -> None:
    """Wait until Watcher applies the fixture rules: it caches each organization's policy for up to a minute.

    A probe exchange proposing ``write_file`` is sent under its own
    conversation ID until the rule denies it.
    """
    probe = {
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": None, "tool_calls": [_call("probe", "write_file", {})]},
            }
        ]
    }
    async with AsyncWatcherClient(str(LIVE_URL), api_key=key) as watcher:
        for _ in range(90):
            request = {"model": "fixture-model", "messages": [{"role": "user", "content": "settings probe"}]}
            outcomes = await submit(
                watcher, request, probe, conversation_id=f"agent-router:probe-{uuid4()}", user_agent=None
            )
            if [outcome.to_dict().get("decision_source") for outcome in outcomes] == ["rule"]:
                return
            await asyncio.sleep(1)
    pytest.fail("Watcher never applied the fixture rules")


async def _replace_settings(key: str | None, yaml: str) -> str:
    """Save ``yaml`` as the organization's settings and return the YAML it replaced (``{}`` when there was none)."""
    async with AsyncWatcherClient(str(LIVE_URL), api_key=key) as watcher:
        current = (await watcher.get_org_managed_settings()).to_dict()
        await watcher.update_org_managed_settings(yaml, expected_version=current["version"])
        return current.get("yaml") or "{}\n"


@pytest.fixture(scope="module")
def withheld_stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict]:
    """Run the gateway, with alternatives, against the real Watcher API under deterministic rules."""
    key = os.environ.get("WATCHER_LIVE_API_KEY", "")
    serve = [
        sys.executable,
        "-c",
        "import asyncio, os, sys; from watcher_agent_router import processor; asyncio.run(processor._serve("
        "sys.argv[1], os.environ['WATCHER_BASE_URL'], os.environ['WATCHER_API_KEY'],"
        " os.environ['GATEWAY_API_KEY'], asyncio.Event(), os.environ['GATEWAY_URL']))",
    ]
    previous = asyncio.run(_replace_settings(key or None, SETTINGS))
    try:
        asyncio.run(_await_rules(key or None))
        provider = Fixture(WithheldProvider)
        try:
            with running_gateway(
                tmp_path_factory.mktemp("withheld"), provider, str(LIVE_URL), key, serve, alternatives=True
            ) as urls:
                yield {**urls, "key": key}
        finally:
            provider.shutdown()
    finally:
        # Restored even when setup fails, so the organization never keeps the fixture rules.
        asyncio.run(_replace_settings(key or None, previous))


async def _records(stack: dict, since: datetime, ids: list[str], settled: Callable[[list, list], bool], session: str):
    """Every stored decision for ``ids`` in any session active since ``since``, and the reply's withheld calls.

    Watcher stores decisions after acknowledging each hook, and the processor
    records the delivered reply after the client has it, so this polls until
    ``settled`` accepts the decisions and the withheld calls named on
    ``session``'s trajectories, or two minutes pass; either way it returns
    the last snapshot, so the caller checks the decisions it holds.
    """
    records: list = []
    named: list = []
    async with AsyncWatcherClient(str(LIVE_URL), api_key=stack["key"] or None) as watcher:
        for _ in range(120):
            records, named = [], []
            for found in (await watcher.search_sessions(start_date=since)).to_dict()["sessions"]:
                listed = (await watcher.list_trajectories(found["session_id"])).to_dict()["trajectories"]
                for trajectory in listed:
                    detail = (
                        await watcher.get_trajectory(
                            found["session_id"], trajectory["trajectory_id"], view=TrajectoryView.EXTENDED
                        )
                    ).to_dict()
                    decisions = detail.get("tool_call_decisions") or {}
                    records += [{**decisions[i], "session_id": found["session_id"]} for i in ids if i in decisions]
                    if found["session_id"] == session:
                        named += detail.get("gateway_withheld_decisions") or []
            if settled(records, named):
                break
            await asyncio.sleep(1)
    return records, named


async def _session_of(stack: dict, conversation: str) -> str:
    async with AsyncWatcherClient(str(LIVE_URL), api_key=stack["key"] or None) as watcher:
        for _ in range(60):
            found = (await watcher.search_sessions(external_ids={"other": [conversation]})).to_dict()["sessions"]
            if found:
                return found[0]["session_id"]
            await asyncio.sleep(1)
    pytest.fail(f"Watcher never stored {conversation}")


@pytest.mark.parametrize("case", ["alternative", "repeat"])
async def test_withheld_calls_are_never_recorded_as_run(withheld_stack: dict, case: str) -> None:
    """The refused call is blocked, its sibling and any repeat never ran, and all of it sits in one session."""
    token = f"{case}-{uuid4().hex[:12]}"
    since = datetime.now(UTC)
    raw = client(withheld_stack).chat.completions.with_raw_response.create(
        model="fixture-model",
        messages=[{"role": "user", "content": token}],
        tools=[
            {"type": "function", "function": {"name": name, "parameters": {"type": "object"}}}
            for name in ("write_file", "read_file")
        ],
    )
    completion = raw.parse()
    assert isinstance(completion, ChatCompletion)
    message = completion.choices[0].message
    session = await _session_of(withheld_stack, raw.headers["x-watcher-conversation-id"])
    refused, sibling = f"{token}-refused", f"{token}-sibling"
    repeats = [f"{token}-repeat", f"{token}-repeat-sibling"] if case == "repeat" else []
    graded = [refused, sibling] + ([] if case == "repeat" else [f"{token}-alternative"])

    def settled(records: list, named: list) -> bool:
        """Every graded call is decided and the refusal is final, or a call was already recorded as run."""
        if any(record.get("decision_context") == HISTORY_ONLY for record in records):
            return True
        statuses = {record["tool_use_id"]: record["tool_status"] for record in records}
        return set(graded) <= set(statuses) and statuses[refused] == "blocked" and bool(named)

    records, named = await _records(withheld_stack, since, graded + repeats, settled, session)

    statuses = {(record["tool_use_id"], record["tool_status"], record.get("decision_context")) for record in records}
    assert all(record.get("decision_context") != HISTORY_ONLY for record in records), statuses
    assert {record["session_id"] for record in records} == {session}, statuses
    assert not [record for record in records if record["tool_use_id"] in repeats], statuses
    by_id = {record["tool_use_id"]: record for record in records}
    assert set(by_id) == set(graded), statuses
    assert by_id[refused]["tool_status"] == "blocked" and by_id[refused]["applied_decision"] == "deny"
    assert by_id[sibling]["tool_status"] != "completed" and by_id[sibling]["applied_decision"] == "allow"
    withheld = {decision["tool_use_id"] for decision in named}
    assert {refused, sibling} <= withheld, "The delivered reply names the calls it replaced"
    if case == "repeat":
        assert not message.tool_calls and (message.content or "").endswith("Shall I stop here?")
    else:
        assert [call.id for call in message.tool_calls or []] == [f"{token}-alternative"]
        assert f"{token}-alternative" not in withheld
