"""Confirm Copilot transcript storage through the public Watcher SDK, then store decisions on its calls."""

import asyncio
import math
from collections import Counter
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from watcher_github_copilot_cli.diagnostics import ReviewReceipt
from watcher_github_copilot_cli.identity import RecordedCall, RecordedMessage
from watcher_github_copilot_cli.reviews import call_hash
from watcher_github_copilot_cli.transcript import (
    ConvertedSession,
    HumanResponse,
    SubagentHistory,
    TranscriptError,
    patch_paths,
    policy_call,
)
from watcher_sdk import AsyncWatcherClient, TrajectoryView, WatcherAPIError

_MESSAGES = TypeAdapter(list[dict[str, JsonValue]])


class PartialRecordingError(TranscriptError):
    """The parent conversation was confirmed but at least one subagent conversation was not."""

    def __init__(self, recorded: "RecordedSession", failed: int) -> None:
        super().__init__(f"The parent history was confirmed, but {failed} subagent histories were not")
        self.recorded = recorded


class RecordedSession(BaseModel):
    model_config = ConfigDict(frozen=True)

    session: UUID
    subagents: dict[str, UUID]


class OutcomeToolCall(BaseModel):
    tool_name: str
    tool_input: dict[str, JsonValue]


class ToolOutcome(BaseModel):
    tool_use_id: str
    tool_name: str
    raw_tool_call: OutcomeToolCall
    policy_decision: Literal["not_evaluated"] = "not_evaluated"
    applied_decision: Literal["not_evaluated"] = "not_evaluated"
    decision_source: Literal["not_evaluated"] = "not_evaluated"
    tool_status: Literal["completed", "blocked"]


def _preserves_fields(stored: JsonValue, supplied: JsonValue) -> bool:
    """Allow server-added object fields while requiring exact values and list order."""
    if isinstance(supplied, dict):
        return isinstance(stored, dict) and all(
            key in stored and _preserves_fields(stored[key], value) for key, value in supplied.items()
        )
    if isinstance(supplied, list):
        return (
            isinstance(stored, list)
            and len(stored) == len(supplied)
            and all(_preserves_fields(saved, sent) for saved, sent in zip(stored, supplied, strict=True))
        )
    return type(stored) is type(supplied) and stored == supplied


async def record_messages(
    client: AsyncWatcherClient,
    identity: str,
    messages: list[dict[str, JsonValue]],
    *,
    timeout_seconds: float,
) -> UUID:
    """Submit a complete snapshot and return its confirmed Watcher session ID.

    Requires a credential with session ingestion and read permissions. A hook
    response acknowledges the request before storage, so confirmation also reads
    every supplied message back in order. A newer stored turn may extend this
    snapshot, which lets an older callback be safely replayed after continuation.
    Server-added fields are allowed; supplied content and tool identities must
    match exactly. Missing storage, ambiguous identities and API failures raise.
    The deadline covers submission and all readback requests, without a queue.
    """
    if not messages:
        raise ValueError("The transcript has no supported messages")
    if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 40:
        raise ValueError("Recording timeout must be greater than zero and at most 40 seconds")
    async with asyncio.timeout(timeout_seconds):
        try:
            await client.pre_tool_use_hook(
                input=[],
                messages=messages,
                external_ids={"other": identity},
                timeout=min(10, timeout_seconds),
            )
        except WatcherAPIError as error:
            if error.status_code == 413:
                raise TranscriptError("The history exceeds Watcher's request size limit") from None
            raise
        while True:
            result = await client.search_sessions(external_ids={"other": [identity]}, limit=2)
            if result.total > 1 or len(result.sessions) > 1:
                raise ValueError("The native identity matched multiple Watcher sessions")
            if result.sessions:
                session = result.sessions[0]
                if isinstance(session.latest_trajectory_id, str):
                    trajectory = await client.get_trajectory(
                        session.session_id, session.latest_trajectory_id, view=TrajectoryView.EXTENDED
                    )
                    if trajectory.session_id != session.session_id:
                        raise ValueError("Watcher returned a trajectory from another session")
                    stored = _MESSAGES.validate_python([message.to_dict() for message in trajectory.messages])
                    if len(stored) >= len(messages) and all(
                        _preserves_fields(saved, sent) for saved, sent in zip(stored, messages, strict=False)
                    ):
                        return UUID(session.session_id)
            await asyncio.sleep(0.25)


async def record_session(
    client: AsyncWatcherClient, native_id: UUID, session: ConvertedSession, *, timeout_seconds: float
) -> RecordedSession:
    """Record the parent conversation, then each subagent conversation as its own Watcher session.

    A subagent's identity is ``github-copilot-cli:<session>:agent:<agentId>``. Separate
    sessions keep a subagent's newer rows from becoming the parent session's latest
    trajectory. The parent is recorded first and one deadline covers everything.
    Subagents are recorded newest first, up to four at a time. A subagent that
    cannot be confirmed does not undo the parent, but is reported.
    """
    identity = "github-copilot-cli:" + str(native_id)
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    parent = await record_messages(client, identity, session.messages, timeout_seconds=timeout_seconds)
    subagents, failed = await record_subagents(client, identity, session.subagents, deadline=deadline)
    recorded = RecordedSession(session=parent, subagents=subagents)
    if failed:
        raise PartialRecordingError(recorded, failed)
    return recorded


async def record_subagents(
    client: AsyncWatcherClient, identity: str, histories: list[SubagentHistory], *, deadline: float
) -> tuple[dict[str, UUID], int]:
    """Record subagent conversations before an event-loop ``deadline``; return confirmations and failures.

    Newest subagents go first, because earlier callbacks have usually recorded the
    older ones already; up to four run at once so a long list still fits.
    """
    loop = asyncio.get_running_loop()
    subagents: dict[str, UUID] = {}
    slots = asyncio.Semaphore(4)

    async def record_subagent(history: SubagentHistory) -> bool:
        async with slots:
            remaining = min(deadline - loop.time(), 40)
            if remaining <= 0:
                return False
            try:
                subagents[history.agent_id] = await record_messages(
                    client, f"{identity}:agent:{history.agent_id}", history.messages, timeout_seconds=remaining
                )
            except Exception:
                return False
            return True

    outcomes = await asyncio.gather(*(record_subagent(history) for history in reversed(histories)))
    return subagents, outcomes.count(False)


def _is_multi_file_patch(name: str, arguments: dict[str, JsonValue]) -> bool:
    """Whether a recorded call is an ``apply_patch`` that names several files.

    That is the only call the gate leaves a receipt for recording to store (see
    ``integration.apply_policy``). The transcript records it as ``policy_call``
    translates the patch: ``Write`` or ``Edit`` after its first file, with every
    path under ``file_paths``. Translating the recorded arguments as a patch again
    must therefore give back exactly the recorded call. A call whose name, first
    path or list of paths differs from the patch in its ``input`` does not.
    """
    patch = arguments.get("input")
    if not isinstance(patch, str) or len(patch_paths(patch)) < 2:
        return False
    return policy_call("apply_patch", arguments) == (name, arguments)


def _restricts(judgment: ReviewReceipt) -> bool:
    """Whether a receipt holds a deny or escalate judgment, applied the way its enforcement mode applies one."""
    if judgment.judged_decision not in {"deny", "escalate"}:
        return False
    if judgment.enforcement_mode == "observe":
        return judgment.decision == "deferred"
    return judgment.enforcement_mode == "enforce" and judgment.decision == judgment.judged_decision


async def upload_completed_calls(
    client: AsyncWatcherClient,
    session_id: UUID,
    identity: str,
    messages: list[dict[str, JsonValue]],
    receipts: list[ReviewReceipt],
) -> None:
    """Report confirmed tool results without replacing the gate's judgment or grades.

    Only gate receipts for this conversation, matching one recorded call and
    one result, can update its execution status. Calls awaiting a result and
    paused or escalated receipts are left to their existing reporting paths.
    Failed batches raise so the next recording callback retries them.
    """
    recorded = [RecordedMessage.model_validate(message) for message in messages]
    calls: dict[str, list[RecordedCall]] = {}
    for message in recorded:
        for call in message.tool_calls:
            calls.setdefault(call.id, []).append(call)
    results = Counter(message.tool_call_id for message in recorded if message.tool_call_id is not None)
    decisions: dict[str, ToolOutcome] = {}
    for receipt in receipts:
        if (
            receipt.stored_by != "gate"
            or receipt.identity != identity
            or receipt.enforcement_mode == "paused"
            or receipt.decision == "escalate"
        ):
            continue
        matches = calls.get(receipt.tool_use_id)
        if matches is None or len(matches) != 1 or results[receipt.tool_use_id] != 1:
            continue
        call = matches[0]
        if call_hash(call.function, call.arguments) != receipt.call_hash:
            continue
        decisions[call.id] = ToolOutcome(
            tool_use_id=call.id,
            tool_name=call.function,
            raw_tool_call=OutcomeToolCall(tool_name=call.function, tool_input=call.arguments),
            tool_status="blocked" if receipt.decision == "deny" else "completed",
        )
    if not decisions:
        return
    result = await client.upload_tool_call_decisions_batch(
        session_id=str(session_id), decisions=[decision.model_dump(mode="json") for decision in decisions.values()]
    )
    if result.failed_tool_use_ids:
        raise ValueError("Watcher could not store every tool outcome")


async def upload_decisions(
    client: AsyncWatcherClient,
    session_id: UUID,
    messages: list[dict[str, JsonValue]],
    judgments: list[ReviewReceipt],
    responses: list[HumanResponse],
) -> None:
    """Store, in one batch, the gate's judgments left for recording and people's answers to its prompts.

    ``judgments`` are receipts the gate saved with ``stored_by="recording"``: the
    judgment that governed a multi-file patch, which the gate could not store
    because Watcher stores a gate request only for the call exactly as the
    transcript records it. Each is stored on its call in ``messages``, the
    conversation recording just confirmed, with the decision values, time and
    status the gate would have stored had it judged the patch as one call. A
    denied call is ``blocked``, any other ``pending``. A judgment is skipped
    unless its call appears exactly once in ``messages``, is a multi-file patch
    and has the hash the gate judged, and unless it is a deny or escalate applied
    as its mode applies one.

    These checks narrow what a receipt can change, but they cannot prove that the
    gate wrote it. They compare the receipt with the confirmed transcript only,
    never with the decision Watcher already stored, and the agent can write to the
    diagnostics directory. A judgment replaces the call's whole stored evaluation,
    so a receipt the agent forges for a recorded multi-file patch can store any
    deny or escalate on that call, and so turn a stored deny into an escalate. If
    the agent also forges the gate's list of escalated calls and an answer in
    Copilot's log, the call then shows as escalated and approved by a person. An
    agent with that access can already reach Watcher's API with the saved
    credential, so this is a cheaper route to the same reach, not a new one.

    ``responses`` report host outcomes only: no Watcher evaluation, so the server
    keeps the gate's stored decision and merges the human decision, its time and
    the call's status into it. A denied call is ``blocked``; an approved one is
    ``completed`` once its result is recorded, otherwise ``pending``, which never
    overwrites a known status. A call with both a judgment and an answer is sent
    once with both, because the server keeps an evaluation over an answer for the
    same call in one batch. Repeating an upload changes nothing. Calls the server
    cannot resolve raise ``ValueError``.
    """
    decisions: dict[str, dict[str, JsonValue]] = {}
    for response in responses:
        decisions[response.tool_use_id] = {
            "tool_use_id": response.tool_use_id,
            "tool_name": response.tool_name,
            "raw_tool_call": {"tool_name": response.tool_name, "tool_input": response.arguments},
            "policy_decision": "not_evaluated",
            "applied_decision": "not_evaluated",
            "decision_source": "not_evaluated",
            "tool_status": "blocked"
            if response.decision == "deny"
            else "completed"
            if response.completed
            else "pending",
            "human_decision": response.decision,
            **({"human_decided_at": response.decided_at} if response.decided_at else {}),
        }
    calls = [call for message in messages for call in RecordedMessage.model_validate(message).tool_calls]
    for judgment in judgments:
        matches = [call for call in calls if call.id == judgment.tool_use_id]
        if (
            len(matches) != 1
            or not _is_multi_file_patch(matches[0].function, matches[0].arguments)
            or call_hash(matches[0].function, matches[0].arguments) != judgment.call_hash
            or not _restricts(judgment)
        ):
            continue
        call, answer = matches[0], decisions.get(judgment.tool_use_id, {})
        decisions[judgment.tool_use_id] = answer | {
            "tool_use_id": call.id,
            "tool_name": call.function,
            "raw_tool_call": {"tool_name": call.function, "tool_input": call.arguments},
            # The legacy field folds a deferred decision to "not_evaluated", as the gate's own request does.
            "policy_decision": "not_evaluated" if judgment.decision == "deferred" else judgment.decision,
            "applied_decision": judgment.decision,
            "judged_decision": judgment.judged_decision,
            "enforcement_mode": judgment.enforcement_mode,
            "decision_source": judgment.decision_source,
            "tool_status": answer.get("tool_status", "blocked" if judgment.decision == "deny" else "pending"),
            **({"decided_at": judgment.decided_at.isoformat()} if judgment.decided_at else {}),
        }
    if not decisions:
        return
    result = await client.upload_tool_call_decisions_batch(
        session_id=str(session_id), decisions=list(decisions.values())
    )
    if result.failed_tool_use_ids:
        raise ValueError("Watcher could not store every decision")
