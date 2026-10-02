"""Bounded, ordered client-side monitoring through the public Watcher SDK.

Copy this example-local helper with its integration. Call flush before shutdown,
then inspect error_count/errors and judgments. It is not a durable queue.
"""

import asyncio
from copy import deepcopy

from watcher_sdk import AsyncWatcherClient


class ObservationQueue:
    """Queue at most 32 snapshots and retain the latest 128 outcomes/errors.

    Provider calls never await grading. Snapshots are submitted in arrival order;
    a full queue explicitly drops the newest snapshot and increments error_count.
    Requests inherit the server policy, including a locked or paused setting.
    Results describe retrospective evaluation and cannot block an already-run tool.
    Submission does not acknowledge durable storage. Flush after producers stop.
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
            if len(outcomes) != len(inputs):
                self.fail("OutcomeCountMismatch")
                return
            for item, outcome in zip(inputs, outcomes, strict=True):
                payload = outcome.to_dict()
                if payload.get("tool_use_id") != item["tool_use_id"]:
                    self.fail("OutcomeIdentityMismatch")
                elif "status_code" in payload:
                    self.fail(f"HookCallError:{payload['status_code']}")
                elif payload.get("enforcement_mode") == "paused":
                    if (
                        payload.get("decision") != "deferred"
                        or payload.get("decision_source") != "bypass"
                        or payload.get("judged_decision") is not None
                    ):
                        self.fail("UnexpectedPausedResult")
                elif payload.get("enforcement_mode") not in ("observe", "enforce") or payload.get("decision") != (
                    "deferred" if payload.get("enforcement_mode") == "observe" else payload.get("judged_decision")
                ):
                    self.fail("UnexpectedEnforcementMode")
                elif (
                    payload.get("judged_decision") not in ("allow", "deny", "escalate")
                    or payload.get("decision_source") not in ("threshold", "rule", "triage", "policy_gateway")
                    or payload.get("grading_error") is not None
                ):
                    self.fail("IncompleteJudgment")
                else:
                    self.judgments = [*self.judgments[-127:], outcome]
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
