"""Store the judgment that governed a multi-file patch on its recorded call once recording confirms it."""

import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from pydantic import JsonValue
from watcher_github_copilot_cli import integration
from watcher_github_copilot_cli.diagnostics import ReviewReceipt, record_escalation, record_event
from watcher_github_copilot_cli.recording import RecordedSession, upload_decisions
from watcher_github_copilot_cli.reviews import call_hash
from watcher_github_copilot_cli.transcript import ConvertedSession, HumanResponse, SubagentHistory

from watcher_sdk import AsyncWatcherClient

NATIVE = UUID("4f3b0c9e-1c7d-4a47-9a0e-3a4e2f9b6c11")
ROOT = f"github-copilot-cli:{NATIVE}"
WATCHER_SESSION = UUID(int=1)
PATCH = (
    "*** Begin Patch\n*** Update File: status.txt\n@@\n-pending\n+complete\n"
    "*** Add File: notes.txt\n+PRIVATE_MARKER\n*** End Patch\n"
)
# A two-file patch as the transcript records it: an Edit named after its first file.
ARGUMENTS: dict[str, JsonValue] = {"file_path": "status.txt", "file_paths": ["status.txt", "notes.txt"], "input": PATCH}
DECIDED = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def conversation(*call_ids: str) -> list[dict[str, JsonValue]]:
    """A recorded conversation whose assistant made one patch call per ID."""
    return [
        {"role": "user", "content": "Finish the task"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": call_id, "function": "Edit", "arguments": ARGUMENTS, "type": "custom"} for call_id in call_ids
            ],
        },
    ]


def left_judgment(
    *,
    decision: str = "escalate",
    judged: str | None = "escalate",
    mode: str = "enforce",
    tool_use_id: str = "patch-1",
    identity: str = ROOT,
    fingerprint: str | None = None,
) -> ReviewReceipt:
    return ReviewReceipt.model_validate(
        {
            "native_session": NATIVE,
            "identity": identity,
            "tool_use_id": tool_use_id,
            "call_hash": fingerprint or call_hash("Edit", ARGUMENTS),
            "decision": decision,
            "judged_decision": judged,
            "enforcement_mode": mode,
            "decision_source": "rule",
            "grade_ids_complete": True,
            "stored_by": "recording",
            "decided_at": DECIDED,
        }
    )


def uploaded(
    messages: list[dict[str, JsonValue]],
    judgments: list[ReviewReceipt],
    responses: list[HumanResponse] | None = None,
    failed: list[str] | None = None,
) -> list[dict[str, JsonValue]]:
    """Run ``upload_decisions`` against a fixture server and return each request body."""
    bodies: list[dict[str, JsonValue]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/tool-call-decisions/batch"
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200, json={"synced_count": 1, "synced_tool_use_ids": [], "failed_tool_use_ids": failed or []}
        )

    async def run() -> None:
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await upload_decisions(client, WATCHER_SESSION, messages, judgments, responses or [])

    asyncio.run(run())
    return bodies


@pytest.mark.parametrize(
    "decision,judged,mode,policy,status",
    [
        ("escalate", "escalate", "enforce", "escalate", "pending"),
        ("deny", "deny", "enforce", "deny", "blocked"),
        ("deferred", "deny", "observe", "not_evaluated", "pending"),
    ],
)
def test_a_left_judgment_is_stored_as_the_gates_evaluation_of_the_recorded_call(
    decision: str, judged: str, mode: str, policy: str, status: str
) -> None:
    [body] = uploaded(conversation("patch-1"), [left_judgment(decision=decision, judged=judged, mode=mode)])
    assert body == {
        "session_id": str(WATCHER_SESSION),
        "decisions": [
            {
                "tool_use_id": "patch-1",
                "tool_name": "Edit",
                "raw_tool_call": {"tool_name": "Edit", "tool_input": ARGUMENTS},
                "policy_decision": policy,
                "applied_decision": decision,
                "judged_decision": judged,
                "enforcement_mode": mode,
                "decision_source": "rule",
                "tool_status": status,
                "decided_at": DECIDED.isoformat(),
            }
        ],
    }


def test_an_answer_to_the_same_call_travels_with_its_judgment() -> None:
    # The server keeps an evaluation over an answer for the same call in one batch,
    # so the two are sent as one item and the person's answer is not lost.
    answer = HumanResponse("patch-1", "Edit", ARGUMENTS, "allow", "2026-10-01T12:00:05.000Z", completed=True)
    other = HumanResponse("other", "Bash", {"command": "pwd"}, "deny", None, completed=False)
    [body] = uploaded(conversation("patch-1"), [left_judgment()], [answer, other])
    decisions = body["decisions"]
    assert isinstance(decisions, list) and len(decisions) == 2
    merged, separate = decisions
    assert isinstance(merged, dict) and isinstance(separate, dict)
    assert merged["tool_use_id"] == "patch-1" and merged["applied_decision"] == "escalate"
    assert merged["judged_decision"] == "escalate" and merged["decision_source"] == "rule"
    assert merged["human_decision"] == "allow" and merged["tool_status"] == "completed"
    assert merged["human_decided_at"] == "2026-10-01T12:00:05+00:00"
    assert separate["tool_use_id"] == "other" and separate["decision_source"] == "not_evaluated"


@pytest.mark.parametrize(
    "case",
    [
        "call-missing",
        "call-repeated",
        "other-arguments",
        "allow",
        "enforce-applied-deferred",
        "observe-applied-deny",
        "paused",
    ],
)
def test_a_judgment_is_stored_only_as_a_restriction_of_the_exact_recorded_call(case: str) -> None:
    # The agent can write to the diagnostics directory, so a receipt that does not
    # match the recorded call, or holds no deny or escalate applied as its mode
    # applies one, is never sent.
    messages = conversation("patch-1", "patch-1") if case == "call-repeated" else conversation("patch-1")
    judgment = {
        "call-missing": left_judgment(tool_use_id="absent"),
        "call-repeated": left_judgment(),
        "other-arguments": left_judgment(fingerprint=call_hash("Edit", {"file_path": "elsewhere.txt"})),
        "allow": left_judgment(decision="allow", judged="allow"),
        "enforce-applied-deferred": left_judgment(decision="deferred", judged="deny"),
        "observe-applied-deny": left_judgment(decision="deny", judged="deny", mode="observe"),
        "paused": left_judgment(decision="deferred", judged=None, mode="paused"),
    }[case]
    assert uploaded(messages, [judgment]) == []


@pytest.mark.parametrize(
    "function,arguments",
    [
        ("Bash", {"command": "rm -rf build"}),
        ("Edit", {"file_path": "status.txt", "input": "*** Begin Patch\n*** Update File: status.txt\n*** End Patch\n"}),
        # The input names two files, but the call is not what that patch translates to.
        ("Write", {"file_path": "elsewhere.txt", "file_paths": ["status.txt", "notes.txt"], "input": PATCH}),
    ],
)
def test_a_judgment_is_stored_only_on_a_multi_file_patch(function: str, arguments: dict[str, JsonValue]) -> None:
    # The gate leaves a judgment for recording only when a patch names several
    # files. A receipt for any other call was written by someone else, such as the
    # agent, and storing it would replace what the gate stored, so it is never sent.
    messages: list[dict[str, JsonValue]] = [
        {"role": "user", "content": "Finish the task"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call-1", "function": function, "arguments": arguments, "type": "function"}],
        },
    ]
    receipt = left_judgment(tool_use_id="call-1", fingerprint=call_hash(function, arguments))
    assert uploaded(messages, [receipt]) == []


def test_a_judgment_the_server_cannot_resolve_raises() -> None:
    with pytest.raises(ValueError, match="every decision"):
        uploaded(conversation("patch-1"), [left_judgment()], failed=["patch-1"])


def observed(
    monkeypatch: pytest.MonkeyPatch,
    config: Path,
    session: ConvertedSession,
    recorded: RecordedSession,
) -> list[tuple[UUID, list[str], list[str]]]:
    """Run a sessionEnd callback; return each upload's session, judged call IDs and answered call IDs."""
    uploads: list[tuple[UUID, list[str], list[str]]] = []

    async def converted(payload: Mapping[str, JsonValue], timeout: float) -> ConvertedSession:
        return session

    async def record(client: object, native: UUID, converted: ConvertedSession, **_: object) -> RecordedSession:
        return recorded

    async def capture(
        client: object,
        session_id: UUID,
        messages: list[dict[str, JsonValue]],
        judgments: list[ReviewReceipt],
        responses: list[HumanResponse],
    ) -> None:
        assert messages == (session.messages if session_id == recorded.session else session.subagents[0].messages)
        uploads.append((session_id, [item.tool_use_id for item in judgments], [item.tool_use_id for item in responses]))

    async def no_readback(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(integration, "read_ended_session", converted)
    monkeypatch.setattr(integration, "record_session", record)
    monkeypatch.setattr(integration, "upload_decisions", capture)
    monkeypatch.setattr(integration, "confirm_reviews", no_readback)
    client = AsyncWatcherClient(httpx_client=httpx.AsyncClient(base_url="http://unused"))
    payload: dict[str, JsonValue] = {"sessionId": str(NATIVE), "reason": "complete"}
    asyncio.run(integration.observe_callback(client, payload, grade=False, config=config))
    return uploads


def test_each_left_judgment_goes_to_the_watcher_session_of_its_conversation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = tmp_path / "config.json"
    worker, unconfirmed = f"{ROOT}:agent:worker-1", f"{ROOT}:agent:worker-2"
    for identity, call in [(ROOT, "patch-1"), (worker, "worker-patch"), (unconfirmed, "lost-patch")]:
        record_event(config, "reviewed", review=left_judgment(identity=identity, tool_use_id=call))
    # A judgment the gate stored itself, and another session's judgment, are not uploaded.
    record_event(config, "reviewed", review=left_judgment().model_copy(update={"stored_by": "gate"}))
    other = left_judgment().model_copy(update={"native_session": UUID(int=9), "tool_use_id": "elsewhere"})
    record_event(config, "reviewed", review=other)
    record_escalation(config, NATIVE, "patch-1")
    session = ConvertedSession(
        messages=conversation("patch-1"),
        subagents=[
            SubagentHistory("worker-1", conversation("worker-patch")),
            SubagentHistory("worker-2", conversation("lost-patch")),
        ],
        replied=True,
        human_responses=[HumanResponse("patch-1", "Edit", ARGUMENTS, "deny", None, completed=False)],
    )
    # worker-2 was not confirmed, so its judgment waits for a later callback.
    recorded = RecordedSession(session=WATCHER_SESSION, subagents={"worker-1": UUID(int=2)})

    uploads = observed(monkeypatch, config, session, recorded)

    assert uploads == [(WATCHER_SESSION, ["patch-1"], ["patch-1"]), (UUID(int=2), ["worker-patch"], [])]


def test_nothing_is_uploaded_without_a_left_judgment_or_answer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    session = ConvertedSession(messages=conversation("patch-1"), subagents=[], replied=True)
    recorded = RecordedSession(session=WATCHER_SESSION, subagents={})
    assert observed(monkeypatch, tmp_path / "config.json", session, recorded) == []


def test_unreadable_receipts_are_an_unsynced_decision_not_a_failed_recording(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def unreadable(config: Path, native_session: UUID | None) -> None:
        raise ValueError("A diagnostics file exceeds its size limit")

    monkeypatch.setattr(integration, "read_review_evidence", unreadable)
    config = tmp_path / "config.json"
    session = ConvertedSession(messages=conversation("patch-1"), subagents=[], replied=True)
    recorded = RecordedSession(session=WATCHER_SESSION, subagents={})
    assert observed(monkeypatch, config, session, recorded) == []
    kinds = [json.loads(line)["kind"] for line in config.with_name("events.jsonl").read_text().splitlines()]
    assert kinds == ["recorded", "unsynced_decisions"]
