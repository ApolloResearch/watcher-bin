"""Copilot command hooks for recording, retrospective observation and a recorded tool veto.

Invoke ``observe`` at agentStop and sessionEnd, or ``enforce`` at preToolUse, with
the camelCase native payload on stdin. A successful gate leaves Copilot's own
permissions in place. Its outer hook timeout remains fail-open, regardless of this adapter.
"""

import asyncio
import json
import math
import os
import subprocess
import sys
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

import typer
from pydantic import BaseModel, JsonValue, ValidationError

from watcher_github_copilot_cli.configuration import API_KEY_UNSUPPORTED, SERVER_OPTION, load_configuration
from watcher_github_copilot_cli.diagnostics import (
    HookKind,
    SkipReason,
    UnrecordedReason,
    escalated_calls,
    read_review_evidence,
    record_escalation,
    record_event,
)
from watcher_github_copilot_cli.identity import (
    NativeCall,
    PendingTool,
    resolve_pending,
    submitted_call,
    tool_arguments,
)
from watcher_github_copilot_cli.monitoring import applied_decision, assess
from watcher_github_copilot_cli.recording import (
    PartialRecordingError,
    RecordedSession,
    record_session,
    upload_decisions,
)
from watcher_github_copilot_cli.reviews import call_hash, confirm_reviews, receipt
from watcher_github_copilot_cli.scopes import skip_reason
from watcher_github_copilot_cli.transcript import (
    ESCALATION_MESSAGE,
    JSON_OBJECT,
    MAX_HOOK_EVENT_BYTES,
    CompletedTurn,
    ConvertedSession,
    SessionEnded,
    TranscriptError,
    check_deadline,
    convert_session,
    is_subagent_stop,
    patch_paths,
    patch_tool,
    read_ended_session,
    read_events,
    session_transcript_path,
    wait_for_completed_session,
)
from watcher_sdk import (
    AsyncWatcherClient,
    IntegrationAuth,
    WatcherAuthenticationError,
    WatcherConnectionError,
    WatcherTimeoutError,
    async_client_from_watcher,
)

app = typer.Typer(invoke_without_command=True, pretty_exceptions_enable=False)

# The gate sends at most this much, conversation and pending call together. Watcher
# refuses hook requests over 8 MiB by default; the remaining 1 MiB covers the JSON
# envelope. A conversation over the budget is judged on its recent part without
# storing the decision, because a trimmed copy would fork the stored history.
MAX_CONTEXT_BYTES = 7 * 1024 * 1024
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
# Copilot gives sessionEnd hooks 1.5 seconds when an interactive session exits or is
# interrupted, then kills them. Those endings are recorded by a detached process,
# which outlives Copilot. Prompt-mode endings wait for the hook, so their failures
# are still reported.
DETACHED_ENDINGS = {"user_exit", "abort"}


class Escalation(PermissionError):
    """Watcher asks a person to approve the call before it runs."""


class PolicyDenial(PermissionError):
    """Watcher returned a validated policy denial."""


class AssessmentFailure(RuntimeError):
    """Transcript delivery was confirmed, but retrospective assessment failed."""


class ConfigurationError(RuntimeError):
    """The hook's configuration, or the credential it names, is missing or unreadable."""


class UnsupportedCredentialError(ConfigurationError):
    """A configuration from an earlier version names an API key, which is no longer accepted."""

    def __init__(self) -> None:
        super().__init__(API_KEY_UNSUPPORTED)


class ServerMismatchError(ConfigurationError):
    """The hook command and its private configuration name different Watcher servers.

    Something rewrote the configuration after setup; following it could send
    recordings and gate requests to a server that approves every call.
    """

    def __init__(self) -> None:
        super().__init__("The hook and its private configuration name different Watcher servers; run setup again")


@dataclass(frozen=True)
class GateContext:
    """What the gate sends with the pending call.

    ``call`` is the one native call the callback matched (see ``identity``). It is
    kept even when its conversation is too large to store, so an escalation of it
    is still remembered. The decision is stored on it only when ``unrecorded`` is
    ``None``, and ``messages`` is then its whole conversation. Otherwise
    ``unrecorded`` says why not, and ``messages`` is the most recent part of the
    conversation, or ``None`` without a readable log of this session. ``identity``
    is the conversation's external ID, sent whenever ``messages`` is.
    """

    messages: list[dict[str, JsonValue]] | None
    call: NativeCall | None = None
    unrecorded: UnrecordedReason | None = None
    identity: str | None = None

    @property
    def tool_use_id(self) -> str | None:
        """The native call the decision is stored on, if it can be stored."""
        return self.call.tool_use_id if self.call is not None and self.unrecorded is None else None


def read_conversation(session_id: str | None, *, deadline: float | None = None) -> ConvertedSession | UnrecordedReason:
    """Convert this session's log as it stands, or say why there is none to use.

    A subagent's call names the subagent, which has no log of its own, and older
    Copilot releases send no ``sessionId``. The log's final line may still be
    partly written. An expired monotonic ``deadline`` raises ``TimeoutError``.
    """
    check_deadline(deadline)
    try:
        native_id = UUID(session_id or "")
    except ValueError:
        return "subagent_no_log"
    path = session_transcript_path(native_id)
    if not path.is_file():
        return "subagent_no_log"
    try:
        events = read_events(
            native_id, path, allow_partial_tail=True, deadline=deadline, max_event_bytes=MAX_HOOK_EVENT_BYTES
        )
        return convert_session(events, deadline=deadline)
    except TimeoutError:
        raise
    except (ValueError, OSError):
        return "transcript_unsupported"


async def gate_context(pending: PendingTool, budget: int, *, deadline: float) -> GateContext:
    """Choose what to send with the pending call, storing the decision whenever that is possible.

    The decision is stored only on a call ``resolve_pending`` links with certainty,
    with that call's conversation, converted as the recording hooks convert it, so
    the stored transcript is a prefix of the next recording and Watcher extends it.
    When no call can be linked, or the conversation exceeds ``budget`` bytes, the
    call is judged with the most recent context that fits and nothing is stored.
    Context helps Watcher judge intent but is not required, so an unreadable log
    never withholds a tool. An expired monotonic ``deadline`` raises ``TimeoutError``.
    """
    resolved = await resolve_pending(pending, deadline=deadline)
    if resolved.call is not None:
        call = resolved.call
        size = 0
        for message in call.messages:
            check_deadline(deadline)
            size += len(json.dumps(message))
        if size <= budget:
            return GateContext(call.messages, call=call, identity=call.identity)
        return GateContext(
            recent_context(call.messages, budget, deadline=deadline),
            call=call,
            unrecorded="conversation_too_large",
            identity=call.identity,
        )
    assert resolved.reason is not None
    converted = read_conversation(pending.sessionId, deadline=deadline)
    if isinstance(converted, str):
        return GateContext(None, unrecorded=resolved.reason)
    return GateContext(
        recent_context(converted.messages, budget, deadline=deadline),
        unrecorded=resolved.reason,
        identity=f"github-copilot-cli:{pending.sessionId}",
    )


def _record_unrecorded(
    config: Path | None, pending: PendingTool, gate: GateContext, reason: UnrecordedReason, fingerprint: str
) -> None:
    """Save why the review is not stored, naming the call only by its session, a hash and a linked ID.

    The session is the linked call's, or else the callback's own session when that
    has a log; a subagent's unlinked call has no proven session and is left unscoped.
    """
    session: UUID | None = gate.call.session if gate.call is not None else None
    if session is None:
        try:
            own = UUID(pending.sessionId or "")
            session = own if session_transcript_path(own).is_file() else None
        except ValueError:
            session = None
    record_event(
        config,
        "unrecorded_review",
        hook="enforce",
        reason=reason,
        native_session=session,
        call_hash=fingerprint,
        tool_use_id=gate.call.tool_use_id if gate.call is not None else None,
    )


def recent_context(
    messages: list[dict[str, JsonValue]], budget: int, *, deadline: float | None = None
) -> list[dict[str, JsonValue]]:
    """The most recent part of ``messages`` within ``budget`` bytes, starting at a user message.

    An expired monotonic ``deadline`` raises ``TimeoutError``.
    """
    check_deadline(deadline)
    kept, size = len(messages), 0
    while kept > 0:
        check_deadline(deadline)
        item = len(json.dumps(messages[kept - 1]))
        if size + item > budget:
            break
        size += item
        kept -= 1
    if kept > 0:
        # Trimmed: start at a user message, so the kept part never begins with a
        # tool result whose call was cut off.
        while kept < len(messages) and messages[kept]["role"] != "user":
            check_deadline(deadline)
            kept += 1
    check_deadline(deadline)
    return messages[kept:]


def further_path_checks(name: str, arguments: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    """Each path after the first that an ``apply_patch`` patch names, as its own policy call.

    ``policy_call`` names a multi-file patch's call after its first path, and Edit
    and Write rules match ``file_path`` alone, so the gate judges every further path
    as a ``Write`` (added file or ``Move to`` target) or ``Edit`` carrying the same
    patch, the same way ``patch_tool`` names the first.
    """
    patch = arguments.get("input")
    if name != "apply_patch" or not isinstance(patch, str):
        return []
    return [
        {"tool_name": patch_tool(header), "tool_input": {"file_path": path, "input": patch}}
        for header, path in patch_paths(patch)[1:]
    ]


def _severity(decision: JsonValue) -> int:
    """How strongly a decision restricts a call: 2 for deny, 1 for escalate, otherwise 0."""
    return {"escalate": 1, "deny": 2}.get(decision, 0) if isinstance(decision, str) else 0


async def apply_policy(
    client: AsyncWatcherClient,
    payload: Mapping[str, JsonValue],
    *,
    hook_timeout: int | None = None,
    config: Path | None = None,
) -> Literal["allow", "deferred"]:
    """Judge this invocation with the conversation so far, storing the decision on its native call.

    The call is named by its native ID and sent with the whole conversation, so
    Watcher records both and the Analyzer shows the decision on that call. A
    content-free receipt of the validated answer is saved beside ``config``, which
    recording later checks against what Watcher stored (see ``reviews``). When
    storing is impossible (see ``gate_context``), the call is judged ephemerally,
    which stores nothing, and the reason is saved to the diagnostics instead.
    A multi-file patch's further paths are judged first, ephemerally, and the
    strictest decision applies. When one of them is judged deny or escalate, the
    first path is judged ephemerally too, and the strictest judgment of all the
    paths is saved as a receipt for recording to store on the call once the
    transcript is confirmed (``stored_by="recording"``; see
    ``recording.upload_decisions``), so the call shows the decision that governed it.
    Returns ``"allow"`` for an approval, including an administrator's configured
    allow on grading failure, and ``"deferred"`` when observe or paused mode leaves
    the call to Copilot's own permissions. Denials and invalid outcomes raise
    ``PolicyDenial`` or another error; an escalation raises ``Escalation``. The SDK deadline must remain below Copilot's configured outer
    timeout, which is fail-open, so with ``hook_timeout``, the installed hook's
    timeout, it ends 60 seconds before it.
    """
    try:
        pending = PendingTool.model_validate(payload)
    except ValidationError:
        raise ValueError("A tool name and argument object are required") from None
    arguments = tool_arguments(pending.toolArgs)
    timeout = float(os.environ.get("WATCHER_TIMEOUT_SECONDS", "420"))
    if not math.isfinite(timeout) or not 0 < timeout <= 420:
        raise ValueError("Watcher timeout must be between zero and 420 seconds")
    if hook_timeout is not None:
        # An install from an earlier version of this sample may have a shorter hook timeout.
        timeout = min(timeout, hook_timeout - 60)
        if timeout <= 0:
            raise ValueError("The installed hook timeout leaves no time for Watcher")
    # The deadline starts before the log is read, so reading it counts against the
    # time left before Copilot's fail-open outer timeout.
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    tool_name, tool_input = submitted_call(pending)
    submitted: dict[str, JsonValue] = {"tool_name": tool_name, "tool_input": tool_input}
    if pending.cwd:
        submitted["cwd"] = pending.cwd
    fingerprint = call_hash(tool_name, tool_input)
    # A large pending call, such as a big create, leaves less room for context.
    gate = await gate_context(pending, MAX_CONTEXT_BYTES - len(json.dumps(submitted)), deadline=deadline)
    if gate.unrecorded is not None:
        _record_unrecorded(config, pending, gate, gate.unrecorded, fingerprint)
    # A subagent's call is named by its own conversation's ID, never as a Copilot
    # session of its own, and an unlinked one without its parent's log by none.
    external_ids = {"other": gate.identity} if gate.identity is not None else None
    if loop.time() >= deadline:
        raise TimeoutError("Reading the Copilot log used the whole deadline")
    further = [
        check | ({"cwd": pending.cwd} if pending.cwd else {})
        for check in further_path_checks(pending.toolName, arguments)
    ]
    # The SDK timeout applies to each connection phase, so a slowly trickling response
    # could outlast Copilot's fail-open outer timeout. This bounds the whole exchange.
    async with asyncio.timeout_at(deadline):
        # Watcher stores one decision per call, and judges it on the call's first
        # path alone. So the further paths of a multi-file patch are judged first,
        # without storing anything. If one of them is judged deny or escalate, the
        # first path's decision could be less strict than what the gate does, and
        # storing it would show a withheld call as allowed. The first path is then
        # judged without storing too, and recording stores the strictest judgment
        # afterwards (see below).
        checks = await asyncio.gather(
            *(
                client.pre_tool_use_hook(
                    input=check,
                    messages=gate.messages or [],
                    ephemeral=True,
                    mode="full",
                    timeout=deadline - loop.time(),
                )
                for check in further
            )
        )
        if any(isinstance(result, list) for result in checks):
            raise ValueError("Watcher returned an unexpected batch result")
        decisions = [applied_decision(result, None) for result in checks]
        # The judgment counts, not the applied decision, so in observe mode too the
        # gate stores no decision whose judgment is milder than a later path's.
        restricted = any(_severity(result.to_dict().get("judged_decision")) > 0 for result in checks)
        stored_id = None if restricted else gate.tool_use_id
        result = None
        # A later path's deny has already withheld the call, so the first path needs
        # no judgment. That deny was also judged, so nothing is stored here either.
        if "deny" not in decisions:
            result = await client.pre_tool_use_hook(
                input=submitted | ({"tool_use_id": stored_id} if stored_id is not None else {}),
                messages=gate.messages or [],
                external_ids=external_ids,
                ephemeral=stored_id is None,
                mode="full",
                timeout=deadline - loop.time(),
            )
    if isinstance(result, list):
        raise ValueError("Watcher returned an unexpected batch result")
    first = applied_decision(result, stored_id) if result is not None else None
    if gate.call is not None and gate.tool_use_id is not None:
        if stored_id is not None:
            assert result is not None
            review = receipt(
                result,
                native_session=gate.call.session,
                identity=gate.call.identity,
                tool_use_id=stored_id,
                fingerprint=fingerprint,
            )
        else:
            # Watcher refuses a stored gate request whose tool name or arguments differ
            # from the call in the transcript, so a later path's judgment cannot be
            # stored here. Recording stores the strictest judgment of all the paths on
            # the call instead, once Watcher has the transcript. On a tie the first
            # path's own judgment is kept.
            strictest = max(
                [result, *checks] if result is not None else checks,
                key=lambda judged: (
                    _severity(judged.to_dict().get("decision")),
                    _severity(judged.to_dict().get("judged_decision")),
                ),
            )
            review = receipt(
                strictest,
                native_session=gate.call.session,
                identity=gate.call.identity,
                tool_use_id=gate.call.tool_use_id,
                fingerprint=fingerprint,
                stored_by="recording",
            )
        record_event(config, "reviewed", review=review)
    if first == "deny" or "deny" in decisions:
        raise PolicyDenial("Watcher withheld this call")
    if "escalate" in (first, *decisions):
        if gate.call is not None:
            record_escalation(config, gate.call.session, gate.call.tool_use_id)
        raise Escalation("Watcher asks for approval of this call")
    return "allow" if first == "allow" else "deferred"


async def _sync_decisions(
    client: AsyncWatcherClient,
    recorded: RecordedSession,
    native_id: UUID,
    session: ConvertedSession,
    config: Path | None,
) -> None:
    """Upload the gate's judgments left for recording and people's answers to its prompts; failures are saved.

    The judgments are the receipts the gate saved beside ``config`` with
    ``stored_by="recording"`` for the native session ``native_id`` (see
    ``apply_policy``). Each goes to the Watcher session that ``recorded`` confirmed
    for its conversation, the parent's or a subagent's; one whose conversation was
    not confirmed waits for a later callback. Answers come from Copilot's log,
    which the agent can append to, so only answers to calls the gate escalated in
    ``native_id``, as recorded beside ``config``, are uploaded; they belong to the
    parent conversation. Without ``config`` there is no such record, and nothing is
    uploaded. Recording is already confirmed, so a failed upload is saved as an
    ``unsynced_decisions`` event, never raised. The next callback uploads everything
    again, and the server keeps what is stored.
    """
    if config is None:
        return
    parent = f"github-copilot-cli:{native_id}"
    conversations = {parent: (recorded.session, session.messages)} | {
        f"{parent}:agent:{history.agent_id}": (recorded.subagents[history.agent_id], history.messages)
        for history in session.subagents
        if history.agent_id in recorded.subagents
    }
    try:
        async with asyncio.timeout(10):
            evidence = await asyncio.to_thread(read_review_evidence, config, native_id)
            judgments = [item for item in evidence.receipts if item.stored_by == "recording"]
            escalated = escalated_calls(config, native_id) if session.human_responses else set()
            responses = [response for response in session.human_responses if response.tool_use_id in escalated]
            for identity, (session_id, messages) in conversations.items():
                selected = [item for item in judgments if item.identity == identity]
                answers = responses if identity == parent else []
                if selected or answers:
                    await upload_decisions(client, session_id, messages, selected, answers)
    except Exception:
        record_event(config, "unsynced_decisions")


async def _confirm_judgments(client: AsyncWatcherClient, native_id: UUID, config: Path | None) -> None:
    """Read back the gate's stored judgments for this session once its transcript is confirmed.

    The result is saved as its own diagnostic and never raised, so a judgment that
    cannot be confirmed never reports the confirmed transcript as undelivered.
    Without ``config`` there are no receipts to check.
    """
    if config is not None:
        await confirm_reviews(client, config, native_session=native_id)


async def observe_callback(
    client: AsyncWatcherClient, payload: Mapping[str, JsonValue], *, grade: bool, config: Path | None = None
) -> RecordedSession | None:
    """Record an agentStop or sessionEnd payload, with retrospective assessment when ``grade``.

    agentStop waits for its own completed turn, records the parent and every
    finished subagent, then assesses that turn's calls. sessionEnd, and replay,
    record the session as it stands, including subagents that finished after the
    last turn, without assessing it again. A subagent's own agentStop records
    nothing, because the parent is still mid-turn. Returns ``None`` when there is
    nothing to record yet. With ``config``, persist confirmed delivery, store the
    judgments and answers recording uploads (see ``_sync_decisions``), then read
    back the gate's stored judgments for the session, before assessment; a later
    grading failure raises ``AssessmentFailure``.

    When the parent is confirmed but a subagent is not, the parent's delivery is
    still saved and its turn still assessed before ``PartialRecordingError`` is
    raised, so one subagent that cannot be stored never hides the parent's
    delivery or stops its assessment. A failed assessment is then saved as a
    separate diagnostic, because the recording failure is the one reported.
    A log with events the converter left out is recorded as usual, after a
    ``skipped_events`` diagnostic.
    """
    if "transcriptPath" not in payload:
        ended = SessionEnded.model_validate(payload)
        session = await read_ended_session(payload, 5)
        if not session.replied:
            # Before the first reply, Copilot can still add system instructions that
            # belong ahead of the first user message. Storing such an early history would
            # let a resumed session reorder its start and fork the stored trajectory, and
            # there is no agent output to monitor yet.
            return None
        if session.skipped_events:
            record_event(config, "skipped_events")
        try:
            recorded = await record_session(client, ended.sessionId, session, timeout_seconds=25)
        except PartialRecordingError as error:
            record_event(config, "recorded", session=error.recorded.session)
            await _sync_decisions(client, error.recorded, ended.sessionId, session, config)
            await _confirm_judgments(client, ended.sessionId, config)
            raise
        record_event(config, "recorded", session=recorded.session)
        await _sync_decisions(client, recorded, ended.sessionId, session, config)
        await _confirm_judgments(client, ended.sessionId, config)
        return recorded
    if is_subagent_stop(payload):
        return None
    turn = CompletedTurn.model_validate(payload)
    session = await wait_for_completed_session(payload, 5)
    if session.skipped_events:
        record_event(config, "skipped_events")
    try:
        recorded = await record_session(client, turn.sessionId, session, timeout_seconds=25)
    except PartialRecordingError as error:
        record_event(config, "recorded", session=error.recorded.session)
        await _sync_decisions(client, error.recorded, turn.sessionId, session, config)
        await _confirm_judgments(client, turn.sessionId, config)
        if grade:
            try:
                await _assess_turn(client, turn, session)
            except AssessmentFailure:
                record_event(config, "failed", failure="evaluation", hook="observe")
        raise
    record_event(config, "recorded", session=recorded.session)
    await _sync_decisions(client, recorded, turn.sessionId, session, config)
    await _confirm_judgments(client, turn.sessionId, config)
    if grade:
        await _assess_turn(client, turn, session)
    return recorded


class WatcherSettings(BaseModel):
    watcher_url: str
    hook_timeout: int | None = None
    watcher_auth: bool = False
    watcher_state_dir: Path | None = None
    auth_profile: IntegrationAuth | None = None

    def create_client(self) -> AsyncWatcherClient:
        if self.auth_profile is not None:
            return self.auth_profile.create_client()
        if self.watcher_auth:
            return async_client_from_watcher(
                self.watcher_url, state_dir=self.watcher_state_dir, timeout=10, max_retries=0
            )
        raise ValueError("The configuration names no Watcher login")


async def _assess_turn(client: AsyncWatcherClient, turn: CompletedTurn, session: ConvertedSession) -> None:
    """Assess the completed turn's calls; any failure raises ``AssessmentFailure``.

    Flush (5 s), recording (25 s), uploading decisions (10 s), judgment readback (5 s)
    and assessment (40 s) stay within the demo hook's 90-second timeout.
    """
    try:
        await assess(client, "github-copilot-cli:" + str(turn.sessionId), session.messages, start=session.turn_start)
    except Exception as error:
        raise AssessmentFailure("Retrospective assessment failed") from error


def watcher_settings(config: Path | None, watcher_url: str | None = None) -> WatcherSettings:
    """Read the destination, login and gate timeout from the configuration setup wrote.

    Hooks authenticate only with the user's login named in ``--config``; there is no
    environment-variable fallback. A missing ``config`` raises ``ValueError``, and a
    configuration from an earlier version that names an API key raises
    ``UnsupportedCredentialError``.

    ``watcher_url`` is the server the hook command names; hooks from earlier
    versions name none and are not checked. A configuration that names another
    server raises ``ServerMismatchError``. The check runs on the settings this
    returns, from a single read of the file, so a process that replaces the file
    between a check and a second read cannot redirect the hook. Setup stores the
    server without a trailing slash; a hand-written hook may add one.
    """
    if config is None:
        raise ValueError("Hooks need --config with the configuration setup wrote")
    try:
        settings = load_configuration(config)
    except ValueError as error:
        if API_KEY_UNSUPPORTED in str(error):
            raise UnsupportedCredentialError from None
        raise
    if watcher_url is not None and settings.watcher_url != watcher_url.rstrip("/"):
        raise ServerMismatchError
    return WatcherSettings(
        watcher_url=settings.watcher_url,
        hook_timeout=settings.gate.timeoutSec if settings.gate else None,
        watcher_auth=settings.watcher_auth,
        watcher_state_dir=settings.watcher_state_dir,
        auth_profile=settings.auth_profile,
    )


async def run_hook(
    mode: str, payload: Mapping[str, JsonValue], config: Path | None, *, grade: bool, watcher_url: str | None = None
) -> RecordedSession | Literal["allow", "deferred"] | None:
    """Call the public SDK; observation uses real native identities after execution.

    Enforce returns the gate's applied decision; observation returns what it recorded.

    A missing or unreadable configuration or credential raises ``ConfigurationError``,
    and a configuration naming another server than ``watcher_url`` raises ``ServerMismatchError``.
    """
    try:
        settings = watcher_settings(config, watcher_url)
    except ConfigurationError:
        raise
    except (KeyError, OSError, ValueError) as error:
        raise ConfigurationError("The Watcher configuration or credential is missing or unreadable") from error
    async with settings.create_client() as client:
        if mode == "enforce":
            return await apply_policy(client, payload, hook_timeout=settings.hook_timeout, config=config)
        else:
            return await observe_callback(client, payload, grade=grade, config=config)
    return None


def _denial_reason(error: Exception) -> str:
    """A fixed reason for Copilot's denial; never the payload or a service message."""
    if isinstance(error, PolicyDenial):
        return "Watcher withheld this tool call"
    if isinstance(error, (UnsupportedCredentialError, ServerMismatchError)):
        return str(error)
    if isinstance(error, WatcherAuthenticationError):
        return "Watcher rejected the credential. Sign in again before retrying this tool call"
    if isinstance(error, (WatcherConnectionError, WatcherTimeoutError, TimeoutError)):
        return "Watcher could not be reached in time, so the tool call was withheld"
    return "Watcher could not evaluate this tool call, so it was withheld"


def recording_failure(error: Exception) -> str:
    """A fixed, content-free description of why recording was not confirmed."""
    if isinstance(error, (TranscriptError, UnsupportedCredentialError, ServerMismatchError)):
        return str(error)
    if isinstance(error, ConfigurationError):
        return "Watcher configuration or credential is missing or unreadable"
    if isinstance(error, ValidationError):
        return "Malformed Copilot callback"
    if isinstance(error, WatcherAuthenticationError):
        return "Watcher rejected the credential; sign in again"
    if isinstance(error, (WatcherConnectionError, WatcherTimeoutError, TimeoutError)):
        return "Watcher was unreachable or the recording deadline expired"
    if isinstance(error, OSError):
        return "Copilot transcript or configuration could not be read"
    return "Recording or retrospective assessment failed"


def record_in_background(raw: str, arguments: list[str]) -> None:
    """Start a detached ``observe`` with these arguments and pass it the payload."""
    worker = subprocess.Popen(
        [sys.executable, "-I", "-m", "watcher_github_copilot_cli.cli", *arguments, "--in-background"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )
    assert worker.stdin is not None
    worker.stdin.write(raw)
    worker.stdin.close()


# How long a hook waits for the opt-out check before handling the callback anyway.
# The check runs before the gate's own deadline starts, and Copilot's outer timeout
# lets the tool run, so a slow check must not use up the hook's time.
SCOPE_SECONDS = 5.0


def _skip_reason_in_time(config: Path, payload: Mapping[str, JsonValue], hook: HookKind) -> SkipReason | None:
    """``scopes.skip_reason`` for this callback, or ``None`` when it does not finish within ``SCOPE_SECONDS``.

    The check runs in a daemon thread, so one stuck on a slow file system never
    keeps the hook from answering or from exiting. An unexpected error in it is
    saved as a ``configuration`` failure of ``hook`` instead of printing a
    traceback, and also gives ``None``, so the callback is recorded and judged.
    """
    found: list[SkipReason | None] = []

    def check() -> None:
        try:
            found.append(skip_reason(config, payload))
        except Exception:
            record_event(config, "failed", failure="configuration", hook=hook)

    worker = threading.Thread(target=check, daemon=True)
    worker.start()
    worker.join(SCOPE_SECONDS)
    return found[0] if found else None


def dispatch_hook(
    mode: str,
    config: Path | None = None,
    *,
    grade: bool = True,
    detachable: bool = False,
    watcher_url: str | None = None,
) -> None:
    """Emit one native decision without copying input or service errors into logs.

    A failed observation exits with status 2 so Copilot shows the warning. Enforce
    answers as Watcher's Claude Code hook does: an explicit allow when Watcher
    approves, which skips Copilot's own permission prompt, ask when Watcher
    escalates, and deny when Watcher withholds the call or does not confirm
    approval. Only observe and paused mode answer with no decision, leaving the
    call to Copilot's own permissions. With ``detachable``, an interactive session
    ending is handed to a detached process. Both processes persist diagnostic
    events alongside the private configuration, including background failures.
    With ``watcher_url``, a configuration naming another server is refused as a
    configuration failure: the gate denies the call and observation warns. A
    detached process receives the same ``watcher_url`` and refuses it itself.

    In a project opted out of this sample's hooks (see ``scopes.skip_reason``),
    personal and project installs alike answer no decision and record nothing,
    saving only a ``skipped`` event, so Copilot's own permissions apply. A check
    that does not finish within ``SCOPE_SECONDS`` handles the callback as usual.
    An interactive session ending is detached before the check, which the
    detached process then makes, so a slow check cannot use up the short time
    Copilot gives those callbacks.
    """
    try:
        raw = sys.stdin.read(MAX_PAYLOAD_BYTES + 1)
        if len(raw) > MAX_PAYLOAD_BYTES:
            raise ValueError("Hook payload exceeds its size limit")
        payload = JSON_OBJECT.validate_json(raw)
        if detachable and "transcriptPath" not in payload and payload.get("reason") in DETACHED_ENDINGS:
            # Copilot stops these hooks within about 1.5 seconds, and saving diagnostics
            # can wait longer for its lock, so the hand-off comes first. The detached
            # process, which runs without ``detachable``, saves its own events and
            # checks for an opt-out itself.
            arguments = [
                "observe",
                *(["--config", str(config)] if config else []),
                *([SERVER_OPTION, watcher_url] if watcher_url else []),
                *([] if grade else ["--record-only"]),
            ]
            record_in_background(raw, arguments)
            record_event(config, "detached")
            sys.stdout.write("{}\n")
            return
        record_event(config, "started")
        if (
            skipped := _skip_reason_in_time(config, payload, "enforce" if mode == "enforce" else "observe")
            if config is not None
            else None
        ) is not None:
            record_event(config, "skipped", skip=skipped)
        else:
            result = asyncio.run(run_hook(mode, payload, config, grade=grade, watcher_url=watcher_url))
            if mode == "enforce":
                record_event(config, "allowed" if result == "allow" else "deferred")
                if result == "allow":
                    approval = {"permissionDecision": "allow", "permissionDecisionReason": "Watcher approved this call"}
                    sys.stdout.write(json.dumps(approval) + "\n")
                    return
            elif result is None:
                record_event(config, "completed")
    except Exception as error:
        if isinstance(error, Escalation):
            record_event(config, "escalated")
        elif isinstance(error, PolicyDenial):
            record_event(config, "denied")
        else:
            record_event(
                config,
                "failed",
                failure=(
                    "configuration"
                    if isinstance(error, ConfigurationError)
                    else "evaluation"
                    if isinstance(error, AssessmentFailure)
                    else "authentication"
                    if isinstance(error, WatcherAuthenticationError)
                    else "connection"
                    if isinstance(error, (WatcherConnectionError, WatcherTimeoutError, TimeoutError))
                    else "recording"
                    if mode == "observe"
                    else "evaluation"
                ),
                hook="enforce" if mode == "enforce" else "observe",
            )
        if mode == "enforce":
            if isinstance(error, Escalation):
                answer = {
                    "permissionDecision": "ask",
                    "permissionDecisionReason": ESCALATION_MESSAGE,
                }
            else:
                answer = {"permissionDecision": "deny", "permissionDecisionReason": _denial_reason(error)}
            sys.stdout.write(json.dumps(answer) + "\n")
            return
        if isinstance(error, AssessmentFailure):
            sys.stderr.write("Watcher recorded this turn but could not complete retrospective assessment.\n")
        else:
            sys.stderr.write(f"Watcher did not confirm this recording: {recording_failure(error)}.\n")
        sys.stdout.write("{}\n")
        raise typer.Exit(2) from None
    sys.stdout.write("{}\n")


@app.callback()
def show_help(ctx: typer.Context) -> None:
    """Read a native JSON hook payload with the observe or enforce command."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command("help", hidden=True)
def help_command(ctx: typer.Context) -> None:
    """Show command usage without reading stdin or contacting Watcher."""
    assert ctx.parent is not None
    typer.echo(ctx.parent.get_help())


ConfigOption = Annotated[Path | None, typer.Option(help="Configuration written by setup.")]
ServerOption = Annotated[
    str | None,
    typer.Option(SERVER_OPTION, help="Watcher server setup configured; refuse a configuration that names another."),
]


@app.command("observe")
def observe_command(
    config: ConfigOption = None,
    record_only: Annotated[
        bool, typer.Option(help="Record without assessing calls, for example when blocking review already judges them.")
    ] = False,
    in_background: Annotated[bool, typer.Option(hidden=True)] = False,
    watcher_url: ServerOption = None,
) -> None:
    """Record, and assess the turn's calls, at agentStop; record the final state at sessionEnd."""
    dispatch_hook("observe", config, grade=not record_only, detachable=not in_background, watcher_url=watcher_url)


@app.command("enforce")
def enforce_command(config: ConfigOption = None, watcher_url: ServerOption = None) -> None:
    """Withhold the pending tool unless Watcher approves it, storing the decision on the recorded call.

    A valid answer in observe or paused mode leaves the call to Copilot's own permissions.
    """
    dispatch_hook("enforce", config, watcher_url=watcher_url)


def main() -> None:
    """Run the installed command; no arguments display help instead of reading stdin."""
    app()


if __name__ == "__main__":
    main()
