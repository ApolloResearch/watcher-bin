"""Keep private, content-free delivery status for Copilot hooks and their detached workers.

The same directory keeps the native IDs of the calls the gate escalated, so recording
uploads people's answers only to the gate's own prompts, and receipts of the judgments
the gate stored, or left for recording to store, so recording can confirm them by
reading Watcher back.
"""

import os
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from filelock import FileLock, Timeout
from pydantic import BaseModel, Field, ValidationError

from watcher_github_copilot_cli.configuration import _write_file

type EventKind = Literal[
    "started",
    "recorded",
    "completed",
    "allowed",
    "deferred",
    "denied",
    "escalated",
    "failed",
    "detached",
    "unrecorded_review",
    "unsynced_decisions",
    # The recorded log had events this sample could not read; see SKIPPED_EVENT_NOTICE.
    "skipped_events",
    # The gate stored a judgment on a native call, or left one for recording to store;
    # the event carries its ReviewReceipt.
    "reviewed",
    # Recording read stored judgments back; the event carries the ReviewCheck.
    "reviews_checked",
    # A callback in an opted-out project was left alone; the event carries its SkipReason.
    "skipped",
]
type FailureKind = Literal["authentication", "connection", "configuration", "recording", "evaluation"]
# Why a hook left a callback alone, recording nothing and answering no decision.
# ``opted_out``: the user opted the session's project out of this sample's hooks,
# which turns off the personal install and any project install there.
type SkipReason = Literal["opted_out"]
type HookKind = Literal["observe", "enforce"]
# Why the gate asked for a review Watcher does not store. Each names a case where
# storing the decision on the recorded call is impossible, or would be misleading:
# ``subagent_no_log``: no log names the call's session or subagent, or the Copilot
#   release names no session, so there is no conversation to store it in.
# ``transcript_unsupported``: a log that could hold the call could not be read or
#   converted, or has a damaged record written around the callback, so a call hidden
#   in the damaged part cannot be ruled out.
# ``tool_call_id_not_found``: no open hook record and unanswered call in the log match
#   the pending call, or the callback lacks the time or directory needed to match.
# ``tool_call_ambiguous``: more than one call matches exactly, such as identical
#   parallel calls. Order never decides which call the decision belongs to.
# ``conversation_too_large``: the whole conversation exceeds the request budget, and
#   a trimmed copy would fork the stored history.
type UnrecordedReason = Literal[
    "subagent_no_log",
    "transcript_unsupported",
    "tool_call_id_not_found",
    "tool_call_ambiguous",
    "conversation_too_large",
]


class ReviewReceipt(BaseModel):
    """What the gate's validated answer said about a judgment Watcher stores on a native call.

    It is evidence of the answer, not of storage: recording confirms storage by
    reading the call's judgment back (see ``reviews.confirm_reviews``). It holds
    opaque IDs, a hash of the submitted call and policy enums, never call content.
    ``grade_ids_complete`` is false when a grading stage that ran gave no grade
    ID, so that stage's grade cannot be linked to the call.

    ``stored_by`` says who stores the judgment. ``"gate"``: the gate's own request
    stored it. ``"recording"``: the judgment that governed a multi-file patch came
    from a request the gate could not store (see ``integration.apply_policy``), so
    recording uploads it once the transcript is confirmed (see
    ``recording.upload_decisions``), with ``decided_at``, the time the gate decided.
    Such a request stores no grade either, so there is none to link.
    """

    receipt_id: UUID = Field(default_factory=uuid4)
    native_session: UUID
    identity: str
    tool_use_id: str = Field(min_length=1)
    call_hash: str
    decision: Literal["allow", "deny", "escalate", "deferred"]
    judged_decision: Literal["allow", "deny", "escalate"] | None
    enforcement_mode: Literal["enforce", "observe", "paused"]
    decision_source: Literal["threshold", "rule", "triage", "policy_gateway", "grading_error", "bypass"]
    grade_ids: list[UUID] = Field(default_factory=list)
    grade_ids_complete: bool
    stored_by: Literal["gate", "recording"] = "gate"
    decided_at: datetime | None = None


class ReviewCheck(BaseModel):
    """One read-back of the retained receipts for a native session, or for all sessions.

    ``confirmed`` receipts matched the stored judgment and its grades exactly,
    ``unconfirmed`` ones did not or could not be read in time, and ``skipped`` ones
    were answered in paused mode, which stores no judgment. ``gaps`` counts calls
    of that session the gate judged without storing; ``unscoped_gaps`` counts those
    whose session is unknown, which may include it. The counts cover only records
    still kept in the rotating diagnostics log, never every call Copilot made.
    """

    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    native_session: UUID | None = None
    confirmed: int = 0
    unconfirmed: int = 0
    skipped: int = 0
    gaps: int = 0
    unscoped_gaps: int = 0
    failure: Literal["authentication", "review"] | None = None


class HookEvent(BaseModel):
    """One diagnostics record.

    An ``unrecorded_review`` names its call by ``native_session``, when the call's
    session log is known, ``call_hash``, and ``tool_use_id`` when exactly one call
    matched, so gaps can be counted per session without keeping the call itself.
    """

    at: datetime
    kind: EventKind
    session: UUID | None = None
    failure: FailureKind | None = None
    hook: HookKind | None = None
    reason: UnrecordedReason | None = None
    native_session: UUID | None = None
    call_hash: str | None = None
    tool_use_id: str | None = None
    review: ReviewReceipt | None = None
    check: ReviewCheck | None = None
    skip: SkipReason | None = None


class HookStatus(BaseModel):
    """The latest state of each concern, kept apart so one success never hides another's gap.

    ``last_delivery`` is the last confirmed transcript; ``last_review_check`` the last
    read-back of stored judgments; ``last_review_gap`` the last call the gate judged
    without storing. Confirming a transcript changes neither of the latter two.
    """

    last_callback: datetime | None = None
    last_delivery: datetime | None = None
    last_session: UUID | None = None
    last_error: HookEvent | None = None
    last_review_check: ReviewCheck | None = None
    last_review_gap: HookEvent | None = None


# status.json holds a few timestamps and IDs; anything larger was not written here.
MAX_STATUS_BYTES = 64 * 1024


def open_private_file(path: Path, flags: int) -> int:
    """Open a diagnostics file as a regular file only, returning its descriptor.

    The gate saves diagnostics before it decides, and the agent can write to this
    directory. A FIFO put in place of a file would make an ordinary open wait for a
    writer until Copilot's outer timeout runs the tool, so the open never blocks
    and never follows a symlink, and anything other than a regular file raises
    ``ValueError``. A FIFO opened for writing with no reader raises ``OSError``.
    """
    descriptor = os.open(path, flags | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("Diagnostics files must be regular files")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _read_private(path: Path, limit: int) -> bytes | None:
    """A diagnostics file's bytes, or ``None`` when it does not exist; see ``open_private_file``."""
    try:
        descriptor = open_private_file(path, os.O_RDONLY)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as source:
        contents = source.read(limit + 1)
    if len(contents) > limit:
        raise ValueError("A diagnostics file exceeds its size limit")
    return contents


def read_status(config: Path) -> HookStatus:
    """Return the persisted hook status, or an empty status before the first callback.

    A status file that is not a regular file, or is larger than any status this
    module writes, raises ``ValueError``.
    """
    contents = _read_private(config.with_name("status.json"), MAX_STATUS_BYTES)
    return HookStatus() if contents is None else HookStatus.model_validate_json(contents)


def record_event(
    config: Path | None,
    kind: EventKind,
    *,
    session: UUID | None = None,
    failure: FailureKind | None = None,
    hook: HookKind | None = None,
    reason: UnrecordedReason | None = None,
    native_session: UUID | None = None,
    call_hash: str | None = None,
    tool_use_id: str | None = None,
    review: ReviewReceipt | None = None,
    check: ReviewCheck | None = None,
    skip: SkipReason | None = None,
) -> None:
    """Persist bounded diagnostics without changing a native permission decision on an I/O failure.

    Only fixed event names, fixed reasons, opaque IDs, hashes and policy enums enter
    this store. Detached workers use the same lock and files as foreground hooks. A
    completed callback does not imply delivery; only a confirmed server readback
    records ``recorded``. A failure stays the status's ``last_error`` until the same
    hook next succeeds: a confirmed recording clears only a recording failure, and a
    gate decision clears only a gate failure, so a tool the gate withheld stays
    visible after the turn is recorded. A failure saved without ``hook`` counts as
    a recording failure.
    """
    if config is None:
        return
    try:
        event = HookEvent(
            at=datetime.now(UTC),
            kind=kind,
            session=session,
            failure=failure,
            hook=hook,
            reason=reason,
            native_session=native_session,
            call_hash=call_hash,
            tool_use_id=tool_use_id,
            review=review,
            check=check,
            skip=skip,
        )
        with FileLock(str(config.with_name("diagnostics.lock")), timeout=2):
            status = read_status(config)
            previous = status.last_error.hook if status.last_error is not None else None
            if kind == "started":
                status.last_callback = event.at
            if kind == "recorded":
                status.last_delivery = event.at
                status.last_session = session
                if previous != "enforce":
                    status.last_error = None
            if kind in {"allowed", "deferred", "denied", "escalated"} and previous == "enforce":
                status.last_error = None
            if failure is not None:
                status.last_error = event
            if check is not None:
                status.last_review_check = check
            if kind == "unrecorded_review":
                status.last_review_gap = event
            log = config.with_name("events.jsonl")
            if log.is_file() and log.lstat().st_size >= 512 * 1024:
                log.replace(log.with_suffix(".previous.jsonl"))
            descriptor = open_private_file(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
            with os.fdopen(descriptor, "a", encoding="utf-8") as output:
                os.fchmod(descriptor, 0o600)
                output.write(event.model_dump_json() + "\n")
            _write_file(config.with_name("status.json"), status.model_dump_json())
    except (OSError, ValueError, Timeout):
        sys.stderr.write("Watcher could not save hook diagnostics. Check the private configuration directory.\n")


class EscalatedCall(BaseModel):
    """One call the gate asked a person about: its native Copilot session and tool-call ID."""

    session: UUID
    tool_use_id: str = Field(min_length=1, max_length=256)


class Escalations(BaseModel):
    """The calls the gate escalated, oldest first."""

    calls: list[EscalatedCall] = Field(default_factory=list)


# Recording reads people's answers from Copilot's log, which the agent can append
# to. Keeping the gate's own escalations here lets recording ignore answers to
# prompts the gate never raised. Only the newest entries are kept; an answer comes
# within the session, long before this many later escalations.
MAX_ESCALATIONS = 1000
MAX_ESCALATIONS_BYTES = 512 * 1024


def _read_escalations(config: Path) -> Escalations:
    contents = _read_private(config.with_name("escalations.json"), MAX_ESCALATIONS_BYTES)
    return Escalations() if contents is None else Escalations.model_validate_json(contents)


def record_escalation(config: Path | None, session: UUID, tool_use_id: str) -> None:
    """Remember that the gate escalated this call, before Copilot asks anyone.

    Like ``record_event``, an I/O failure is reported on stderr and never raised,
    so the gate still answers. The answer to that prompt is then not uploaded.
    """
    if config is None:
        return
    try:
        entry = EscalatedCall(session=session, tool_use_id=tool_use_id)
        with FileLock(str(config.with_name("diagnostics.lock")), timeout=2):
            escalations = _read_escalations(config)
            if entry not in escalations.calls:
                escalations.calls = [*escalations.calls, entry][-MAX_ESCALATIONS:]
                _write_file(config.with_name("escalations.json"), escalations.model_dump_json())
    except (OSError, ValueError, Timeout):
        sys.stderr.write("Watcher could not save the gate's escalation. Check the private configuration directory.\n")


def escalated_calls(config: Path, session: UUID) -> set[str]:
    """The native IDs of this session's calls the gate escalated.

    A record that is not a regular file, is too large or is malformed raises
    ``ValueError``; other read failures raise ``OSError``.
    """
    return {call.tool_use_id for call in _read_escalations(config).calls if call.session == session}


class ReviewGap(BaseModel):
    """A call the gate judged without storing, as ``read_review_evidence`` counts it."""

    reason: UnrecordedReason
    native_session: UUID | None = None
    call_hash: str | None = None
    tool_use_id: str | None = None


class ReviewEvidence(BaseModel):
    """Receipts and gaps still kept in the diagnostics log.

    ``gaps`` belong to the requested session (or to any known session when none
    was requested); ``unscoped_gaps`` have no known session.
    """

    receipts: list[ReviewReceipt] = Field(default_factory=list)
    gaps: list[ReviewGap] = Field(default_factory=list)
    unscoped_gaps: list[ReviewGap] = Field(default_factory=list)


# The log rotates once it reaches 512 KiB, so each file holds at most that much
# plus one event; anything larger was not written by this module.
MAX_EVENTS_BYTES = 1024 * 1024


def read_review_evidence(config: Path, native_session: UUID | None) -> ReviewEvidence:
    """The receipts and gaps in the current and previous diagnostics logs, for one session or all.

    Reads under the writers' lock. Malformed lines are skipped, so a damaged log
    only loses its own records. Rotation drops the oldest records, so the result
    never proves that every call left one. A log that is not a regular file or is
    too large raises ``ValueError``; a lock timeout raises ``filelock.Timeout``.
    """
    log = config.with_name("events.jsonl")
    receipts: dict[UUID, ReviewReceipt] = {}
    evidence = ReviewEvidence()
    with FileLock(str(config.with_name("diagnostics.lock")), timeout=2):
        for path in (log.with_suffix(".previous.jsonl"), log):
            contents = _read_private(path, MAX_EVENTS_BYTES)
            for line in (contents or b"").splitlines():
                if not line.strip():
                    continue
                try:
                    event = HookEvent.model_validate_json(line)
                except ValidationError:
                    continue
                if event.review is not None and native_session in (None, event.review.native_session):
                    receipts[event.review.receipt_id] = event.review
                if event.kind != "unrecorded_review" or event.reason is None:
                    continue
                gap = ReviewGap(
                    reason=event.reason,
                    native_session=event.native_session,
                    call_hash=event.call_hash,
                    tool_use_id=event.tool_use_id,
                )
                if gap.native_session is None:
                    evidence.unscoped_gaps.append(gap)
                elif native_session in (None, gap.native_session):
                    evidence.gaps.append(gap)
    evidence.receipts = list(receipts.values())
    return evidence
