"""Apply Watcher policy before Mastra's native output processor releases tools.

The Node integration submits complete Inspect messages to this public SDK bridge.
The server's configured mode controls observation or enforcement. Optional human
choices are recorded and verified before approval can release execution.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Literal

from watcher_sdk import AsyncWatcherClient, TrajectoryView


class Withheld(RuntimeError):
    """Watcher denied execution or the result could not be safely applied."""


class ApprovalRequired(Withheld):
    """Human approval is required before the pending native call can proceed."""


def _json_identity(value: object) -> str:
    """Encode only JSON values, distinguishing booleans, integers and floats.

    Native arguments must retain their JSON types between recording and execution.
    Object key order is irrelevant; Python-only containers, keys and nonfinite
    numbers are rejected rather than silently coerced by json.dumps.
    """
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise Withheld("Tool arguments require string object keys")
        return "{" + ",".join(json.dumps(key) + ":" + _json_identity(value[key]) for key in sorted(value)) + "}"
    if type(value) is list:
        return "[" + ",".join(_json_identity(item) for item in value) + "]"
    if value is None or type(value) in (str, bool, int, float):
        return json.dumps(value, allow_nan=False, ensure_ascii=False)
    raise Withheld("Tool arguments must contain only JSON values")


class Monitor:
    """Grade full pending history and execute only explicitly allowed callbacks.

    Server policy is inherited by default. Explicit overrides may be admin-locked.
    Observe and paused decisions preserve ordinary application permissions.
    Escalations await an optional application human-approval callback; without one
    they block. Human choices are uploaded and read back before execution. This
    requires session-read and owner/write-any access; reporting failures block.
    Full grading uses the SDK's 420-second default budget, configurable per instance.
    Instances serialize approvals and reject ID reuse, including after failed grades.
    They do not provide durable exactly-once execution across application restarts.
    """

    def __init__(
        self,
        watcher: AsyncWatcherClient,
        session_id: str,
        *,
        timeout: float = 420,
        enforcement: Literal["server", "enforce", "observe", "paused"] = "server",
        approval_callback: Callable[..., Awaitable[bool]] | None = None,
        human_audit_timeout: float = 10,
    ):
        if not session_id or timeout <= 0:
            raise ValueError("A conversation ID and positive timeout are required")
        self.watcher = watcher
        self.session_id = session_id
        self.timeout = timeout
        if enforcement not in {"server", "enforce", "observe", "paused"}:
            raise ValueError("Unsupported enforcement setting")
        self.settings = None if enforcement == "server" else {"enforcement": {"mode": enforcement}}
        if human_audit_timeout <= 0:
            raise ValueError("A positive human decision recording deadline is required")
        self.approval_callback = approval_callback
        self.human_audit_timeout = human_audit_timeout
        self.external_ids = {"other": session_id}
        self.prior_decisions: list[dict] = []
        self.attempted: set[str] = set()
        self.lock = asyncio.Lock()

    async def authorize(self, messages: list[dict], inputs: list[dict]) -> None:
        """Apply matching decisions to every supplied pending identity before dispatch.

        This is useful at a native callback boundary. The caller must execute only
        these exact inputs after return; dispatch() performs that coupling for Python.
        No result for a pending call may already occur in the supplied history.
        """
        messages, inputs = deepcopy(messages), deepcopy(inputs)
        async with self.lock:
            pending = {}
            seen = set()
            for message in messages:
                for call in message.get("tool_calls", []):
                    if message["role"] != "assistant" or not call["id"] or call["id"] in seen:
                        raise Withheld("Missing or duplicate transcript identity")
                    seen.add(call["id"])
                    pending[call["id"]] = {
                        "tool_use_id": call["id"],
                        "tool_name": call["function"],
                        "tool_input": call["arguments"],
                    }
                if message["role"] == "tool":
                    if message["tool_call_id"] not in pending:
                        raise Withheld("Unmatched transcript result")
                    del pending[message["tool_call_id"]]
            ids = [item["tool_use_id"] for item in inputs]
            if len(set(ids)) != len(ids) or any(key in self.attempted for key in ids):
                raise Withheld("Repeated execution identity")
            if not inputs or any(
                _json_identity(pending.get(item["tool_use_id"])) != _json_identity(item) for item in inputs
            ):
                raise Withheld("Pending transcript identity does not match execution")
            self.attempted.update(ids)
            for start in range(0, len(inputs), 32):
                batch = inputs[start : start + 32]
                outcomes = await self.watcher.pre_tool_use_hook(
                    [
                        dict(item, prior_decisions=deepcopy(self.prior_decisions[-20:]))
                        if self.prior_decisions
                        else item
                        for item in batch
                    ],
                    messages=messages,
                    external_ids={"other": self.session_id},
                    mode="full",
                    timeout=self.timeout,
                    settings_overrides=self.settings,
                )
                if not isinstance(outcomes, list) or len(outcomes) != len(batch):
                    raise Withheld("Incomplete enforcement response")
                for item, outcome in zip(batch, outcomes, strict=True):
                    await self.apply(item, outcome)

    async def apply(self, item, outcome):
        """Apply one matching server decision before a tool batch is released."""
        call_id, name, arguments = item["tool_use_id"], item["tool_name"], item["tool_input"]
        serialize = getattr(outcome, "to_dict", None)
        if isinstance(outcome, list) or not callable(serialize):
            raise Withheld("Watcher returned an unexpected tool outcome")
        result = serialize()
        if result.get("tool_use_id") != call_id:
            raise Withheld("Watcher returned another call's decision")
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
                raise Withheld("Watcher returned an invalid grading-failure result")
        elif failure is not None:
            raise Withheld("Watcher returned inconsistent grading provenance")
        if decision == "deferred":
            if enforcement == "paused" and source == "bypass" and result.get("judged_decision") is None:
                return
            if (
                enforcement == "observe"
                and source in {"threshold", "rule", "triage", "policy_gateway", "grading_error"}
                and result.get("judged_decision") in {"allow", "deny", "escalate"}
            ):
                return
            raise Withheld("Watcher returned an inconsistent deferred decision")
        if enforcement != "enforce" or decision not in {"allow", "deny", "escalate"}:
            raise Withheld("Watcher returned an inconsistent applied decision")
        if result.get("decision_source") not in {"threshold", "rule", "triage", "policy_gateway", "grading_error"}:
            raise Withheld("Watcher returned an invalid enforcement source")
        if result.get("judged_decision") != decision:
            raise Withheld("Watcher returned an incomplete enforcement decision")
        if decision == "allow":
            return
        if decision == "deny":
            raise Withheld("Watcher denied this tool call")
        if self.approval_callback is None:
            raise ApprovalRequired("Watcher requires human approval; the tool was not executed")
        approved = await self.approval_callback(
            tool_use_id=call_id,
            tool_name=name,
            tool_input=deepcopy(arguments),
            outcome=outcome,
        )
        if type(approved) is not bool:
            raise Withheld("The approval callback did not return an explicit human choice")
        choice = "allow" if approved else "deny"
        self.prior_decisions.append({"tool_name": name, "tool_input": deepcopy(arguments), "response": choice})
        await self.report_human_decision(call_id, name, arguments, approved=approved)
        if not approved:
            raise Withheld("The pending tool call was not approved")

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
                sessions = await self.watcher.search_sessions(
                    external_ids={key: [value] for key, value in self.external_ids.items()}, limit=2
                )
                if sessions.total > 1 or len(sessions.sessions) > 1:
                    raise Withheld("The conversation matched multiple Watcher sessions")
                if sessions.total == 1 and len(sessions.sessions) == 1:
                    session = sessions.sessions[0].to_dict()
                    session_id = session["session_id"]
                    trajectory_id = session.get("latest_trajectory_id")
                    if not isinstance(trajectory_id, str) or not trajectory_id:
                        await asyncio.sleep(0.1)
                        continue
                    offset = 0
                    while True:
                        calls = await self.watcher.search_tool_calls(
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
                            raise Withheld("The pending tool identity matched multiple recorded calls")
                        if matching:
                            if (
                                matching[0].get("tool_name") != name
                                or matching[0].get("applied_decision") != "escalate"
                            ):
                                raise Withheld("The stored call does not match the pending escalation")
                            original = await self._stored_escalation(
                                session_id, trajectory_id, call_id, name, arguments
                            )
                            if original.get("tool_status") != "pending":
                                raise Withheld("The stored tool is no longer pending execution")
                            receipt = await self.watcher.upload_tool_call_decisions_batch(
                                session_id=session_id, decisions=[payload]
                            )
                            stored = receipt.to_dict()
                            if (
                                stored.get("synced_tool_use_ids") != [call_id]
                                or stored.get("synced_count") != 1
                                or stored.get("failed_tool_use_ids")
                                or stored.get("failed_tool_call_grade_ids")
                            ):
                                raise Withheld("Watcher did not acknowledge the human decision")
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
                                raise Withheld(
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
        response = await self.watcher.get_trajectory(session_id, trajectory_id, view=TrajectoryView.EXTENDED)
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
            raise Withheld("The stored trajectory does not match the pending escalation")
        return decision

    async def record(self, messages: list[dict]) -> None:
        """Submit results without regrading; acceptance does not confirm durable storage."""
        outcomes = await self.watcher.pre_tool_use_hook(
            [],
            messages=deepcopy(messages),
            external_ids={"other": self.session_id},
            timeout=self.timeout,
        )
        if outcomes:
            raise Withheld("Unexpected ingestion response")

    async def dispatch(self, messages: list[dict], inputs: list[dict], functions: dict) -> list[dict]:
        """Authorize the complete batch before invoking any registered async tool.

        Unknown tools and monitoring failures propagate with zero side effects.
        Ordinary tool exceptions become linked error results. The native caller
        records the converted results to keep future transcript prefixes identical.
        Callers must not retry an identity after execution or recording failure.
        """
        messages, inputs = deepcopy(messages), deepcopy(inputs)
        if any(item["tool_name"] not in functions for item in inputs):
            await self.record(messages)
            raise Withheld("Unregistered tool requested")
        callbacks = [functions[item["tool_name"]] for item in inputs]
        await self.authorize(messages, inputs)
        results = []
        for item, callback in zip(inputs, callbacks, strict=True):
            result = {"role": "tool", "tool_call_id": item["tool_use_id"]}
            try:
                value = await callback(**deepcopy(item["tool_input"]))
                result["content"] = json.dumps(value, ensure_ascii=False)
            except Exception as error:
                result["content"] = json.dumps({"error": type(error).__name__})
            results.append(result)
        return results
