"""Report completed gate calls without replacing their stored judgments."""

import asyncio
from copy import deepcopy
from pathlib import Path
from typing import Literal
from uuid import UUID

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, JsonValue
from watcher_github_copilot_cli import integration, recording
from watcher_github_copilot_cli.diagnostics import ReviewReceipt, record_event
from watcher_github_copilot_cli.recording import RecordedSession
from watcher_github_copilot_cli.reviews import call_hash
from watcher_github_copilot_cli.transcript import ConvertedSession, SubagentHistory

from watcher_sdk import AsyncWatcherClient

NATIVE = UUID("4f3b0c9e-1c7d-4a47-9a0e-3a4e2f9b6c11")
IDENTITY = f"github-copilot-cli:{NATIVE}"
SESSION = UUID(int=1)
ARGUMENTS: dict[str, JsonValue] = {"command": "printf completed"}
MESSAGES: list[dict[str, JsonValue]] = [
    {"role": "user", "content": "Print completed"},
    {"role": "assistant", "content": "", "tool_calls": [{"id": "call", "function": "Bash", "arguments": ARGUMENTS}]},
    {"role": "tool", "tool_call_id": "call", "function": "Bash", "content": "completed"},
]


class SubmittedCall(BaseModel):
    tool_name: str
    tool_input: dict[str, JsonValue]


class Outcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_use_id: str
    tool_name: str
    raw_tool_call: SubmittedCall
    policy_decision: Literal["not_evaluated"]
    applied_decision: Literal["not_evaluated"]
    decision_source: Literal["not_evaluated"]
    tool_status: Literal["completed", "blocked"]


class Batch(BaseModel):
    session_id: UUID
    decisions: list[Outcome]


def receipt() -> ReviewReceipt:
    return ReviewReceipt(
        native_session=NATIVE,
        identity=IDENTITY,
        tool_use_id="call",
        call_hash=call_hash("Bash", ARGUMENTS),
        decision="allow",
        judged_decision="allow",
        enforcement_mode="enforce",
        decision_source="triage",
        grade_ids=[UUID(int=7)],
        grade_ids_complete=True,
    )


async def capture(
    messages: list[dict[str, JsonValue]], receipts: list[ReviewReceipt], failed: list[str]
) -> list[Batch]:
    batches: list[Batch] = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/tool-call-decisions/batch"
        batch = Batch.model_validate_json(request.content)
        batches.append(batch)
        return httpx.Response(
            200, json={"synced_count": len(batch.decisions), "synced_tool_use_ids": [], "failed_tool_use_ids": failed}
        )

    async with AsyncWatcherClient(
        httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
    ) as client:
        await recording.upload_completed_calls(client, SESSION, IDENTITY, messages, receipts)
    return batches


@pytest.mark.parametrize("decision,status", [("allow", "completed"), ("deferred", "completed"), ("deny", "blocked")])
def test_confirmed_results_update_only_the_execution_outcome(decision: str, status: str) -> None:
    reviewed = receipt().model_copy(
        update={
            "decision": decision,
            "judged_decision": "allow" if decision == "deferred" else decision,
            "enforcement_mode": "observe" if decision == "deferred" else "enforce",
        }
    )
    [batch] = asyncio.run(capture(MESSAGES, [reviewed, reviewed], []))
    assert batch.session_id == SESSION
    assert [decision.model_dump() for decision in batch.decisions] == [
        {
            "tool_use_id": "call",
            "tool_name": "Bash",
            "raw_tool_call": {"tool_name": "Bash", "tool_input": ARGUMENTS},
            "policy_decision": "not_evaluated",
            "applied_decision": "not_evaluated",
            "decision_source": "not_evaluated",
            "tool_status": status,
        }
    ]


@pytest.mark.parametrize(
    "case",
    [
        "pending",
        "missing-call",
        "duplicate-call",
        "duplicate-result",
        "arguments",
        "identity",
        "paused",
        "escalate",
        "left-judgment",
        "no-receipt",
    ],
)
def test_unconfirmed_or_unmatched_calls_get_no_completion_update(case: str) -> None:
    messages = deepcopy(MESSAGES)
    reviewed = receipt()
    if case == "pending":
        messages.pop()
    elif case == "missing-call":
        messages.pop(1)
    elif case == "duplicate-call":
        messages.insert(1, deepcopy(MESSAGES[1]))
    elif case == "duplicate-result":
        messages.append(deepcopy(MESSAGES[2]))
    elif case == "arguments":
        reviewed = reviewed.model_copy(update={"call_hash": call_hash("Bash", {"command": "different"})})
    elif case == "identity":
        reviewed = reviewed.model_copy(update={"identity": IDENTITY + ":agent:other"})
    elif case == "paused":
        reviewed = reviewed.model_copy(update={"enforcement_mode": "paused"})
    elif case == "escalate":
        reviewed = reviewed.model_copy(update={"decision": "escalate"})
    elif case == "left-judgment":
        reviewed = reviewed.model_copy(update={"stored_by": "recording"})
    assert asyncio.run(capture(messages, [] if case == "no-receipt" else [reviewed], [])) == []


def test_a_failed_completion_update_is_retryable() -> None:
    with pytest.raises(ValueError, match="every tool outcome"):
        asyncio.run(capture(MESSAGES, [receipt()], ["call"]))


def test_recording_updates_only_confirmed_parent_and_subagent_conversations(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    for identity in [IDENTITY, IDENTITY + ":agent:worker", IDENTITY + ":agent:unconfirmed"]:
        record_event(config, "reviewed", review=receipt().model_copy(update={"identity": identity}))
    session = ConvertedSession(
        messages=MESSAGES,
        subagents=[SubagentHistory("worker", MESSAGES), SubagentHistory("unconfirmed", MESSAGES)],
        replied=True,
    )
    recorded = RecordedSession(session=SESSION, subagents={"worker": UUID(int=2)})
    batches: list[Batch] = []

    def respond(request: httpx.Request) -> httpx.Response:
        batches.append(Batch.model_validate_json(request.content))
        return httpx.Response(200, json={"synced_count": 1, "synced_tool_use_ids": ["call"], "failed_tool_use_ids": []})

    async def run() -> None:
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await integration._sync_decisions(client, recorded, NATIVE, session, config)

    asyncio.run(run())
    assert [batch.session_id for batch in batches] == [SESSION, UUID(int=2)]
    assert all(batch.decisions[0].tool_status == "completed" for batch in batches)
