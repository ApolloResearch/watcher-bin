"""Find the native call a preToolUse callback is about, linking it only when exactly one call matches.

The callback carries no call ID. Copilot writes each preToolUse hook invocation to
the session log as a ``hook.start`` record naming the session or subagent, working
directory and native calls, and a ``hook.end`` once the hook has answered.
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, JsonValue, ValidationError

from watcher_github_copilot_cli.diagnostics import UnrecordedReason
from watcher_github_copilot_cli.transcript import (
    JSON_OBJECT,
    MAX_HOOK_EVENT_BYTES,
    UNREADABLE_EVENT,
    IncompleteTranscriptError,
    NativeModel,
    SessionStartData,
    TranscriptError,
    check_deadline,
    convert_session,
    policy_call,
    read_events,
    session_state_dir,
    session_transcript_path,
    storable,
)

# How long a callback waits for its hook record to reach the log, within the gate's
# own deadline. Copilot normally writes the record before it starts the hook.
IDENTITY_WAIT_SECONDS = 5.0
POLL_SECONDS = 0.05
# Copilot timestamps the callback and its hook record separately, so the two can
# differ slightly. Time only narrows the candidates; the call must still match uniquely.
HOOK_CLOCK_TOLERANCE_MS = 1_000
# A damaged line could be a hidden hook record only if Copilot wrote it around the
# callback. Copilot appends events in time order (native logs were in order to the
# millisecond), so a damaged line followed by a readable event from before the
# candidate window was written before that window too and cannot be a candidate.
# This extra second is room for a write that lands slightly out of order.
LOG_ORDER_SLACK_MS = 1_000
# A subagent's calls are written to its parent's log while the callback runs, so
# only a log modified this shortly before the callback can hold the record.
RECENT_LOG_SECONDS = 5


class PendingTool(NativeModel):
    """Copilot's preToolUse payload; ``timestamp`` is milliseconds since the epoch."""

    toolName: Annotated[str, Field(min_length=1)]
    toolArgs: dict[str, JsonValue] | str
    sessionId: str | None = None
    cwd: str | None = None
    timestamp: int | None = None


def tool_arguments(value: dict[str, JsonValue] | str) -> dict[str, JsonValue]:
    """A call's arguments as an object; freeform text that is not a JSON object becomes ``{"input": text}``."""
    if isinstance(value, dict):
        return value
    try:
        return JSON_OBJECT.validate_json(value)
    except ValidationError:
        # Freeform tools such as GPT's apply_patch send raw text rather than JSON.
        # The transcript records them as custom calls with the text under "input".
        return {"input": value}


def submitted_call(pending: PendingTool) -> tuple[str, dict[str, JsonValue]]:
    """The tool name and arguments the gate submits, exactly as the transcript records the same call.

    Both use ``policy_call``'s Claude Code names, and Watcher strips NUL characters
    before storing, as the converter does, so a stored judgment's call matches the
    call in its transcript. Watcher refuses a stored gate request when they differ.
    """
    name, translated = policy_call(pending.toolName, tool_arguments(pending.toolArgs))
    return name, JSON_OBJECT.validate_python(storable(translated))


class HookTool(NativeModel):
    id: Annotated[str, Field(min_length=1)]
    name: str
    args: dict[str, JsonValue] | str


class HookInput(NativeModel):
    sessionId: str
    cwd: str
    toolCalls: list[HookTool]


class HookStartData(NativeModel):
    hookType: Literal["preToolUse"]
    hookInvocationId: str
    input: HookInput


class HookStart(NativeModel):
    timestamp: Annotated[datetime, Field(strict=False)]
    agentId: str | None = None
    data: HookStartData


class HookEndData(NativeModel):
    hookInvocationId: str


class HookEnd(NativeModel):
    data: HookEndData


class Stamped(NativeModel):
    timestamp: Annotated[datetime, Field(strict=False)]


class RecordedCall(NativeModel):
    id: str
    function: str
    arguments: dict[str, JsonValue]


class RecordedMessage(NativeModel):
    tool_calls: list[RecordedCall] = Field(default_factory=list)
    tool_call_id: str | None = None


class NativeCall(BaseModel):
    """The one native call a callback matched, with its conversation up to that call.

    ``session`` is the parent session whose log holds the call and ``agent_id`` the
    subagent that made it, if any. ``messages`` is that conversation as the
    recording hooks convert it, ending with the unanswered call, so it is a
    prefix of the conversation recording later stores under ``identity``.
    """

    session: UUID
    agent_id: str | None
    tool_use_id: str
    messages: list[dict[str, JsonValue]]

    @property
    def identity(self) -> str:
        """The conversation's external ID, the one ``recording.record_session`` gives it."""
        parent = f"github-copilot-cli:{self.session}"
        return parent if self.agent_id is None else f"{parent}:agent:{self.agent_id}"


class Resolution(BaseModel):
    """Either the matched ``call`` or the ``reason`` none could be linked."""

    call: NativeCall | None = None
    reason: UnrecordedReason | None = None


class Attempt(BaseModel):
    """One read of the logs; ``final`` results are not retried while the callback waits."""

    resolution: Resolution
    final: bool


def _gap(reason: UnrecordedReason, *, final: bool) -> Attempt:
    return Attempt(resolution=Resolution(reason=reason), final=final)


def _same(left: JsonValue, right: JsonValue) -> bool:
    """Exact JSON equality: unlike ``==``, ``1``, ``1.0`` and ``true`` differ."""
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def _candidate_logs(pending: PendingTool, deadline: float) -> tuple[list[Path], bool]:
    """The logs that can hold the callback's hook record, and whether that is the session's own log.

    A parent session's callback names its own log. A subagent's callback names the
    subagent, whose calls are in its parent's log, so every log written since
    shortly before the callback is searched. A log that cannot be inspected raises
    ``OSError``.
    """
    try:
        own = session_transcript_path(UUID(pending.sessionId or ""))
        if own.is_file():
            return [own], True
    except ValueError:
        pass
    assert pending.timestamp is not None
    since = pending.timestamp / 1000 - RECENT_LOG_SECONDS
    recent: list[Path] = []
    for path in sorted(session_state_dir().glob("*/events.jsonl")):
        check_deadline(deadline)
        try:
            if path.stat().st_mtime >= since:
                recent.append(path)
        except FileNotFoundError:
            continue
    return recent, False


def _actors(events: list[dict[str, JsonValue]]) -> set[str]:
    """Every subagent, and session, a log's events name, read without validating them."""
    actors: set[str] = set()
    for event in events:
        agent = event.get("agentId")
        if isinstance(agent, str) and agent:
            actors.add(agent)
        data = event.get("data")
        inputs = data.get("input") if event.get("type") == "hook.start" and isinstance(data, dict) else None
        if isinstance(inputs, dict) and isinstance(session := inputs.get("sessionId"), str) and session:
            actors.add(session)
    return actors


def _settled_through(events: list[dict[str, JsonValue]], before_ms: int, deadline: float) -> int:
    """The index of the last event with a readable, timezone-aware timestamp earlier than ``before_ms``, or -1.

    Copilot appends events in time order, so every line up to that index was written
    before ``before_ms``: a damaged line there cannot be a record from after it.
    The search stops at the first timestamp earlier than one before it. Such an
    event was appended out of order, for example by another process writing an
    old date after a damaged line, so it cannot show when the lines ahead of it
    were written.
    """
    settled = -1
    latest = None
    for index, event in enumerate(events):
        check_deadline(deadline)
        try:
            stamp = Stamped.model_validate(event).timestamp
        except ValidationError:
            continue
        if stamp.tzinfo is None:
            continue
        millis = round(stamp.timestamp() * 1000)
        if latest is not None and millis < latest:
            break
        latest = millis
        if millis < before_ms:
            settled = index
    return settled


def _recorded_call(
    events: list[dict[str, JsonValue]],
    session: UUID,
    agent_id: str | None,
    call_id: str,
    submitted: tuple[str, dict[str, JsonValue]],
    deadline: float,
) -> NativeCall | None:
    """The call ``call_id`` in its conversation up to the hook record, if recorded exactly as submitted.

    ``final=True`` converts a subagent that has not finished yet, the same way
    recording does when the session ends. The call must appear once, unanswered,
    with the submitted name and arguments; otherwise ``None``. An unsupported
    conversation raises ``TranscriptError``.
    """
    converted = convert_session(events, final=True, deadline=deadline)
    if agent_id is None:
        messages = converted.messages
    else:
        messages = next((history.messages for history in converted.subagents if history.agent_id == agent_id), [])
    calls: list[RecordedCall] = []
    answered = False
    for message in messages:
        check_deadline(deadline)
        parsed = RecordedMessage.model_validate(message)
        calls += [call for call in parsed.tool_calls if call.id == call_id]
        answered = answered or parsed.tool_call_id == call_id
    name, arguments = submitted
    if len(calls) != 1 or answered or calls[0].function != name or not _same(calls[0].arguments, arguments):
        return None
    return NativeCall(session=session, agent_id=agent_id, tool_use_id=call_id, messages=messages)


def _attempt(pending: PendingTool, deadline: float) -> Attempt:
    """Read the candidate logs once and link the callback only to a call no other record could also be.

    A candidate is an open preToolUse hook record within ``HOOK_CLOCK_TOLERANCE_MS``
    of the callback, for the same session or subagent and working directory, naming
    a native call with the same tool name and exact arguments. Candidates are counted
    across every log searched; a second one ends the search as ambiguous, whatever
    the order. So does such a record that has already ended: the log is
    agent-writable, and the callback's own invocation cannot have ended while it
    runs, so an ended match may be the real record closed by an appended hook end. A log that could hold a candidate must be readable around the
    callback: an unreadable line, a malformed preToolUse hook record or a malformed
    hook end written then could hide another candidate, or keep an answered one
    looking open, so nothing is linked. Damage written earlier is skipped, so one
    broken line does not stop decisions being stored for the rest of the session.
    Damage counts as earlier when a readable event after it is timestamped before
    the candidate window, less ``LOG_ORDER_SLACK_MS`` (see ``_settled_through``).
    An oversized event anywhere leaves the log unread. An unfinished final line and
    a record not yet written are retried while the callback waits. An expired
    monotonic ``deadline`` raises ``TimeoutError``.
    """
    assert pending.timestamp is not None
    submitted = submitted_call(pending)
    native_arguments = tool_arguments(pending.toolArgs)
    try:
        paths, own = _candidate_logs(pending, deadline)
    except TimeoutError:
        raise
    except OSError:
        return _gap("transcript_unsupported", final=True)
    reason: UnrecordedReason = "tool_call_id_not_found" if own else "subagent_no_log"
    found: NativeCall | None = None
    candidates = 0
    for path in paths:
        check_deadline(deadline)
        try:
            session = UUID(path.parent.name)
        except ValueError:
            continue
        try:
            events = read_events(session, path, deadline=deadline, max_event_bytes=MAX_HOOK_EVENT_BYTES)
        except IncompleteTranscriptError:
            return _gap("transcript_unsupported", final=False)
        except FileNotFoundError:
            continue
        except TimeoutError:
            raise
        except (TranscriptError, OSError):
            return _gap("transcript_unsupported", final=True)
        # Lines up to ``settled`` were written before any candidate could be, so
        # damage there is skipped; damage after it could hide a candidate.
        settled = _settled_through(events, pending.timestamp - HOOK_CLOCK_TOLERANCE_MS - LOG_ORDER_SLACK_MS, deadline)
        unreadable = any(event.get("type") == UNREADABLE_EVENT for event in events[settled + 1 :])
        if not own and not unreadable and pending.sessionId not in _actors(events):
            continue
        if unreadable:
            return _gap("transcript_unsupported", final=True)
        reason = "tool_call_id_not_found"
        try:
            start = next(event for event in events if event.get("type") == "session.start" and not event.get("agentId"))
            if SessionStartData.model_validate(start.get("data")).sessionId != session:
                return _gap("transcript_unsupported", final=True)
        except (StopIteration, ValidationError):
            return _gap("transcript_unsupported", final=True)
        ended: set[str] = set()
        for index, event in enumerate(events):
            check_deadline(deadline)
            if event["type"] != "hook.end":
                continue
            try:
                ended.add(HookEnd.model_validate(event).data.hookInvocationId)
            except ValidationError:
                if index > settled:
                    return _gap("transcript_unsupported", final=True)
        for index, event in enumerate(events):
            check_deadline(deadline)
            data = event.get("data")
            if event["type"] != "hook.start" or not isinstance(data, dict) or data.get("hookType") != "preToolUse":
                continue
            try:
                hook: HookStart | None = HookStart.model_validate(event)
            except ValidationError:
                hook = None
            if hook is None or hook.timestamp.tzinfo is None:
                if index > settled:
                    return _gap("transcript_unsupported", final=True)
                continue
            if (
                abs(round(hook.timestamp.timestamp() * 1000) - pending.timestamp) > HOOK_CLOCK_TOLERANCE_MS
                or hook.data.input.sessionId != pending.sessionId
                or (hook.agentId or str(session)) != pending.sessionId
                or hook.data.input.cwd != pending.cwd
            ):
                continue
            matching = [
                tool
                for tool in hook.data.input.toolCalls
                if tool.name == pending.toolName and _same(tool_arguments(tool.args), native_arguments)
            ]
            if matching and hook.data.hookInvocationId in ended:
                # This callback's own invocation is still running, so an ended match
                # in the window may be the real record with a hook.end appended to it.
                return _gap("tool_call_ambiguous", final=True)
            candidates += len(matching)
            if candidates > 1:
                return _gap("tool_call_ambiguous", final=True)
            if matching:
                try:
                    found = _recorded_call(
                        events[: index + 1], session, hook.agentId, matching[0].id, submitted, deadline
                    )
                except (TranscriptError, ValidationError):
                    return _gap("transcript_unsupported", final=True)
    if found is not None:
        return Attempt(resolution=Resolution(call=found), final=True)
    return _gap(reason, final=False)


async def resolve_pending(pending: PendingTool, *, deadline: float) -> Resolution:
    """The one native call this callback is about, or why it cannot be linked.

    Waits up to ``IDENTITY_WAIT_SECONDS`` for Copilot to write the hook record,
    within the absolute monotonic ``deadline``, whose expiry raises ``TimeoutError``.
    Identical candidates are never told apart by order: they stay unlinked, so a
    decision is never stored on, or a person's answer attributed to, the wrong call.
    """
    if not pending.sessionId:
        return Resolution(reason="subagent_no_log")
    if pending.timestamp is None or pending.cwd is None:
        return Resolution(reason="tool_call_id_not_found")
    check_deadline(deadline)
    wait_until = min(deadline, time.monotonic() + IDENTITY_WAIT_SECONDS)
    attempt: Attempt | None = None
    while True:
        try:
            # The read runs in a thread that stops itself at ``wait_until``, so an
            # abandoned read never outlives the callback.
            attempt = await asyncio.to_thread(_attempt, pending, wait_until)
        except TimeoutError:
            check_deadline(deadline)
            return attempt.resolution if attempt is not None else Resolution(reason="transcript_unsupported")
        if attempt.final or time.monotonic() + POLL_SECONDS >= wait_until:
            return attempt.resolution
        await asyncio.sleep(POLL_SECONDS)
