"""Apply Watcher decisions at the framework's native before-tool boundary.

One Monitor follows the server's enforce, observe or paused setting. Human
approvals can be supplied through an awaited application callback; without one,
escalations block. Transcript submission does not acknowledge durable storage.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Literal

from watcher_camel.adapter import messages_for_watcher
from watcher_sdk import AsyncWatcherClient, TrajectoryView


def same_json_arguments(left, right):
    """Compare JSON values without Python's bool/number equality coercion.

    Object-key order is immaterial; array order and JSON literal types must match.
    Non-JSON values and non-finite numbers fail before execution is authorized.
    """
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


class ToolBlocked(RuntimeError):
    """Watcher denied a call or the integration could not safely interpret its result."""


class ApprovalRequired(ToolBlocked):
    """A human must approve this pending call; unattended callers must not execute it."""


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
    ):
        if not conversation_id or timeout <= 0:
            raise ValueError("A conversation ID and positive grading timeout are required")
        self.client = client
        self.external_ids = {"other": f"camel:{conversation_id}"}
        self.timeout = timeout
        if enforcement not in {"server", "enforce", "observe", "paused"}:
            raise ValueError("Unsupported enforcement setting")
        self.settings = None if enforcement == "server" else {"enforcement": {"mode": enforcement}}
        if human_audit_timeout <= 0:
            raise ValueError("A positive human decision recording deadline is required")
        self.approval_callback = approval_callback
        self.human_audit_timeout = human_audit_timeout
        self.prior_decisions: list[dict] = []
        self.attempted = set()

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
        """
        transcript = deepcopy(transcript)
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
        submitted: dict = {"tool_name": name, "tool_input": deepcopy(arguments), "tool_use_id": call_id}
        if self.prior_decisions:
            submitted["prior_decisions"] = deepcopy(self.prior_decisions[-20:])
        outcome = await self.client.pre_tool_use_hook(
            submitted,
            messages=transcript[: index + 1],
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
                return
            raise ToolBlocked("Watcher returned an inconsistent deferred decision")
        if enforcement != "enforce" or decision not in {"allow", "deny", "escalate"}:
            raise ToolBlocked("Watcher returned an inconsistent applied decision")
        if result.get("decision_source") not in {"threshold", "rule", "triage", "policy_gateway", "grading_error"}:
            raise ToolBlocked("Watcher returned an invalid enforcement source")
        if result.get("judged_decision") != decision:
            raise ToolBlocked("Watcher returned an incomplete enforcement decision")
        if decision == "allow":
            return
        if decision == "deny":
            raise ToolBlocked("Watcher denied this tool call")
        if self.approval_callback is None:
            raise ApprovalRequired("Watcher requires human approval; the tool was not executed")
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

        Once a human choice is supplied, cancellation waits for this bounded
        reporting attempt to finish. After successful recording, cancellation
        propagates without releasing the tool. An audit failure takes priority over
        cancellation so the caller can retain the unconfirmed choice. Waiting for
        human input is outside this method and remains cancellable.
        """
        if type(approved) is not bool:
            raise ValueError("An explicit human choice is required")
        report = asyncio.create_task(self._report_human_decision(call_id, name, arguments, approved=approved))
        cancelled = None
        while not report.done():
            try:
                await asyncio.shield(report)
            except asyncio.CancelledError as error:
                cancelled = error
        if cancelled is not None:
            raise cancelled from report.exception()
        report.result()

    async def _report_human_decision(self, call_id, name, arguments, *, approved: bool):
        """Complete one audit within its deadline even when a sibling tool aborts."""
        payload = {
            "tool_use_id": call_id,
            "tool_name": name,
            "raw_tool_call": {"tool_name": name, "tool_input": deepcopy(arguments)},
            "policy_decision": "not_evaluated",
            "applied_decision": "not_evaluated",
            "decision_source": "not_evaluated",
            "tool_status": "pending" if approved else "blocked",
            "human_decision": "allow" if approved else "deny",
            "human_decided_at": datetime.now(UTC).isoformat(),
        }
        async with asyncio.timeout(self.human_audit_timeout):
            while True:
                sessions = await self.client.search_sessions(
                    external_ids={key: [value] for key, value in self.external_ids.items()}, limit=2
                )
                if sessions.total > 1 or len(sessions.sessions) > 1:
                    raise ToolBlocked("The conversation matched multiple Watcher sessions")
                if sessions.total == 1 and len(sessions.sessions) == 1:
                    session = sessions.sessions[0].to_dict()
                    session_id = session["session_id"]
                    trajectory_id = session.get("latest_trajectory_id")
                    if not isinstance(trajectory_id, str) or not trajectory_id:
                        await asyncio.sleep(0.1)
                        continue
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
                            if (
                                matching[0].get("tool_name") != name
                                or matching[0].get("applied_decision") != "escalate"
                            ):
                                raise ToolBlocked("The stored call does not match the pending escalation")
                            original = await self._stored_escalation(
                                session_id, trajectory_id, call_id, name, arguments
                            )
                            if original.get("tool_status") != "pending":
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
                                raise ToolBlocked("Watcher did not acknowledge the human decision")
                            confirmed = await self._stored_escalation(
                                session_id, trajectory_id, call_id, name, arguments
                            )
                            mutable = {"human_decision", "human_decided_at", "tool_status", "updated_at"}
                            previous_evaluation = {key: value for key, value in original.items() if key not in mutable}
                            current_evaluation = {key: value for key, value in confirmed.items() if key not in mutable}
                            if (
                                confirmed.get("human_decision") != payload["human_decision"]
                                or confirmed.get("tool_status") != payload["tool_status"]
                                or not isinstance(confirmed.get("human_decided_at"), str)
                                or datetime.fromisoformat(confirmed["human_decided_at"])
                                != datetime.fromisoformat(payload["human_decided_at"])
                                or json.dumps(previous_evaluation, sort_keys=True, allow_nan=False)
                                != json.dumps(current_evaluation, sort_keys=True, allow_nan=False)
                            ):
                                raise ToolBlocked(
                                    "Watcher did not expose the recorded human decision with its original evaluation"
                                )
                            return
                        offset += len(calls.tool_calls)
                        if not calls.tool_calls or offset >= calls.total:
                            break
                await asyncio.sleep(0.1)

    async def _stored_escalation(self, session_id, trajectory_id, call_id, name, arguments):
        """Read one exact pending function and its evaluation from public storage.

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
            or decision.get("applied_decision") != "escalate"
            or not isinstance(decision.get("raw_tool_call"), dict)
            or decision["raw_tool_call"].get("tool_name") != name
            or json.dumps(decision["raw_tool_call"].get("tool_input"), sort_keys=True, allow_nan=False)
            != json.dumps(arguments, sort_keys=True, allow_nan=False)
        ):
            raise ToolBlocked("The stored trajectory does not match the pending escalation")
        return decision

    async def record(self, messages):
        """Submit results and final answer without executing or regrading tools.

        An empty response confirms request acceptance, not durable storage.
        Query Watcher when the application needs persistence confirmation.
        """
        receipt = await self.client.pre_tool_use_hook(
            None,
            messages=messages_for_watcher(messages),
            external_ids=self.external_ids,
            timeout=self.timeout,
        )
        if receipt != []:
            raise ToolBlocked("Final transcript recording returned unexpected outcomes")
