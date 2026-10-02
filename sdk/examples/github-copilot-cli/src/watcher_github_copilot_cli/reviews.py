"""Confirm the judgments the gate stored by reading them back, using content-free receipts."""

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, JsonValue

from watcher_github_copilot_cli.diagnostics import ReviewCheck, ReviewReceipt, read_review_evidence, record_event
from watcher_github_copilot_cli.monitoring import PolicyOutcome
from watcher_sdk import AsyncWatcherClient, TrajectoryView, WatcherAuthenticationError
from watcher_sdk._generated.models import GatewayResult, PreToolUseHookResponse, TriageResult
from watcher_sdk._generated.types import Unset

# Readback runs after recording inside the observer's callback, whose installed
# timeout leaves room for this much on top of the flush, recording and answer uploads.
CONFIRM_SECONDS = 5.0


def call_hash(name: str, arguments: dict[str, JsonValue]) -> str:
    """A SHA-256 of the exact submitted call, so diagnostics can match it without keeping it."""
    return hashlib.sha256(json.dumps([name, arguments], sort_keys=True).encode()).hexdigest()


def receipt(
    result: PreToolUseHookResponse,
    *,
    native_session: UUID,
    identity: str,
    tool_use_id: str,
    fingerprint: str,
    stored_by: Literal["gate", "recording"] = "gate",
) -> ReviewReceipt:
    """The receipt of a validated answer for a stored judgment, with every grade it links.

    Triage and gateway grades link to the call only through the IDs the answer
    returns. ``grade_ids_complete`` is false when the deciding stage is missing or
    any stage that ran returned no grade ID, so that grade cannot be confirmed.
    With ``stored_by="recording"`` the answer came from a request that stored
    nothing, grades included, so the receipt links no grade and is complete
    without one; it is stamped with the current time for recording to upload.
    """
    outcome = PolicyOutcome.model_validate(result.to_dict())
    complete = (outcome.decision_source != "triage" or isinstance(result.triage, TriageResult)) and (
        outcome.decision_source != "policy_gateway" or isinstance(result.gateway, GatewayResult)
    )
    grade_ids: list[UUID] = []
    for stage in (result.triage, result.gateway):
        if stage is None or isinstance(stage, Unset):
            continue
        if isinstance(stage.tool_call_grade_id, UUID):
            grade_ids.append(stage.tool_call_grade_id)
        else:
            complete = False
    if stored_by == "recording":
        grade_ids, complete = [], True
    return ReviewReceipt.model_validate(
        {
            "native_session": native_session,
            "identity": identity,
            "tool_use_id": tool_use_id,
            "call_hash": fingerprint,
            "decision": outcome.decision,
            "judged_decision": outcome.judged_decision,
            "enforcement_mode": outcome.enforcement_mode,
            "decision_source": outcome.decision_source,
            "grade_ids": grade_ids,
            "grade_ids_complete": complete,
            "stored_by": stored_by,
            "decided_at": datetime.now(UTC) if stored_by == "recording" else None,
        }
    )


class StoredCall(BaseModel):
    tool_name: str
    tool_input: dict[str, JsonValue]


class StoredGrade(BaseModel):
    tool_call_grade_id: UUID


class StoredJudgment(BaseModel):
    """The fields of a stored decision that a receipt is checked against."""

    tool_use_id: str
    tool_name: str
    raw_tool_call: StoredCall
    applied_decision: str | None = None
    judged_decision: str | None = None
    enforcement_mode: str | None = None
    decision_source: str
    grades: list[StoredGrade] = Field(default_factory=list)


def _matches(stored: StoredJudgment, expected: ReviewReceipt) -> bool:
    """Whether Watcher stored the receipt's exact call, decision and every grade it returned."""
    call = stored.raw_tool_call
    return (
        stored.tool_use_id == expected.tool_use_id
        and stored.tool_name == call.tool_name
        and call_hash(call.tool_name, call.tool_input) == expected.call_hash
        and stored.applied_decision == expected.decision
        and stored.judged_decision == expected.judged_decision
        and stored.enforcement_mode == expected.enforcement_mode
        and stored.decision_source == expected.decision_source
        and set(expected.grade_ids) <= {grade.tool_call_grade_id for grade in stored.grades}
    )


async def _confirmed(client: AsyncWatcherClient, identity: str, expected: list[ReviewReceipt]) -> AsyncIterator[UUID]:
    """Yield each receipt of ``identity``'s conversation as its stored judgment is found.

    The latest trajectory is read first and earlier ones, such as branches a rewind
    left, after it. Yielding as it goes keeps the receipts already confirmed when a
    later read fails or runs out of time.
    """
    found = await client.search_sessions(external_ids={"other": [identity]}, limit=2)
    if found.total != 1 or len(found.sessions) != 1:
        return
    session = found.sessions[0]
    listed = await client.list_trajectories(session.session_id)
    trajectories = [item.trajectory_id for item in listed.trajectories if item.session_id == session.session_id]
    if isinstance(session.latest_trajectory_id, str):
        trajectories.insert(0, session.latest_trajectory_id)
    pending = {item.receipt_id: item for item in expected}
    for trajectory_id in dict.fromkeys(trajectories):
        # Decisions come with either view; the truncated one leaves out heavy message content.
        trajectory = await client.get_trajectory(session.session_id, trajectory_id, view=TrajectoryView.TRUNCATED)
        decisions = trajectory.tool_call_decisions
        if trajectory.session_id != session.session_id or isinstance(decisions, Unset):
            continue
        for receipt_id, item in list(pending.items()):
            if item.tool_use_id in decisions and _matches(
                StoredJudgment.model_validate(decisions[item.tool_use_id].to_dict()), item
            ):
                del pending[receipt_id]
                yield receipt_id
        if not pending:
            return


async def confirm_reviews(
    client: AsyncWatcherClient,
    config: Path,
    *,
    native_session: UUID | None,
    timeout: float = CONFIRM_SECONDS,
    record: bool = True,
    repeat: bool = True,
) -> ReviewCheck:
    """Read the stored judgments of the retained receipts back, for one native session or all of them.

    Only reads: nothing is graded or stored again, and no tool permission changes.
    Receipts answered in paused mode are skipped, since paused mode stores no
    judgment, and receipts missing a grade ID are unconfirmed without a read. The
    newest receipts are read first, and reading repeats until every receipt is
    confirmed or ``timeout`` expires; with ``repeat=False`` each is read only once,
    still within ``timeout``. Every failure is caught and reported as the
    check's ``failure``, never raised; the check is saved as the status's
    ``last_review_check``. With ``record=False`` the diagnostics stay unchanged,
    so a check run on request does not replace the hooks' own last check.
    """
    check = ReviewCheck(native_session=native_session)
    confirmed: set[UUID] = set()
    receipts: list[ReviewReceipt] = []
    try:
        async with asyncio.timeout(timeout):
            evidence = await asyncio.to_thread(read_review_evidence, config, native_session)
            receipts = evidence.receipts
            check.gaps, check.unscoped_gaps = len(evidence.gaps), len(evidence.unscoped_gaps)
            readable = [item for item in reversed(receipts) if item.enforcement_mode != "paused"]
            check.skipped = len(receipts) - len(readable)
            pending = [item for item in readable if item.grade_ids_complete]
            while pending:
                groups: dict[str, list[ReviewReceipt]] = {}
                for item in pending:
                    groups.setdefault(item.identity, []).append(item)
                for identity, items in groups.items():
                    async for receipt_id in _confirmed(client, identity, items):
                        confirmed.add(receipt_id)
                pending = [item for item in pending if item.receipt_id not in confirmed]
                if not repeat:
                    break
                if pending:
                    await asyncio.sleep(0.25)
    except WatcherAuthenticationError:
        check.failure = "authentication"
    except Exception:
        check.failure = "review"
    check.confirmed = len(confirmed)
    check.unconfirmed = len(receipts) - check.skipped - check.confirmed
    if check.unconfirmed and check.failure is None:
        check.failure = "review"
    # The failure stays on the check: the status's last error belongs to the hooks,
    # and a judgment that cannot be confirmed must not hide a tool the gate withheld.
    if record:
        record_event(config, "reviews_checked", check=check)
    return check
