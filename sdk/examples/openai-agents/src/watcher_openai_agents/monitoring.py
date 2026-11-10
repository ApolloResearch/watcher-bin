"""Apply Watcher decisions at the framework's native before-tool boundary.

One Monitor follows the server's enforce, observe or paused setting. Human
approvals can be supplied through an awaited application callback; without one,
escalations block. Refused and cancelled calls are reported to Watcher as
blocked or cancelled. Transcript submission does not acknowledge durable storage.
"""

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Literal, NoReturn

import httpx

from watcher_openai_agents.adapter import mark_tool_errors, messages_for_watcher
from watcher_sdk import (
    AsyncWatcherClient,
    TrajectoryView,
    WatcherAPIError,
    WatcherConnectionError,
    WatcherNotFoundError,
    WatcherRateLimitError,
    WatcherTimeoutError,
)

# Decision sources of a Watcher evaluation; bypassed and unevaluated records have
# none. report_status and human decisions upload an outcome only onto a recorded
# evaluation, which they wait for and then check is unchanged by the upload.
EVALUATED_SOURCES = frozenset({"threshold", "rule", "triage", "policy_gateway", "grading_error"})

# Seconds between lookups while waiting for Watcher to store a call: the pause
# doubles from the first value up to the cap, so a slow store costs few requests.
FIRST_POLL_INTERVAL = 0.1
MAX_POLL_INTERVAL = 1.0


def retryable(error):
    """Whether a status report that failed with ``error`` may succeed if retried later.

    Watcher not storing the call before the deadline, a transport failure, rate
    limiting and server errors may pass. A refused permission, a rejected
    request, or a stored call that contradicts the reported one will not. The
    SDK raises its own errors for a failed connection or a timeout, but passes
    a connection dropped mid-request through as httpx's error.
    """
    if isinstance(error, TimeoutError | WatcherConnectionError | WatcherTimeoutError | WatcherRateLimitError):
        return True
    if isinstance(error, httpx.NetworkError | httpx.RemoteProtocolError):
        return True
    return isinstance(error, WatcherAPIError) and error.status_code >= 500


def same_json_arguments(left, right):
    """Compare JSON values without Python's bool/number equality coercion.

    Object-key order is immaterial; array order and JSON literal types must match.
    Non-JSON values and non-finite numbers fail before execution is authorized.
    """
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def outcome_payload(call_id, name, arguments, status):
    """Build a decision upload that reports only an execution status.

    The ``not_evaluated`` fields mark it as carrying no Watcher evaluation, so
    the server keeps the call's recorded evaluation and merges in the status.
    """
    return {
        "tool_use_id": call_id,
        "tool_name": name,
        "raw_tool_call": {"tool_name": name, "tool_input": deepcopy(arguments)},
        "policy_decision": "not_evaluated",
        "applied_decision": "not_evaluated",
        "decision_source": "not_evaluated",
        "tool_status": status,
    }


class ToolBlocked(RuntimeError):
    """Watcher denied a call or the integration could not safely interpret its result."""


class ApprovalRequired(ToolBlocked):
    """A human must approve this pending call; unattended callers must not execute it."""


class StatusNotRecorded(ToolBlocked):
    """record() sent the transcript, but could not confirm the status of some withheld calls.

    ``failures`` maps each such call ID to the error its report failed with.
    An upload can be stored before its readback fails, so a status may exist
    although it was not confirmed. The next record() retries the IDs in
    ``retrying``; the Monitor stopped reporting the others and lists them in
    Monitor.unrecorded.
    """

    def __init__(self, failures: dict[str, BaseException], retrying: set[str]):
        super().__init__(f"Watcher did not confirm the status of withheld calls {sorted(failures)}")
        self.failures = failures
        self.retrying = frozenset(retrying)


class Monitor:
    """One conversation's policy decisions and final transcript submissions.

    The server's mode is inherited by default. An explicit enforcement selection
    requests an override and can be rejected by an administrator lock. Deferred
    decisions preserve the framework's ordinary dispatch and permission checks.
    Denials block. Escalations wait for approval_callback when supplied; its
    only approving result is literal True. The callback must obtain an authorized
    human choice, not call a model to approve. The choice is then recorded through
    the public decision-upload API before an approved call is released. This needs
    session read access and owner/write-any authority; reporting failure blocks.
    Recent human choices are included as context in later hook requests.
    With no callback, escalations block.

    Keep one instance per conversation and retain the conversation ID across
    turns. Failed attempts consume their call IDs; this object never retries a
    tool or grading request. In-memory state is not durable exactly-once execution.

    Responses history cannot say that a call failed or was refused, and Watcher
    records a call it let through whose later result has no ``error`` as
    completed. A call this Monitor refuses (a denial, or an escalation nobody
    approves) is reported as blocked, and one cancelled while it is decided as
    cancelled, through the same decision upload as a human choice; its result
    text stays as the agent saw it. A call withheld before Watcher answered (a
    monitoring failure or a cancellation), or whose report failed, is reported
    after the next record() instead. Tool exceptions are execution failures: the
    Monitor remembers each one reported through mark_failed and sends that call's
    result with ``error``.
    """

    def __init__(
        self,
        client: AsyncWatcherClient,
        conversation_id: str,
        *,
        timeout=420,
        enforcement: Literal["server", "enforce", "observe", "paused"] = "server",
        approval_callback: Callable[..., Awaitable[bool]] | None = None,
        human_audit_timeout: float = 10,
        late_report_attempts: int = 3,
    ):
        if not conversation_id or timeout <= 0:
            raise ValueError("A conversation ID and positive grading timeout are required")
        self.client = client
        self.external_ids = {"other": f"openai-agents:{conversation_id}"}
        self.timeout = timeout
        if enforcement not in {"server", "enforce", "observe", "paused"}:
            raise ValueError("Unsupported enforcement setting")
        self.settings = None if enforcement == "server" else {"enforcement": {"mode": enforcement}}
        if human_audit_timeout <= 0:
            raise ValueError("A positive human decision recording deadline is required")
        if late_report_attempts < 1:
            raise ValueError("At least one late status report attempt is required")
        self.approval_callback = approval_callback
        self.human_audit_timeout = human_audit_timeout
        self.late_report_attempts = late_report_attempts
        self.prior_decisions: list[dict] = []
        self.attempted = set()
        # Calls before() let run. Any result Watcher holds for a call submitted
        # but never released is refusal text, so a person's rejection of it may
        # replace the status Watcher settled from that text.
        self.released: set[str] = set()
        # Calls whose Watcher evaluation this Monitor received: only those can
        # have a recorded decision for report_status to update.
        self.evaluated: set[str] = set()
        # Calls whose blocked or cancelled status this Monitor has recorded or is
        # recording, including a person's rejection. A call is claimed before the
        # upload starts, so the first report stands; a failed upload releases the
        # claim for a later retry.
        self.reported: set[str] = set()
        # Withheld calls whose status is not yet recorded, as (name, arguments,
        # status): record() reports them once Watcher has stored the call.
        self.unreported: dict[str, tuple[str, object, str]] = {}
        # How many record() calls have failed to report each call in unreported.
        self.late_attempts: dict[str, int] = {}
        # Withheld calls the Monitor stopped reporting, with the error the last
        # report failed with: a permanent failure, or late_report_attempts
        # retryable ones. Their status is unconfirmed, not necessarily absent:
        # an upload can be stored before its readback fails. Nothing retries
        # these automatically.
        self.unrecorded: dict[str, BaseException] = {}
        self.errors: dict[str, dict] = {}

    def mark_failed(self, call_id, message):
        """Record that a released call's tool failed while it ran.

        Later before() and record() histories send that call's result with
        ``error`` ``{"type": "unknown", "message": message}``, so Watcher does
        not record it as completed. Only for execution failures, such as a tool
        exception your own code catches: report a refusal or cancellation with
        report_status, which keeps the result free of ``error``. Marking a call
        again replaces its error.
        """
        self.errors[call_id] = {"type": "unknown", "message": message}

    async def before(self, messages, call_id, name, arguments):
        """Validate native pending history, then wait before the caller executes.

        Supply the pending call's original ID, name and JSON arguments. Framework
        schema validation and coercion still determine the tool body's values.
        Completed calls, identity mismatches and repeated attempts fail closed.
        The monitor sees the historical prefix ending at the pending assistant
        message, including sibling calls but no later results or final answer.
        """
        transcript = messages_for_watcher(messages)
        await self.before_transcript(transcript, call_id, name, arguments)

    async def before_transcript(self, transcript, call_id, name, arguments):
        """Gate an already normalized Inspect history at an application-owned boundary.

        Prefer before() when native message objects are available. No side effect
        belongs before this await, and no exception from it is an authorization.
        Results of calls reported through mark_failed are sent with their
        ``error``. A cancellation once the call is submitted withholds it and is
        reported as cancelled (see report_status) before it propagates; a
        reporting failure becomes its cause. A call withheld before Watcher
        answered, by a cancellation or by a failure such as a timeout, is
        reported after the next record().
        """
        transcript = mark_tool_errors(deepcopy(transcript), self.errors)
        matches = [
            (index, call)
            for index, message in enumerate(transcript)
            if message["role"] == "assistant"
            for call in message.get("tool_calls", [])
            if call["id"] == call_id
        ]
        if not call_id or len(matches) != 1 or call_id in self.attempted:
            raise ToolBlocked("A unique, unattempted pending tool ID is required")
        index, call = matches[0]
        if call["function"] != name or not same_json_arguments(call["arguments"], arguments):
            raise ToolBlocked("Execution does not match the pending transcript call")
        if any(message.get("tool_call_id") == call_id for message in transcript if message["role"] == "tool"):
            raise ToolBlocked("Completed tools cannot be authorized retroactively")
        self.attempted.add(call_id)
        try:
            await self._decide(transcript[: index + 1], call_id, name, arguments)
        except asyncio.CancelledError as cancelled:
            await self._report_then_raise(cancelled, call_id, name, arguments, "cancelled")
        except Exception:
            # Every refusal raises; one whose status is not recorded yet, such
            # as a call withheld after a monitoring failure, is queued.
            self._withhold(call_id, name, arguments, "blocked")
            raise
        self.released.add(call_id)

    def _withhold(self, call_id, name, arguments, status):
        """Queue a withheld call's status for record(), unless it is reported or being reported."""
        if call_id not in self.reported:
            self.unrecorded.pop(call_id, None)
            self.unreported.setdefault(call_id, (name, deepcopy(arguments), status))

    async def _report_then_raise(self, error, call_id, name, arguments, status) -> NoReturn:
        """Report status for a call that error withholds, then raise error.

        A call Watcher has not evaluated, or whose report fails, is queued for
        record() instead. A reporting failure becomes error's cause; the call
        stays withheld either way.
        """
        try:
            if not await self.report_status(call_id, name, arguments, status):
                self._withhold(call_id, name, arguments, status)
        except Exception as failure:
            raise error from failure
        raise error

    async def _decide(self, prefix, call_id, name, arguments):
        """Submit one pending call with its history prefix and apply Watcher's decision.

        Returns only when the call may run; every refusal raises.
        """
        submitted: dict = {"tool_name": name, "tool_input": deepcopy(arguments), "tool_use_id": call_id}
        if self.prior_decisions:
            submitted["prior_decisions"] = deepcopy(self.prior_decisions[-20:])
        outcome = await self.client.pre_tool_use_hook(
            submitted,
            messages=prefix,
            external_ids=self.external_ids,
            settings_overrides=self.settings,
            mode="full",
            timeout=self.timeout,
        )
        serialize = getattr(outcome, "to_dict", None)
        if isinstance(outcome, list) or not callable(serialize):
            raise ToolBlocked("Watcher returned an unexpected tool outcome")
        result = serialize()
        if result.get("tool_use_id") != call_id:
            raise ToolBlocked("Watcher returned another call's decision")
        decision = result.get("decision")
        enforcement = result.get("enforcement_mode")
        source = result.get("decision_source")
        failure = result.get("grading_error")
        if source == "grading_error":
            if (
                not isinstance(failure, dict)
                or failure.get("code")
                not in {"timeout", "at_capacity", "allowance_exhausted", "grader_failed", "no_result"}
                or not isinstance(failure.get("message"), str)
            ):
                raise ToolBlocked("Watcher returned an invalid grading-failure result")
        elif failure is not None:
            raise ToolBlocked("Watcher returned inconsistent grading provenance")
        if decision == "deferred":
            if enforcement == "paused" and source == "bypass" and result.get("judged_decision") is None:
                return
            if (
                enforcement == "observe"
                and source in {"threshold", "rule", "triage", "policy_gateway", "grading_error"}
                and result.get("judged_decision") in {"allow", "deny", "escalate"}
            ):
                self.evaluated.add(call_id)
                return
            raise ToolBlocked("Watcher returned an inconsistent deferred decision")
        if enforcement != "enforce" or decision not in {"allow", "deny", "escalate"}:
            raise ToolBlocked("Watcher returned an inconsistent applied decision")
        if result.get("decision_source") not in {"threshold", "rule", "triage", "policy_gateway", "grading_error"}:
            raise ToolBlocked("Watcher returned an invalid enforcement source")
        if result.get("judged_decision") != decision:
            raise ToolBlocked("Watcher returned an incomplete enforcement decision")
        self.evaluated.add(call_id)
        if decision == "allow":
            return
        if decision == "deny":
            await self._report_then_raise(
                ToolBlocked("Watcher denied this tool call"), call_id, name, arguments, "blocked"
            )
        if self.approval_callback is None:
            await self._report_then_raise(
                ApprovalRequired("Watcher requires human approval; the tool was not executed"),
                call_id,
                name,
                arguments,
                "blocked",
            )
        approved = await self.approval_callback(
            tool_use_id=call_id,
            tool_name=name,
            tool_input=deepcopy(arguments),
            outcome=outcome,
        )
        if type(approved) is not bool:
            raise ToolBlocked("The approval callback did not return an explicit human choice")
        choice = "allow" if approved else "deny"
        self.prior_decisions.append({"tool_name": name, "tool_input": deepcopy(arguments), "response": choice})
        await self.report_human_decision(call_id, name, arguments, approved=approved)
        if not approved:
            raise ToolBlocked("The pending tool call was not approved")

    async def report_human_decision(self, call_id, name, arguments, *, approved: bool):
        """Record the explicit human choice without overwriting Watcher's evaluation.

        Hook recording is asynchronous. Wait up to human_audit_timeout for one
        canonical conversation and the initial call audit, then use the SDK's
        batch-upload receipt and read back the stored human choice and execution
        status from extended trajectory detail, preserving the original evaluation.
        Readback matters because a content scrub can make an upload a successful
        no-op. This requires session-read permission and
        authority to update that session (its owner, or sessions:write:any).

        An approved call remains pending here: approval is not proof of execution.
        A human rejection marks it blocked. Any lookup, ambiguity, timeout or
        upload failure propagates before the native tool body can run. The caller
        should retain its human choice if reporting fails; this example has no
        persistent approval queue and does not retry tool execution.

        A rejection reported again after its upload failed records the person's
        choice even once Watcher has moved the call on from pending, provided
        this Monitor never released the call and no human decision is recorded
        for it. It then replaces a completed or unknown status, which Watcher
        settles from the refusal text the agent saw, or adds the choice to a
        blocked status reported without one. The call leaves the queue that
        record() reports and ``unrecorded``.

        Once a human choice is supplied, cancellation waits for this bounded
        reporting attempt to finish. After successful recording, cancellation
        propagates without releasing the tool. An audit failure takes priority over
        cancellation so the caller can retain the unconfirmed choice. Waiting for
        human input is outside this method and remains cancellable.
        """
        if type(approved) is not bool:
            raise ValueError("An explicit human choice is required")
        await self._shielded(self._report_human_decision(call_id, name, arguments, approved=approved))

    async def report_status(self, call_id, name, arguments, status: Literal["blocked", "cancelled"]) -> bool:
        """Record that a call Watcher evaluated was refused or cancelled, so it never reads as completed.

        The Monitor reports its own refusals and cancellations. Call this for one
        your application makes after Watcher let a call through: ``blocked`` when
        your own check refuses it, ``cancelled`` when you stop it, including
        while its tool runs. Pass the call's original ID, name and JSON
        arguments. The result text the agent saw stays as it is, without
        ``error``.

        Returns False without uploading anything for a call this Monitor never
        received a Watcher evaluation of: a request that failed or was cancelled
        before Watcher answered, a paused-mode bypass, or a call it did not
        submit. The Monitor itself reports calls it withheld before Watcher
        answered, after the next record(). It also returns False for a call
        whose status it already reported or is reporting, including a person's
        rejection: the first report stands.

        Otherwise this uses the same upload and readback as
        report_human_decision and returns True: wait up to human_audit_timeout
        for Watcher's recorded evaluation of the call, upload the status without
        changing that evaluation, then read it back. A call already blocked or
        cancelled is not overwritten: the attempt raises ToolBlocked. A
        completed or unknown status, which Watcher settles from the result text
        the agent saw, is replaced. An evaluation that is never recorded (an
        ephemeral request, a key without ingest permission) times out. Any
        lookup, upload or readback failure raises, and later record() calls
        report the status (see record()). Cancellation waits for this bounded
        attempt.
        """
        if status not in {"blocked", "cancelled"}:
            raise ValueError("Report a refusal as blocked or a cancellation as cancelled")
        if call_id not in self.evaluated or call_id in self.reported:
            return False
        self.reported.add(call_id)
        await self._shielded(self._report_outcome(call_id, name, arguments, status))
        return True

    async def _report_outcome(self, call_id, name, arguments, status):
        """Upload one status; a failed upload releases the call's claim and queues it for record().

        Runs inside _shielded, so the claim follows the upload's real outcome
        even when report_status's caller is cancelled meanwhile.
        """
        try:
            await self._upload_outcome(outcome_payload(call_id, name, arguments, status), arguments, applied=None)
        except BaseException:
            self.reported.discard(call_id)
            self._withhold(call_id, name, arguments, status)
            raise
        self.unreported.pop(call_id, None)
        self.late_attempts.pop(call_id, None)
        self.unrecorded.pop(call_id, None)

    async def _shielded(self, report):
        """Await a reporting coroutine to completion even if this task is cancelled meanwhile.

        A reporting failure takes priority; otherwise a cancellation received
        while waiting propagates once the report has finished.
        """
        task = asyncio.create_task(report)
        cancelled = None
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError as error:
                cancelled = error
        if cancelled is not None:
            raise cancelled from task.exception()
        task.result()

    async def _report_human_decision(self, call_id, name, arguments, *, approved: bool):
        """Complete one audit within its deadline even when a sibling tool aborts."""
        payload = outcome_payload(call_id, name, arguments, "pending" if approved else "blocked")
        payload["human_decision"] = "allow" if approved else "deny"
        payload["human_decided_at"] = datetime.now(UTC).isoformat()
        never_released = not approved and call_id in self.attempted and call_id not in self.released
        await self._upload_outcome(payload, arguments, applied="escalate", never_released=never_released)
        if not approved:
            # The rejection recorded the call as blocked, which settles a status
            # still queued or given up on. An approval leaves those as they are.
            self.reported.add(call_id)
            self.unreported.pop(call_id, None)
            self.late_attempts.pop(call_id, None)
            self.unrecorded.pop(call_id, None)

    async def _session(self):
        """Return this conversation's session ID and latest trajectory ID, or None until both are stored."""
        sessions = await self.client.search_sessions(
            external_ids={key: [value] for key, value in self.external_ids.items()}, limit=2
        )
        if sessions.total > 1 or len(sessions.sessions) > 1:
            raise ToolBlocked("The conversation matched multiple Watcher sessions")
        if sessions.total != 1 or len(sessions.sessions) != 1:
            return None
        session = sessions.sessions[0].to_dict()
        trajectory_id = session.get("latest_trajectory_id")
        if not isinstance(trajectory_id, str) or not trajectory_id:
            return None
        return session["session_id"], trajectory_id

    async def _upload_outcome(self, payload, arguments, *, applied, never_released=False):
        """Merge an outcome-only payload into Watcher's recorded evaluation of its call, then read it back.

        Wait up to human_audit_timeout for one canonical conversation and the
        call's recorded evaluation: applied decision ``applied``, or any Watcher
        evaluation when ``applied`` is None. A human decision needs the stored
        call still pending. A status report needs it not yet blocked or
        cancelled, and replaces a completed or unknown status, which Watcher
        settles from the result text the agent saw. A rejection of a call this
        Monitor never released (``never_released``) may also replace a
        completed or unknown status, or join a blocked one, while no human
        decision is recorded for the call. After upload, the stored
        outcome must equal the payload's and every other field must be
        unchanged, including the human fields when the payload reports only a
        status.
        """
        call_id, name = payload["tool_use_id"], payload["tool_name"]
        human = "human_decision" in payload
        outcome = "human decision" if human else "reported status"
        pause = FIRST_POLL_INTERVAL
        async with asyncio.timeout(self.human_audit_timeout):
            while True:
                stored_session = await self._session()
                if stored_session is not None:
                    session_id, trajectory_id = stored_session
                    offset = 0
                    while True:
                        calls = await self.client.search_tool_calls(
                            session_id=session_id,
                            tool_names=[name],
                            limit=100,
                            offset=offset,
                            sort_by="occurred_at",
                            sort_order="desc",
                        )
                        matching = [
                            item.to_dict() for item in calls.tool_calls if item.to_dict().get("tool_use_id") == call_id
                        ]
                        if len(matching) > 1:
                            raise ToolBlocked("The pending tool identity matched multiple recorded calls")
                        if matching:
                            if matching[0].get("tool_name") != name or (
                                applied is not None and matching[0].get("applied_decision") != applied
                            ):
                                raise ToolBlocked("The stored call does not match the reported call")
                            original = await self._stored_decision(
                                session_id, trajectory_id, call_id, name, arguments, applied
                            )
                            current = original.get("tool_status")
                            # Only refusal text can have settled a call that never ran.
                            refused = (
                                never_released
                                and original.get("human_decision") is None
                                and current in {"blocked", "completed", "unknown"}
                            )
                            if current in {"blocked", "cancelled"} and not refused:
                                raise ToolBlocked("The stored tool was already reported blocked or cancelled")
                            if human and current != "pending" and not refused:
                                raise ToolBlocked("The stored tool is no longer pending execution")
                            receipt = await self.client.upload_tool_call_decisions_batch(
                                session_id=session_id, decisions=[payload]
                            )
                            stored = receipt.to_dict()
                            if (
                                stored.get("synced_tool_use_ids") != [call_id]
                                or stored.get("synced_count") != 1
                                or stored.get("failed_tool_use_ids")
                                or stored.get("failed_tool_call_grade_ids")
                            ):
                                raise ToolBlocked(f"Watcher did not acknowledge the {outcome}")
                            confirmed = await self._stored_decision(
                                session_id, trajectory_id, call_id, name, arguments, applied
                            )
                            mutable = {"tool_status", "updated_at"}
                            if human:
                                mutable |= {"human_decision", "human_decided_at"}
                            previous_evaluation = {key: value for key, value in original.items() if key not in mutable}
                            current_evaluation = {key: value for key, value in confirmed.items() if key not in mutable}
                            if (
                                confirmed.get("tool_status") != payload["tool_status"]
                                or (
                                    human
                                    and (
                                        confirmed.get("human_decision") != payload["human_decision"]
                                        or not isinstance(confirmed.get("human_decided_at"), str)
                                        or datetime.fromisoformat(confirmed["human_decided_at"])
                                        != datetime.fromisoformat(payload["human_decided_at"])
                                    )
                                )
                                or json.dumps(previous_evaluation, sort_keys=True, allow_nan=False)
                                != json.dumps(current_evaluation, sort_keys=True, allow_nan=False)
                            ):
                                raise ToolBlocked(
                                    f"Watcher did not expose the recorded {outcome} with its original evaluation"
                                )
                            return
                        offset += len(calls.tool_calls)
                        if not calls.tool_calls or offset >= calls.total:
                            break
                await asyncio.sleep(pause)
                pause = min(pause * 2, MAX_POLL_INTERVAL)

    async def _stored_decision(self, session_id, trajectory_id, call_id, name, arguments, applied):
        """Read one exact pending function and its evaluation from public storage.

        The evaluation must have applied decision ``applied``, or, when that is
        None, come from Watcher's own evaluation (EVALUATED_SOURCES).
        Extended trajectory content preserves JSON argument types. Display-list
        categories are not approval evidence: routine escalations may have none.
        Missing, scrubbed, duplicated or mismatching content withholds execution.
        """
        response = await self.client.get_trajectory(session_id, trajectory_id, view=TrajectoryView.EXTENDED)
        stored = response.to_dict()
        matching = [
            call
            for message in stored.get("messages", [])
            for call in message.get("tool_calls") or []
            if call.get("id") == call_id
        ]
        decision = stored.get("tool_call_decisions", {}).get(call_id)
        if (
            stored.get("session_id") != session_id
            or stored.get("trajectory_id") != trajectory_id
            or len(matching) != 1
            or matching[0].get("type") != "function"
            or matching[0].get("function") != name
            or json.dumps(matching[0].get("arguments"), sort_keys=True, allow_nan=False)
            != json.dumps(arguments, sort_keys=True, allow_nan=False)
            or not isinstance(decision, dict)
            or decision.get("tool_use_id") != call_id
            or decision.get("tool_name") != name
            or (
                decision.get("applied_decision") != applied
                if applied is not None
                else decision.get("decision_source") not in EVALUATED_SOURCES
            )
            or not isinstance(decision.get("raw_tool_call"), dict)
            or decision["raw_tool_call"].get("tool_name") != name
            or json.dumps(decision["raw_tool_call"].get("tool_input"), sort_keys=True, allow_nan=False)
            != json.dumps(arguments, sort_keys=True, allow_nan=False)
        ):
            raise ToolBlocked("The stored trajectory does not match the reported call")
        return decision

    async def record(self, messages):
        """Submit results and final answer without executing or regrading tools, then report withheld calls.

        Results of calls reported through mark_failed are sent with their
        ``error``. An empty response confirms request acceptance, not durable
        storage. Query Watcher when the application needs persistence
        confirmation.

        Then each call this Monitor withheld without recording its status is
        reported: one withheld after a monitoring failure is ``blocked``, one
        cancelled before Watcher answered is ``cancelled``, and one whose
        report failed keeps the status that report carried. If any of those
        reports fails, this raises StatusNotRecorded although the transcript
        was accepted. A report that failed in a way a retry may fix (Watcher
        had not stored the call before human_audit_timeout, a transport
        failure, rate limiting or a server error) is retried by later record()
        calls, up to late_report_attempts in all. After a permanent failure,
        such as a refused permission, or the last attempt, the Monitor stops
        reporting the call and lists it in ``unrecorded``; the application
        decides what to do with those. Their status is unconfirmed: an upload
        stored before its readback failed may have recorded it.

        Cancelling record() stops these reports at once. A call whose report it
        stops stays queued without using an attempt, and its status is
        unconfirmed: an upload may have been stored before the cancellation. A
        later report that finds the status stored does not upload it again. A
        report that failed before the cancellation counts as usual, so check
        ``unrecorded`` after a cancellation too.
        """
        receipt = await self.client.pre_tool_use_hook(
            None,
            messages=messages_for_watcher(messages, self.errors),
            external_ids=self.external_ids,
            timeout=self.timeout,
        )
        if receipt != []:
            raise ToolBlocked("Final transcript recording returned unexpected outcomes")
        if self.unreported:
            await self._report_withheld()

    async def _report_withheld(self):
        """Report every queued call not being reported elsewhere, concurrently.

        Raises StatusNotRecorded once every report has finished, if any failed.
        A cancellation cancels the reports and waits for all of them to stop,
        through any further cancellation, then propagates; the task's
        cancellation count is left as it is, so an enclosing asyncio.timeout
        still reports its own expiry. Either way, every claimed call's queue
        entry, claim and attempts are updated from its report's outcome before
        this returns or raises, including a report cancelled before it started.
        """
        queued = {call_id: item for call_id, item in self.unreported.items() if call_id not in self.reported}
        if not queued:
            return
        self.reported.update(queued)
        reports = {call_id: asyncio.create_task(self._report_late(call_id, *item)) for call_id, item in queued.items()}
        try:
            await asyncio.wait(reports.values())
        except asyncio.CancelledError:
            for report in reports.values():
                report.cancel()
            # A report's cleanup can await, for example to close its connection;
            # its call stays claimed until it has stopped.
            while not all(report.done() for report in reports.values()):
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.wait(reports.values())
            for call_id, report in reports.items():
                self._settle_report(call_id, report)
            raise
        failures = {
            call_id: failure
            for call_id, report in reports.items()
            if (failure := self._settle_report(call_id, report)) is not None
        }
        if failures:
            raise StatusNotRecorded(failures, set(failures) & set(self.unreported)) from next(iter(failures.values()))

    def _settle_report(self, call_id, report):
        """Update a claimed call's queue entry, claim and attempts from its stopped late report; return its failure.

        A confirmed status takes the call off the queue and keeps its claim. A
        failed call stays queued while retryable() holds and it has attempts
        left, and otherwise moves to ``unrecorded``. A cancelled report leaves
        the call queued with its attempts unchanged. Unless the status is
        confirmed, the claim is released so a later report can retry the call.
        A person's rejection recorded while the report ran has already settled
        the call: it then keeps its claim, and nothing is returned.
        """
        failure = None if report.cancelled() else report.exception()
        if not report.cancelled() and failure is None:
            self.unreported.pop(call_id, None)
            self.late_attempts.pop(call_id, None)
            return None
        if call_id not in self.unreported:
            return None
        self.reported.discard(call_id)
        if failure is None:
            return None
        attempts = self.late_attempts.get(call_id, 0) + 1
        if retryable(failure) and attempts < self.late_report_attempts:
            self.late_attempts[call_id] = attempts
        else:
            self.unreported.pop(call_id, None)
            self.late_attempts.pop(call_id, None)
            self.unrecorded[call_id] = failure
        return failure

    async def _report_late(self, call_id, name, arguments, status):
        """Record a withheld call's status once Watcher stores the call, then read it back.

        Watcher may hold no evaluation of the call yet, or ever: the status-only
        upload then creates the call's decision record, and an evaluation
        recorded later keeps its status. Watcher stores the call from a
        transcript containing it and refuses an upload until then, so this
        waits up to human_audit_timeout, pausing longer between lookups as it
        waits. A call already blocked or cancelled is left as it is. A pending,
        completed or unknown status, which Watcher can derive from the result
        the agent saw for the withheld call, is replaced.
        """
        payload = outcome_payload(call_id, name, arguments, status)
        pause = FIRST_POLL_INTERVAL
        async with asyncio.timeout(self.human_audit_timeout):
            while True:
                stored = await self._stored_call(call_id, name, arguments)
                if stored is not None:
                    session_id, decision = stored
                    if decision is not None and decision.get("tool_status") in {"blocked", "cancelled"}:
                        return
                    receipt = await self.client.upload_tool_call_decisions_batch(
                        session_id=session_id, decisions=[payload]
                    )
                    synced = receipt.to_dict()
                    if (
                        synced.get("synced_tool_use_ids") == [call_id]
                        and synced.get("synced_count") == 1
                        and not synced.get("failed_tool_use_ids")
                        and not synced.get("failed_tool_call_grade_ids")
                    ):
                        confirmed = await self._stored_call(call_id, name, arguments)
                        if confirmed is None or (confirmed[1] or {}).get("tool_status") != status:
                            raise ToolBlocked("Watcher did not expose the reported status")
                        return
                    # An upload racing Watcher's storage of the call fails and is retried.
                    if synced.get("synced_count") or synced.get("failed_tool_use_ids") != [call_id]:
                        raise ToolBlocked("Watcher did not acknowledge the reported status")
                await asyncio.sleep(pause)
                pause = min(pause * 2, MAX_POLL_INTERVAL)

    async def _stored_call(self, call_id, name, arguments):
        """Find a withheld call on any branch of the conversation Watcher stored.

        Like the decision upload, this looks across every trajectory of the
        session, not only the latest. Returns None until Watcher stores the
        call, otherwise the session ID and the call's decision record, or None
        in place of the record while there is none. Raises when Watcher does
        not show the call's arguments and decision to this API key, or when the
        stored call has another function or arguments.
        """
        stored_session = await self._session()
        if stored_session is None:
            return None
        session_id = stored_session[0]
        try:
            response = await self.client.get_session_tool_call(session_id, call_id)
        except WatcherNotFoundError:
            return None
        stored = response.to_dict()
        if not stored.get("can_read_content") or not stored.get("can_read_findings"):
            raise ToolBlocked("Watcher did not show the stored call's arguments and decision")
        decision = stored.get("decision")
        if (
            stored.get("tool_use_id") != call_id
            or stored.get("tool_name") != name
            or not same_json_arguments(stored.get("arguments"), arguments)
            or (decision is not None and (decision.get("tool_use_id") != call_id or decision.get("tool_name") != name))
        ):
            raise ToolBlocked("The stored call does not match the withheld call")
        return session_id, decision
