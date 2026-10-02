"""Bounded, ordered observation of complete native provider HTTP pairs."""

import asyncio
from copy import deepcopy

from watcher_huggingface_inference.raw import inventory


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
    """Submit buffered pairs without holding the native response for grading.

    Server policy is inherited. Decisions are advisory because the provider reply
    has already been released. Failures and dropped work are visible through
    error_count/errors. Stop producers and flush before closing Watcher. This is
    not a durable queue, and hook success is not a storage receipt.
    """

    def __init__(self, watcher, session_id):
        if not session_id:
            raise ValueError("A conversation ID is required")
        self.watcher, self.session_id = watcher, session_id
        self.tasks, self.errors, self.judgments = [], [], []
        self.error_count = 0

    def fail(self, kind):
        self.error_count += 1
        self.errors = [*self.errors[-127:], kind]

    def enqueue(self, exchange):
        """Snapshot one original wire pair; drop visibly when the queue is full."""
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
        self.tasks.append(asyncio.create_task(self._submit(previous, deepcopy(exchange))))

    async def _submit(self, previous, exchange):
        if previous is not None:
            await asyncio.wait([previous])
        try:
            expected = {call["tool_use_id"] for call in inventory(exchange["response"], "chat_completions").values()}
            outcomes = await self.watcher.pre_tool_use_hook(
                request_body=exchange["request"],
                response_body=exchange["response"],
                url=exchange["url"],
                user_agent=exchange["user_agent"],
                provider="huggingface",
                external_ids={"other": self.session_id},
            )
            if not isinstance(outcomes, list) or len(outcomes) != len(expected):
                raise ValueError("Incomplete advisory response")
            completed = []
            for outcome in outcomes:
                serialize = getattr(outcome, "to_dict", None)
                if not callable(serialize):
                    raise ValueError("Invalid advisory response")
                identifier = serialize().get("tool_use_id")
                if not isinstance(identifier, str) or identifier not in expected:
                    raise ValueError("Unknown or repeated native tool ID")
                expected.remove(identifier)
                if validate_observation(outcome, identifier):
                    completed.append(outcome)
            self.judgments = [*self.judgments, *completed][-128:]
        except Exception as error:
            self.fail(type(error).__name__)

    async def flush(self):
        """Wait for pending submissions and retain cancellation/failure diagnostics."""
        tasks, self.tasks = self.tasks, []
        for result in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(result, BaseException):
                self.fail(type(result).__name__)
