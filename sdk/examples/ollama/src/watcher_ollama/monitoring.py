"""Apply configured Watcher policy before application-owned tool execution.

This example does not control provider-hosted tools. Keep one Monitor per complete
conversation; an attempted tool ID is never executed again by that instance.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Literal

from ollama import Message

from watcher_ollama.integration import messages_from_native
from watcher_sdk import AsyncWatcherClient


class Withheld(RuntimeError):
    """Watcher denied execution or the result could not be safely applied."""


class ApprovalRequired(Withheld):
    """Human approval is required before the pending native call can proceed."""


class RecordingFailed(RuntimeError):
    """Retain native history and Inspect messages when a recording request fails.

    Use ``history`` for the next native model turn and retry only
    ``monitor.record(error.messages)``. Tool effects may already have happened;
    neither retry dispatch nor regenerate the pending tool turn.
    """

    def __init__(self, history: list, messages: list[dict]):
        super().__init__("Conversation recording failed; history is retained")
        self.history = deepcopy(history)
        self.messages = deepcopy(messages)


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
    they block. Human callback results are not persisted to Watcher by this helper.
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
    ):
        if not session_id or timeout <= 0:
            raise ValueError("A conversation ID and positive timeout are required")
        self.watcher = watcher
        self.session_id = session_id
        self.timeout = timeout
        if enforcement not in {"server", "enforce", "observe", "paused"}:
            raise ValueError("Unsupported enforcement setting")
        self.settings = None if enforcement == "server" else {"enforcement": {"mode": enforcement}}
        self.approval_callback = approval_callback
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
                    batch,
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
        if approved is not True:
            raise Withheld("The pending tool call was not approved")

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

    async def record_history(self, history: list, messages: list[dict]) -> None:
        """Record a native turn while preserving recovery state on ordinary failures."""
        try:
            await self.record(messages)
        except Exception as error:
            raise RecordingFailed(history, messages) from error

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


async def run_turn(client, monitor: Monitor, *, model: str, messages: list, functions: dict, tools=None):
    """Gate native Ollama requests at the application dispatcher and return full history.

    The mapper rejects ambiguous same-name parallel calls because native results
    lack IDs. Distinct names and later repeated names retain stable history IDs.
    """
    history = deepcopy(messages)
    response = await client.chat(model=model, messages=history, tools=tools, stream=False)
    if not response.done or response.done_reason not in (None, "stop"):
        raise Withheld("Incomplete model response")
    history.append(response.message)
    mapped = messages_from_native(history)
    inputs = [
        {"tool_use_id": call["id"], "tool_name": call["function"], "tool_input": call["arguments"]}
        for call in mapped[-1].get("tool_calls", [])
    ]
    if inputs:
        results = await monitor.dispatch(mapped, inputs, functions)
        history.extend(
            Message(role="tool", tool_name=item["tool_name"], content=result["content"])
            for item, result in zip(inputs, results, strict=True)
        )
        await monitor.record_history(history, messages_from_native(history))
    else:
        await monitor.record_history(history, mapped)
    return history
