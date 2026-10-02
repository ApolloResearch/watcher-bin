"""Observe real Aider writes through injected Model and InputOutput subclasses.

Only controlled nonstreaming Coder runs are supported. Model request snapshots
retain the complete context that preceded each write. The archive concatenates
full model exchanges, so context repeated by Aider remains repeated in the record.
Write IDs belong to this application and identify IO invocations, not model tools.
"""

from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from aider.coders import Coder
from aider.io import InputOutput
from aider.models import Model
from pydantic import BaseModel, Field

from watcher_aider.conversion import normalize_chat
from watcher_sdk import AsyncWatcherClient


class Capture(BaseModel):
    """Hold native model exchanges and IO receipts for one sequential Coder instance."""

    exchanges: list[dict] = Field(default_factory=list)
    active: dict | None = None
    skipped_dry_runs: int = 0
    unassociated_writes: int = 0


class ObservedModel(Model):
    """Preserve native request/response objects while delegating model execution unchanged."""

    def __init__(self, name: str, capture: Capture):
        super().__init__(name)
        self.capture = capture

    def send_completion(self, messages, functions, stream, temperature=None):
        if stream:
            raise ValueError("This observer supports nonstreaming Coder runs only")
        self.capture.active = None
        request = deepcopy(messages)
        result = super().send_completion(messages, functions, stream, temperature)
        response = result[1].model_dump(exclude_none=True)
        exchange = {"request": request, "response": response, "writes": []}
        self.capture.exchanges.append(exchange)
        self.capture.active = exchange
        return result


class ObservedIO(InputOutput):
    """Record actual write_text invocations without changing their result or exception.

    Dry runs do not write and therefore produce no operation. Writes without a
    preceding captured model response are counted separately, never attributed to
    a model by guessing from a filename or output message.
    """

    def __init__(self, capture: Capture, **kwargs):
        super().__init__(**kwargs)
        self.capture = capture

    def write_text(self, filename, content, max_retries=5, initial_delay=0.1):
        if self.dry_run:
            self.capture.skipped_dry_runs += 1
            return super().write_text(filename, content, max_retries, initial_delay)
        exchange = self.capture.active
        operation = {
            "id": str(uuid4()),
            "arguments": {"path": str(Path(filename).resolve()), "content": content},
            "status": "running",
        }
        if exchange is not None:
            exchange["writes"].append(operation)
        else:
            self.capture.unassociated_writes += 1
        try:
            result = super().write_text(filename, content, max_retries, initial_delay)
        except (OSError, UnicodeError) as error:
            operation.update(status="error", error=type(error).__name__)
            raise
        operation["status"] = "completed"
        return result


def run_prompt(coder: Coder, capture: Capture, prompt: str):
    """Run one native instruction, preventing later writes from inheriting stale context."""
    capture.active = None
    try:
        return coder.run(with_message=prompt)
    finally:
        capture.active = None


def exchange_messages(exchange: dict) -> list[dict]:
    """Normalize the native model exchange without parsing its edit instructions."""
    choices = exchange["response"]["choices"]
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("Aider observation requires one complete native model response")
    choice = choices[0]
    if choice.get("index", 0) != 0 or choice.get("finish_reason") is None:
        raise ValueError("Aider observation requires the complete first response choice")
    message = choice["message"]
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise ValueError("The captured native model response is not an assistant message")
    return normalize_chat([*exchange["request"], message])


def write_messages(operation: dict) -> list[dict]:
    """Represent one application-observed IO call and its captured terminal outcome."""
    if operation["status"] not in {"completed", "error", "withheld"}:
        raise ValueError("Cannot report an incomplete native write")
    result = {
        "role": "tool",
        "tool_call_id": operation["id"],
        "content": {
            "completed": "File write completed",
            "error": "File write failed",
            "withheld": "File write withheld before execution",
        }[operation["status"]],
    }
    if operation["status"] in {"error", "withheld"}:
        result["error"] = {"type": "unknown", "message": operation["error"]}
    return [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": operation["id"], "function": "aider_write_file", "arguments": operation["arguments"]}
            ],
        },
        result,
    ]


def archive_messages(capture: Capture) -> list[dict]:
    """Build an exchange journal with actual IO receipts after each native response.

    Full request contexts intentionally recur for successive model exchanges. This
    preserves every context snapshot; it is not Aider's compacted chat transcript.
    """
    messages = []
    for exchange in capture.exchanges:
        messages.extend(exchange_messages(exchange))
        for operation in exchange["writes"]:
            messages.extend(write_messages(operation))
    return messages


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


async def send_capture(
    client: AsyncWatcherClient, session_id: str, capture: Capture, *, record_only: bool = False
) -> None:
    """Judge completed writes against their original model context, then flush the journal.

    Rules and triage run within the 10-second per-write budget; gateway grading is
    excluded. A timeout can leave server-side work running and billable. All native
    execution is finished before submission. A Watcher failure propagates
    to the caller after the final upload attempt and cannot undo or prevent a write.
    Reusing this capture reuses operation IDs. Server policy is inherited: paused
    mode records history without grading, and returned decisions are advisory to
    already-completed writes. No historical execution outcome is synthesized.
    """
    if not session_id:
        raise ValueError("A session ID is required")
    identity = {"other": "aider:" + session_id}
    if record_only:
        outcomes = await client.pre_tool_use_hook(
            input=[], messages=archive_messages(capture), external_ids=identity, timeout=10
        )
        if outcomes != []:
            raise ValueError("Transcript-only submission returned unexpected outcomes")
        return
    try:
        for exchange in capture.exchanges:
            context = exchange_messages(exchange)
            for operation in exchange["writes"]:
                call, _ = write_messages(operation)
                outcomes = await client.pre_tool_use_hook(
                    input=[
                        {
                            "tool_use_id": operation["id"],
                            "tool_name": "aider_write_file",
                            "tool_input": operation["arguments"],
                        }
                    ],
                    messages=context + [call],
                    external_ids=identity,
                    mode="triage_only",
                    timeout=10,
                )
                if len(outcomes) != 1:
                    raise ValueError("Watcher returned incomplete write observation")
                validate_observation(outcomes[0], operation["id"])
    finally:
        await client.pre_tool_use_hook(input=[], messages=archive_messages(capture), external_ids=identity, timeout=10)
