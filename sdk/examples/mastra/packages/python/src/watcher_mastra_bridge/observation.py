"""Bounded, ordered client-side monitoring through the public Watcher SDK.

Call flush before shutdown,
then inspect error_count/errors and judgments. It is not a durable queue.
"""

import asyncio
from copy import deepcopy

from watcher_sdk import AsyncWatcherClient


def validate_observation(outcome: object, expected_id: str) -> bool:
    """Validate an advisory server outcome and report whether to checkpoint its judgment.

    Inherit the server's effective policy. Historical observations never execute
    or block a native action. Paused bypasses and configured grading-failure
    outcomes are valid but stay eligible for assessment on a later callback.
    Invalid provenance or a mismatched identity raises before it can be cached.
    """
    serialize = getattr(outcome, "to_dict", None)
    if not callable(serialize):
        raise ValueError("Watcher returned an invalid observation outcome")
    result = serialize()
    if not isinstance(result, dict) or result.get("tool_use_id") != expected_id:
        raise ValueError("Watcher returned another call's observation")
    source, failure = result.get("decision_source"), result.get("grading_error")
    if source == "grading_error":
        if (
            not isinstance(failure, dict)
            or failure.get("code")
            not in {"timeout", "at_capacity", "allowance_exhausted", "grader_failed", "no_result"}
            or not isinstance(failure.get("message"), str)
        ):
            raise ValueError("Watcher returned invalid grading-failure provenance")
    elif failure is not None:
        raise ValueError("Watcher returned inconsistent grading provenance")
    decision, mode, judged = result.get("decision"), result.get("enforcement_mode"), result.get("judged_decision")
    if mode == "paused" and decision == "deferred" and source == "bypass" and judged is None:
        return False
    if source not in {"threshold", "rule", "triage", "policy_gateway", "grading_error"} or judged not in {
        "allow",
        "deny",
        "escalate",
    }:
        raise ValueError("Watcher returned an incomplete observation judgment")
    if (mode == "observe" and decision == "deferred") or (mode == "enforce" and decision == judged):
        return source != "grading_error"
    raise ValueError("Watcher returned an inconsistent observation decision")


class ObservationQueue:
    """Queue at most 32 snapshots and retain the latest 128 outcomes/errors.

    Provider calls never await grading. Snapshots are submitted in arrival order;
    a full queue explicitly drops the newest snapshot and increments error_count.
    Submission acceptance does not confirm durable recording. Server policy is inherited
    without overrides. Paused mode records history without grading. Responses are
    advisory to completed actions. flush must run after producers stop.
    """

    def __init__(self, watcher: AsyncWatcherClient, session_id: str):
        if not session_id:
            raise ValueError("A conversation ID is required")
        self.watcher = watcher
        self.session_id = session_id
        self.tasks: list[asyncio.Task] = []
        self.errors: list[str] = []
        self.error_count = 0
        self.judgments: list = []

    def fail(self, kind: str) -> None:
        """Expose content-free failure names while bounding diagnostic retention."""
        self.error_count += 1
        self.errors = [*self.errors[-127:], kind]

    def enqueue(self, messages: list[dict], inputs: list[dict]) -> None:
        """Detach one complete transcript; fail visibly when pending work is full."""
        for task in self.tasks:
            if task.cancelled():
                self.fail("CancelledError")
            elif task.done() and (error := task.exception()) is not None:
                self.fail(type(error).__name__)
        self.tasks = [task for task in self.tasks if not task.done()]
        if len(self.tasks) >= 32:
            self.fail("ObservationQueueFull")
            return
        previous = self.tasks[-1] if self.tasks else None
        self.tasks.append(asyncio.create_task(self._submit(previous, deepcopy(messages), deepcopy(inputs))))

    async def _submit(self, previous, messages, inputs) -> None:
        if previous is not None:
            # Preserve ordering without inheriting a predecessor's failure or cancellation.
            await asyncio.wait([previous])
        try:
            outcomes = await self.watcher.pre_tool_use_hook(
                inputs,
                messages=messages,
                external_ids={"other": self.session_id},
            )
            if not isinstance(outcomes, list) or len(outcomes) != len(inputs):
                self.fail("OutcomeCountMismatch")
                return
            for item, outcome in zip(inputs, outcomes, strict=True):
                serialize = getattr(outcome, "to_dict", None)
                if not callable(serialize):
                    self.fail("IncompleteJudgment")
                    continue
                payload = serialize()
                if not isinstance(payload, dict):
                    self.fail("IncompleteJudgment")
                    continue
                if payload.get("tool_use_id") != item["tool_use_id"]:
                    self.fail("OutcomeIdentityMismatch")
                elif "status_code" in payload:
                    self.fail(f"HookCallError:{payload['status_code']}")
                else:
                    try:
                        has_judgment = validate_observation(outcome, item["tool_use_id"])
                    except ValueError:
                        self.fail("IncompleteJudgment")
                    else:
                        if has_judgment:
                            self.judgments = [*self.judgments[-127:], outcome]
                        elif payload.get("grading_error") is not None:
                            self.fail("GradingFailurePolicyApplied")
        except Exception as error:
            # The public SDK can expose HTTP transport and response-parser exceptions directly.
            self.fail(type(error).__name__)

    async def flush(self) -> None:
        """Await all queued work after the producer stops; inspect error_count afterward."""
        tasks, self.tasks = self.tasks, []
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                self.fail(type(outcome).__name__)
