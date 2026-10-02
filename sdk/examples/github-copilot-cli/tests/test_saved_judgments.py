"""Keep content-free receipts of stored gate judgments and confirm them by reading Watcher back."""

import asyncio
import json
import time
from pathlib import Path
from typing import Literal
from uuid import UUID

import httpx
import pytest
from pydantic import BaseModel, Field, JsonValue
from readback_fixture import login_configuration
from test_identity import ARGS, MILLIS, SESSION, STAMP, hook_start, native_events, pending, write_log
from typer.testing import CliRunner
from watcher_github_copilot_cli import identity
from watcher_github_copilot_cli.cli import _print_review_check, app
from watcher_github_copilot_cli.diagnostics import (
    ReviewCheck,
    ReviewReceipt,
    escalated_calls,
    read_review_evidence,
    read_status,
    record_event,
)
from watcher_github_copilot_cli.integration import Escalation, PolicyDenial, apply_policy, observe_callback
from watcher_github_copilot_cli.reviews import call_hash, confirm_reviews, receipt
from watcher_github_copilot_cli.transcript import ESCALATION_MESSAGE

from watcher_sdk import AsyncWatcherClient
from watcher_sdk._generated.models import PreToolUseHookResponse

ROOT = f"github-copilot-cli:{SESSION}"
WORKER = f"{ROOT}:agent:worker-1"


@pytest.fixture(autouse=True)
def short_identity_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity, "IDENTITY_WAIT_SECONDS", 0.2)


class Judgment(BaseModel):
    """One stored decision as the trajectory endpoint returns it."""

    tool_use_id: str = "native-call"
    tool_name: str = "Bash"
    tool_input: dict[str, JsonValue] = Field(default_factory=lambda: dict(ARGS))
    applied: str = "deny"
    judged: str | None = "deny"
    mode: str = "enforce"
    source: str = "policy_gateway"
    grade_ids: list[UUID] = Field(default_factory=lambda: [UUID(int=3)])

    def wire(self) -> dict[str, JsonValue]:
        return {
            "tool_use_id": self.tool_use_id,
            "tool_name": self.tool_name,
            "raw_tool_call": {"tool_name": self.tool_name, "tool_input": self.tool_input, "cwd": "/workspace"},
            "policy_decision": "deny",
            "tool_status": "pending",
            "decision_source": self.source,
            "tool_call_id": str(UUID(int=1)),
            "tool_call_decision_id": str(UUID(int=2)),
            "tool_call_created_at": STAMP,
            "created_at": STAMP,
            "updated_at": STAMP,
            "applied_decision": self.applied,
            "judged_decision": self.judged,
            "enforcement_mode": self.mode,
            "grades": [
                {
                    "grader_id": str(UUID(int=4)),
                    "grades": {},
                    "tool_call_grade_id": str(grade_id),
                    "grader_version": 0,
                    "input_messages": [],
                    "run_kind": "policy_gateway",
                    "created_at": STAMP,
                }
                for grade_id in self.grade_ids
            ],
        }


class Trajectory(BaseModel):
    trajectory_id: str
    session_id: UUID
    judgments: list[Judgment] = Field(default_factory=list)
    messages: list[JsonValue] = Field(default_factory=list)

    def summary(self) -> dict[str, JsonValue]:
        return {
            "trajectory_id": self.trajectory_id,
            "session_id": str(self.session_id),
            "message_count": len(self.messages),
            "first_timestamp": STAMP,
            "last_timestamp": STAMP,
            "source": "watcher-hook",
        }

    def wire(self) -> dict[str, JsonValue]:
        return {
            "trajectory_id": self.trajectory_id,
            "session_id": str(self.session_id),
            "source": "watcher-hook",
            "messages": self.messages,
            "grades": [],
            "metadata": {},
            "created_at": STAMP,
            "tool_call_decisions": {judgment.tool_use_id: judgment.wire() for judgment in self.judgments},
        }


class StoredSession(BaseModel):
    session_id: UUID
    trajectories: list[Trajectory]
    latest: str


class SubmittedTool(BaseModel):
    tool_name: str
    tool_input: dict[str, JsonValue]
    tool_use_id: str | None = None


class Submission(BaseModel):
    input: SubmittedTool | list[JsonValue]
    messages: list[dict[str, JsonValue]]
    external_ids: dict[str, str] | None = None
    ephemeral: bool = False


class UploadedDecision(BaseModel):
    tool_use_id: str
    raw_tool_call: SubmittedTool
    applied_decision: str
    judged_decision: str | None = None
    enforcement_mode: str | None = None
    decision_source: str
    tool_status: str
    human_decision: str | None = None


class DecisionBatch(BaseModel):
    session_id: UUID
    decisions: list[UploadedDecision]


class SearchFilters(BaseModel):
    external_ids: dict[str, list[str]]


class Search(BaseModel):
    filters: SearchFilters


class JudgmentServer(BaseModel):
    """Answer the gate, transcript snapshots and the read-only judgment readback."""

    sessions: dict[str, StoredSession] = Field(default_factory=dict)
    response: dict[str, JsonValue] = Field(default_factory=dict)
    # Answers for particular paths of a patch, by the judged call's ``file_path``.
    path_responses: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)
    submissions: list[Submission] = Field(default_factory=list)
    uploads: list[UploadedDecision] = Field(default_factory=list)
    reads: list[str] = Field(default_factory=list)

    def respond(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api")
        if path == "/v1/hooks/pre-tool-use":
            submission = Submission.model_validate_json(request.content)
            self.submissions.append(submission)
            if isinstance(submission.input, list):
                assert submission.external_ids is not None
                stored = self.sessions.get(submission.external_ids["other"])
                if stored is not None:
                    stored.trajectories[0].messages = list(submission.messages)
                return httpx.Response(200, json=[])
            answer = self.path_responses.get(str(submission.input.tool_input.get("file_path")), self.response)
            return httpx.Response(200, json={**answer, "tool_use_id": submission.input.tool_use_id})
        if path == "/v1/tool-call-decisions/batch":
            batch = DecisionBatch.model_validate_json(request.content)
            [target] = [item for item in self.sessions.values() if item.session_id == batch.session_id]
            for decision in batch.decisions:
                self.uploads.append(decision)
                target.trajectories[0].judgments.append(
                    Judgment(
                        tool_use_id=decision.tool_use_id,
                        tool_name=decision.raw_tool_call.tool_name,
                        tool_input=decision.raw_tool_call.tool_input,
                        applied=decision.applied_decision,
                        judged=decision.judged_decision,
                        mode=decision.enforcement_mode or "",
                        source=decision.decision_source,
                        grade_ids=[],
                    )
                )
            synced: list[JsonValue] = [decision.tool_use_id for decision in batch.decisions]
            return httpx.Response(
                200, json={"synced_count": len(synced), "synced_tool_use_ids": synced, "failed_tool_use_ids": []}
            )
        if path == "/v1/sessions/search":
            [identity_filter] = Search.model_validate_json(request.content).filters.external_ids["other"]
            self.reads.append(f"search {identity_filter}")
            stored = self.sessions.get(identity_filter)
            rows = (
                []
                if stored is None
                else [
                    {
                        "session_id": str(stored.session_id),
                        "agent_platform": "other",
                        "trajectory_count": len(stored.trajectories),
                        "message_count": 2,
                        "started_at": STAMP,
                        "ended_at": STAMP,
                        "latest_trajectory_id": stored.latest,
                    }
                ]
            )
            return httpx.Response(200, json={"sessions": rows, "total": len(rows), "limit": 2, "offset": 0})
        assert request.method == "GET", f"Readback must not write: {path}"
        for stored in self.sessions.values():
            if path == f"/v1/sessions/{stored.session_id}/trajectories":
                self.reads.append(f"list {stored.session_id}")
                summaries: list[JsonValue] = [item.summary() for item in stored.trajectories]
                return httpx.Response(200, json={"trajectories": summaries, "total": len(summaries)})
            for trajectory in stored.trajectories:
                if path == f"/v1/sessions/{stored.session_id}/trajectories/{trajectory.trajectory_id}":
                    self.reads.append(f"get {trajectory.trajectory_id} {request.url.params['view']}")
                    return httpx.Response(200, json=trajectory.wire())
        raise AssertionError(f"Unexpected route: {path}")


def stored(*judgments: Judgment, session: UUID = SESSION, trajectory: str = "latest") -> StoredSession:
    return StoredSession(
        session_id=session,
        trajectories=[Trajectory(trajectory_id=trajectory, session_id=session, judgments=list(judgments))],
        latest=trajectory,
    )


def client_for(server: JudgmentServer) -> AsyncWatcherClient:
    return AsyncWatcherClient(
        httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(server.respond))
    )


def outcome(
    decision: str = "deny",
    judged: str | None = "deny",
    mode: str = "enforce",
    source: str = "rule",
    **stages: JsonValue,
) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {
        "decision": decision,
        "judged_decision": judged,
        "enforcement_mode": mode,
        "decision_source": source,
        "verdict": {},
        "latency_ms": 1,
    }
    return result | stages


def gate(server: JudgmentServer, config: Path, callback: dict[str, JsonValue] | None = None) -> str:
    """Run the gate for the pending call and return how it ended."""

    async def run() -> str:
        async with client_for(server) as client:
            try:
                return await apply_policy(client, callback or pending().model_dump(), config=config)
            except PolicyDenial:
                return "deny"
            except Escalation:
                return "escalate"

    return asyncio.run(run())


def diagnostics_text(config: Path) -> str:
    return "".join(
        path.read_text()
        for path in (config.with_name("events.jsonl"), config.with_name("events.previous.jsonl"))
        if path.exists()
    )


@pytest.mark.parametrize("mode", ["enforce", "observe", "paused"])
def test_a_stored_judgment_leaves_a_content_free_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    write_log(tmp_path, native_events())
    config = tmp_path / "config.json"
    server = JudgmentServer(
        response=outcome(
            decision="deny" if mode == "enforce" else "deferred",
            judged=None if mode == "paused" else "deny",
            mode=mode,
            source="bypass" if mode == "paused" else "rule",
        )
    )

    ended = gate(server, config)

    [submission] = server.submissions
    assert submission.ephemeral is False and submission.external_ids == {"other": ROOT}
    assert isinstance(submission.input, SubmittedTool) and submission.input.tool_use_id == "native-call"
    assert submission.input.tool_name == "Bash"
    assert ended == ("deny" if mode == "enforce" else "deferred")
    [saved] = read_review_evidence(config, SESSION).receipts
    assert saved.model_dump(exclude={"receipt_id"}) == {
        "native_session": SESSION,
        "identity": ROOT,
        "tool_use_id": "native-call",
        "call_hash": call_hash("Bash", ARGS),
        "decision": "deny" if mode == "enforce" else "deferred",
        "judged_decision": None if mode == "paused" else "deny",
        "enforcement_mode": mode,
        "decision_source": "bypass" if mode == "paused" else "rule",
        "grade_ids": [],
        "grade_ids_complete": True,
        "stored_by": "gate",
        "decided_at": None,
    }
    assert "PRIVATE_MARKER" not in diagnostics_text(config)


def test_another_calls_answer_leaves_no_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    write_log(tmp_path, native_events())
    config = tmp_path / "config.json"

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={**outcome(decision="allow", judged="allow"), "tool_use_id": "wrong-call"})

    async def run() -> None:
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, pending().model_dump(), config=config)

    with pytest.raises(ValueError, match="another call"):
        asyncio.run(run())
    assert read_review_evidence(config, SESSION).receipts == []


@pytest.mark.parametrize("decision", ["allow", "escalate"])
def test_identical_calls_are_judged_without_storing_and_their_gap_is_scoped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, decision: str
) -> None:
    # Neither identical call is chosen, so no judgment, receipt or escalation names
    # one; the gap names the session and a hash of the call, never its arguments.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    write_log(tmp_path, native_events(duplicate=True))
    config = tmp_path / "config.json"
    server = JudgmentServer(response=outcome(decision=decision, judged=decision))

    assert gate(server, config) == decision

    [submission] = server.submissions
    assert submission.ephemeral is True and isinstance(submission.input, SubmittedTool)
    assert submission.input.tool_use_id is None
    evidence = read_review_evidence(config, SESSION)
    assert evidence.receipts == [] and evidence.unscoped_gaps == []
    [gap] = evidence.gaps
    assert (gap.reason, gap.native_session, gap.call_hash, gap.tool_use_id) == (
        "tool_call_ambiguous",
        SESSION,
        call_hash("Bash", ARGS),
        None,
    )
    assert escalated_calls(config, SESSION) == set()
    status = read_status(config)
    assert status.last_review_gap is not None and status.last_review_gap.reason == "tool_call_ambiguous"
    assert "PRIVATE_MARKER" not in diagnostics_text(config)


def test_a_subagent_call_is_stored_on_its_own_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    write_log(tmp_path, native_events(agent="worker-1"))
    config = tmp_path / "config.json"
    server = JudgmentServer(response=outcome(decision="escalate", judged="escalate"))

    assert gate(server, config, pending("worker-1").model_dump()) == "escalate"

    [submission] = server.submissions
    assert submission.ephemeral is False and submission.external_ids == {"other": WORKER}
    assert isinstance(submission.input, SubmittedTool) and submission.input.tool_use_id == "native-call"
    assert submission.messages[-1]["tool_calls"] == [{"id": "native-call", "function": "Bash", "arguments": ARGS}]
    [saved] = read_review_evidence(config, SESSION).receipts
    assert saved.identity == WORKER and saved.native_session == SESSION
    assert escalated_calls(config, SESSION) == {"native-call"}


def test_an_unlinked_subagent_gap_without_a_parent_is_unscoped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    config = tmp_path / "config.json"

    gate(JudgmentServer(response=outcome(decision="allow", judged="allow")), config, pending("worker-1").model_dump())

    evidence = read_review_evidence(config, None)
    assert evidence.gaps == []
    [gap] = evidence.unscoped_gaps
    assert gap.reason == "subagent_no_log" and gap.native_session is None


def response(**fields: JsonValue) -> PreToolUseHookResponse:
    return PreToolUseHookResponse.from_dict({**outcome(), "tool_use_id": "native-call", **fields})


GRADE_A, GRADE_B = UUID(int=10), UUID(int=11)


@pytest.mark.parametrize(
    "fields,grade_ids,complete",
    [
        ({"decision_source": "rule"}, [], True),
        ({"decision_source": "threshold"}, [], True),
        ({"decision_source": "triage", "triage": {"tool_call_grade_id": str(GRADE_A)}}, [GRADE_A], True),
        ({"decision_source": "triage"}, [], False),
        ({"decision_source": "triage", "triage": None}, [], False),
        ({"decision_source": "triage", "triage": {}}, [], False),
        ({"decision_source": "policy_gateway", "gateway": {"tool_call_grade_id": str(GRADE_B)}}, [GRADE_B], True),
        ({"decision_source": "policy_gateway", "triage": {"tool_call_grade_id": str(GRADE_A)}}, [GRADE_A], False),
        (
            {
                "decision_source": "policy_gateway",
                "triage": {"tool_call_grade_id": str(GRADE_A)},
                "gateway": {"tool_call_grade_id": str(GRADE_B)},
            },
            [GRADE_A, GRADE_B],
            True,
        ),
        (
            {"decision_source": "policy_gateway", "triage": {}, "gateway": {"tool_call_grade_id": str(GRADE_B)}},
            [GRADE_B],
            False,
        ),
    ],
)
def test_a_receipt_keeps_every_grade_link_and_whether_any_is_missing(
    fields: dict[str, JsonValue], grade_ids: list[UUID], complete: bool
) -> None:
    saved = receipt(
        response(**fields), native_session=SESSION, identity=ROOT, tool_use_id="native-call", fingerprint="hash"
    )
    assert saved.grade_ids == grade_ids and saved.grade_ids_complete is complete


def record_receipt(
    config: Path,
    *,
    tool_use_id: str = "native-call",
    identity_name: str = ROOT,
    session: UUID = SESSION,
    mode: Literal["enforce", "paused"] = "enforce",
    grade_ids: list[UUID] | None = None,
    complete: bool = True,
) -> ReviewReceipt:
    saved = ReviewReceipt(
        native_session=session,
        identity=identity_name,
        tool_use_id=tool_use_id,
        call_hash=call_hash("Bash", ARGS),
        decision="deferred" if mode == "paused" else "deny",
        judged_decision=None if mode == "paused" else "deny",
        enforcement_mode=mode,
        decision_source="bypass" if mode == "paused" else "policy_gateway",
        grade_ids=[UUID(int=3)] if grade_ids is None else grade_ids,
        grade_ids_complete=complete,
    )
    record_event(config, "reviewed", review=saved)
    return saved


def check(server: JudgmentServer, config: Path, *, session: UUID | None = SESSION, timeout: float = 0.4) -> ReviewCheck:
    async def run() -> ReviewCheck:
        async with client_for(server) as client:
            return await confirm_reviews(client, config, native_session=session, timeout=timeout)

    return asyncio.run(run())


@pytest.mark.parametrize(
    "state",
    [
        "saved",
        "extra-grades",
        "missing-grade",
        "wrong-input",
        "wrong-tool",
        "wrong-mode",
        "missing",
        "no-session",
        "incomplete-grades",
        "paused",
        "rotated",
    ],
)
def test_a_receipt_is_confirmed_only_by_the_exact_stored_judgment_and_its_grades(tmp_path: Path, state: str) -> None:
    config = tmp_path / "config.json"
    record_receipt(config, mode="paused" if state == "paused" else "enforce", complete=state != "incomplete-grades")
    if state == "rotated":
        with config.with_name("events.jsonl").open("a") as stream:
            stream.write(" " * (512 * 1024) + "\n")
        record_event(config, "started")
    judgment = Judgment(
        grade_ids=[]
        if state == "missing-grade"
        else [UUID(int=3), UUID(int=9)]
        if state == "extra-grades"
        else [UUID(int=3)],
        tool_input={"command": "different"} if state == "wrong-input" else dict(ARGS),
        tool_name="Read" if state == "wrong-tool" else "Bash",
        mode="observe" if state == "wrong-mode" else "enforce",
    )
    server = JudgmentServer(
        sessions={} if state == "no-session" else {ROOT: stored(*([] if state == "missing" else [judgment]))}
    )

    result = check(server, config)

    confirmed = state in {"saved", "extra-grades", "rotated"}
    assert (result.confirmed, result.unconfirmed, result.skipped) == (
        int(confirmed),
        int(not confirmed and state != "paused"),
        int(state == "paused"),
    )
    assert result.failure == (None if confirmed or state == "paused" else "review")
    if state in {"paused", "incomplete-grades"}:
        # Nothing can confirm these, so nothing is read for them.
        assert server.reads == []
    else:
        assert all(read.endswith("truncated") for read in server.reads if read.startswith("get"))
    assert read_status(config).last_review_check == result


def test_a_readback_can_leave_the_diagnostics_unchanged(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    record_receipt(config)
    events = config.with_name("events.jsonl").read_bytes()
    status = config.with_name("status.json").read_bytes()

    async def run() -> ReviewCheck:
        async with client_for(JudgmentServer(sessions={ROOT: stored(Judgment())})) as client:
            return await confirm_reviews(client, config, native_session=None, timeout=0.4, record=False)

    result = asyncio.run(run())

    assert (result.confirmed, result.unconfirmed, result.failure) == (1, 0, None)
    assert config.with_name("events.jsonl").read_bytes() == events
    assert config.with_name("status.json").read_bytes() == status


def test_a_readback_without_repeats_reads_each_receipt_once(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    record_receipt(config)
    # The judgment is never stored, so a repeating readback would poll until its timeout.
    server = JudgmentServer(sessions={ROOT: stored()})

    async def run() -> ReviewCheck:
        async with client_for(server) as client:
            return await confirm_reviews(client, config, native_session=None, timeout=30, repeat=False)

    started = time.monotonic()
    result = asyncio.run(run())

    assert time.monotonic() - started < 10
    assert (result.confirmed, result.unconfirmed, result.failure) == (0, 1, "review")
    assert [read for read in server.reads if read.startswith("search")] == [f"search {ROOT}"]


def test_a_delayed_judgment_is_confirmed_once_it_is_stored(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    record_receipt(config)
    server = JudgmentServer(sessions={ROOT: stored()})
    original = server.respond

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/trajectories/latest") and server.reads.count("get latest truncated") == 1:
            server.sessions[ROOT].trajectories[0].judgments.append(Judgment())
        return original(request)

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            return await confirm_reviews(client, config, native_session=SESSION, timeout=2)

    result = asyncio.run(run())

    assert (result.confirmed, result.unconfirmed, result.failure) == (1, 0, None)


def test_a_judgment_on_an_earlier_branch_is_confirmed_once(tmp_path: Path) -> None:
    # A rewind leaves the judged call on an earlier trajectory than the latest one.
    config = tmp_path / "config.json"
    record_receipt(config)
    record_receipt(config, tool_use_id="new-call")
    session = StoredSession(
        session_id=SESSION,
        trajectories=[
            Trajectory(trajectory_id="after-rewind", session_id=SESSION, judgments=[Judgment(tool_use_id="new-call")]),
            Trajectory(trajectory_id="before-rewind", session_id=SESSION, judgments=[Judgment()]),
        ],
        latest="after-rewind",
    )
    server = JudgmentServer(sessions={ROOT: session})

    result = check(server, config)

    assert (result.confirmed, result.unconfirmed, result.failure) == (2, 0, None)
    assert server.reads == [
        f"search {ROOT}",
        f"list {SESSION}",
        "get after-rewind truncated",
        "get before-rewind truncated",
    ]


def test_a_subagent_receipt_is_confirmed_on_the_subagents_session(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    record_receipt(config, identity_name=WORKER)
    record_receipt(config, tool_use_id="other-session-call", session=UUID(int=99))
    server = JudgmentServer(sessions={WORKER: stored(Judgment(), session=UUID(int=7))})

    result = check(server, config)

    assert (result.confirmed, result.unconfirmed, result.native_session) == (1, 0, SESSION)
    assert all(ROOT not in read or WORKER in read for read in server.reads)


@pytest.mark.parametrize("blocked", ["search", "list", "get"])
def test_a_slow_readback_reports_a_failure_without_touching_delivery(tmp_path: Path, blocked: str) -> None:
    config = tmp_path / "config.json"
    record_receipt(config)
    record_event(config, "recorded", session=UUID(int=5))
    delivered = read_status(config).last_delivery
    server = JudgmentServer(sessions={ROOT: stored()})

    async def respond(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        kind = "search" if path.endswith("/search") else "list" if path.endswith("/trajectories") else "get"
        if kind == blocked:
            await asyncio.Event().wait()
        return server.respond(request)

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            async with asyncio.timeout(2):
                return await confirm_reviews(client, config, native_session=SESSION, timeout=0.1)

    result = asyncio.run(run())

    assert (result.confirmed, result.unconfirmed, result.failure) == (0, 1, "review")
    status = read_status(config)
    assert status.last_delivery == delivered and status.last_review_check == result
    # The check carries its own failure; the hooks' last error is left to them.
    assert status.last_error is None
    record_event(config, "recorded", session=UUID(int=5))
    after = read_status(config)
    # A later delivery confirms the transcript only; the judgment check stays as it was.
    assert after.last_delivery is not None and delivered is not None and after.last_delivery > delivered
    assert after.last_review_check == result


def test_a_failed_readback_never_hides_a_withheld_tool(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    record_receipt(config)
    record_event(config, "failed", failure="connection", hook="enforce")
    record_event(config, "recorded", session=UUID(int=5))

    result = check(JudgmentServer(), config, timeout=0.1)

    status = read_status(config)
    assert result.failure == "review" and status.last_review_check == result
    assert status.last_error is not None and (status.last_error.hook, status.last_error.failure) == (
        "enforce",
        "connection",
    )


def test_a_rejected_credential_is_reported_as_an_authentication_failure(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    record_receipt(config)

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "PRIVATE_ERROR"})

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            return await confirm_reviews(client, config, native_session=SESSION, timeout=0.4)

    result = asyncio.run(run())

    assert (result.confirmed, result.unconfirmed, result.failure) == (0, 1, "authentication")
    assert "PRIVATE_ERROR" not in diagnostics_text(config)


def test_receipts_confirmed_before_a_later_read_hangs_still_count(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    record_receipt(config, identity_name=WORKER, tool_use_id="worker-call")
    record_receipt(config)
    server = JudgmentServer(
        sessions={ROOT: stored(Judgment()), WORKER: stored(Judgment(tool_use_id="worker-call"), session=UUID(int=7))}
    )

    async def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search") and WORKER in request.content.decode():
            await asyncio.Event().wait()
        return server.respond(request)

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            return await confirm_reviews(client, config, native_session=SESSION, timeout=0.3)

    result = asyncio.run(run())

    # The newest receipt is read first, so an older identity cannot starve it.
    assert (result.confirmed, result.unconfirmed, result.failure) == (1, 1, "review")


def test_a_check_without_receipts_reads_nothing(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    server = JudgmentServer()

    result = check(server, config)

    assert (result.confirmed, result.unconfirmed, result.failure) == (0, 0, None)
    assert server.reads == []


@pytest.mark.parametrize("contents", [None, "not an event\n", '{"kind":"reviewed","at":"x"}\n'])
def test_missing_or_corrupt_diagnostics_confirm_nothing(tmp_path: Path, contents: str | None) -> None:
    config = tmp_path / "config.json"
    if contents is not None:
        config.with_name("events.jsonl").write_text(contents)
    evidence = read_review_evidence(config, None)
    assert evidence.receipts == [] and evidence.gaps == [] and evidence.unscoped_gaps == []


def test_an_unreadable_diagnostics_log_is_a_review_failure(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.with_name("events.jsonl").mkdir()

    result = check(JudgmentServer(), config)

    assert result.failure == "review"


def test_gaps_and_receipts_are_counted_per_session(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    record_receipt(config, mode="paused")
    record_event(config, "unrecorded_review", hook="enforce", reason="tool_call_ambiguous", native_session=SESSION)
    record_event(config, "unrecorded_review", hook="enforce", reason="tool_call_ambiguous", native_session=UUID(int=9))
    record_event(config, "unrecorded_review", hook="enforce", reason="subagent_no_log")

    result = check(JudgmentServer(), config)

    assert (result.skipped, result.gaps, result.unscoped_gaps) == (1, 1, 1)
    everything = check(JudgmentServer(), config, session=None)
    assert (everything.gaps, everything.unscoped_gaps, everything.native_session) == (2, 1, None)


def test_a_delivered_transcript_keeps_an_unlinked_review_visible(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    record_event(config, "unrecorded_review", hook="enforce", reason="tool_call_ambiguous", native_session=SESSION)
    record_event(config, "recorded", session=UUID(int=5))
    status = read_status(config)
    assert status.last_delivery is not None and status.last_error is None
    assert status.last_review_gap is not None and status.last_review_gap.reason == "tool_call_ambiguous"


@pytest.mark.timeout(10)
def test_a_recorded_turn_confirms_its_transcript_then_its_judgments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    config = tmp_path / "config.json"
    record_receipt(config)
    start, user, assistant, hook = native_events()
    result: dict[str, JsonValue] = {"content": "done"}
    events = [
        start,
        user,
        {"type": "assistant.turn_start", "data": {"turnId": "0"}},
        assistant,
        hook,
        {"type": "hook.end", "data": {"hookInvocationId": "invocation"}},
        {"type": "tool.execution_complete", "data": {"toolCallId": "native-call", "success": True, "result": result}},
        {"type": "assistant.message", "data": {"content": "Done"}},
        {"type": "assistant.turn_end", "data": {"turnId": "0"}},
    ]
    path = write_log(tmp_path, events)
    payload: dict[str, JsonValue] = {"sessionId": str(SESSION), "transcriptPath": str(path), "timestamp": MILLIS}
    with path.open("a") as stream:
        stream.write(json.dumps({"type": "hook.start", "data": {"hookType": "agentStop", "input": payload}}) + "\n")
    server = JudgmentServer(sessions={ROOT: stored(Judgment())})

    async def run():
        async with client_for(server) as client:
            return await observe_callback(client, payload, grade=False, config=config)

    recorded = asyncio.run(run())

    assert recorded is not None and recorded.session == SESSION
    snapshot = next(index for index, read in enumerate(server.reads) if read.startswith("get latest extended"))
    review = next(index for index, read in enumerate(server.reads) if read.startswith("get latest truncated"))
    assert snapshot < review
    status = read_status(config)
    assert status.last_delivery is not None and status.last_review_check is not None
    assert (status.last_review_check.confirmed, status.last_review_check.unconfirmed) == (1, 0)


def test_replay_prints_the_judgment_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    config = login_configuration(tmp_path / "config" / "config.json", tmp_path, "https://watcher.test/api")
    record_receipt(config)
    record_event(config, "unrecorded_review", hook="enforce", reason="tool_call_ambiguous", native_session=SESSION)
    write_log(
        tmp_path,
        [
            {"type": "session.start", "data": {"sessionId": str(SESSION)}},
            {"type": "user.message", "data": {"content": "Hello"}},
            {"type": "assistant.message", "data": {"content": "Hello back"}},
        ],
    )
    server = JudgmentServer(sessions={ROOT: stored(Judgment())})

    async def handle(transport: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        return server.respond(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)

    result = CliRunner().invoke(app, ["replay", "--config", str(config), "--session-id", str(SESSION)])

    assert result.exit_code == 0, result.output
    assert "Stored judgments: 1 confirmed, 0 unconfirmed, 0 not stored while paused" in result.stdout
    assert "Calls judged without storing: 1 in this session, 0 in an unknown session" in result.stdout


@pytest.mark.parametrize(
    ("check", "message"),
    [
        (None, "Stored judgments: not checked"),
        (ReviewCheck(native_session=UUID(int=9)), "Stored judgments: not checked"),
        (ReviewCheck(native_session=SESSION, failure="authentication"), "Watcher rejected the credential"),
        (ReviewCheck(native_session=SESSION, failure="review"), "did not match the gate's answer"),
    ],
    ids=["unreadable-status", "other-session", "authentication", "review"],
)
def test_replay_explains_a_judgment_check_it_cannot_show_or_that_failed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], check: ReviewCheck | None, message: str
) -> None:
    config = tmp_path / "config.json"
    if check is None:
        config.with_name("status.json").write_text("not a status")
    else:
        record_event(config, "reviews_checked", check=check)

    _print_review_check(config, SESSION)

    assert message in capsys.readouterr().out


MULTI_FILE_PATCH = (
    "*** Begin Patch\n*** Update File: status.txt\n@@\n-pending\n+complete\n"
    "*** Add File: protected/new.txt\n+PRIVATE_MARKER\n*** End Patch\n"
)


@pytest.mark.timeout(10)
def test_a_patch_escalated_by_a_later_file_shows_that_judgment_and_the_answer_once_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The gate cannot store a later file's judgment on the call, so recording stores
    # it with the person's answer, and the readback confirms what was stored.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    config = tmp_path / "config.json"
    patch_call: dict[str, JsonValue] = {
        "toolCallId": "patch-1",
        "name": "apply_patch",
        "arguments": MULTI_FILE_PATCH,
        "type": "custom",
    }
    start, user, _, _ = native_events()
    events = [
        start,
        user,
        {"type": "assistant.turn_start", "data": {"turnId": "0"}},
        {"type": "assistant.message", "data": {"content": "", "toolRequests": [patch_call]}},
        hook_start([{"id": "patch-1", "name": "apply_patch", "args": MULTI_FILE_PATCH}]),
    ]
    path = write_log(tmp_path, events)
    server = JudgmentServer(
        sessions={ROOT: stored()},
        response=outcome(decision="allow", judged="allow", source="threshold"),
        path_responses={"protected/new.txt": outcome(decision="escalate", judged="escalate", source="rule")},
    )
    callback = {**pending().model_dump(), "toolName": "apply_patch", "toolArgs": MULTI_FILE_PATCH}

    assert gate(server, config, callback) == "escalate"
    assert [submission.ephemeral for submission in server.submissions] == [True, True]

    permission = {"kind": "hook", "toolCallId": "patch-1", "toolName": "apply_patch", "hookMessage": ESCALATION_MESSAGE}
    result: dict[str, JsonValue] = {"content": "done"}
    payload: dict[str, JsonValue] = {"sessionId": str(SESSION), "transcriptPath": str(path), "timestamp": MILLIS}
    later = [
        {"type": "permission.requested", "data": {"requestId": "prompt", "permissionRequest": permission}},
        {
            "type": "permission.completed",
            "timestamp": "2026-09-30T12:00:05.000Z",
            "data": {
                "requestId": "prompt",
                "toolCallId": "patch-1",
                "result": {"kind": "approved"},
                "decisionSource": "human_response",
            },
        },
        {"type": "hook.end", "data": {"hookInvocationId": "invocation"}},
        {"type": "tool.execution_complete", "data": {"toolCallId": "patch-1", "success": True, "result": result}},
        {"type": "assistant.message", "data": {"content": "Done"}},
        {"type": "assistant.turn_end", "data": {"turnId": "0"}},
        {"type": "hook.start", "data": {"hookType": "agentStop", "input": payload}},
    ]
    with path.open("a") as stream:
        stream.writelines(json.dumps(event) + "\n" for event in later)

    async def run():
        async with client_for(server) as client:
            return await observe_callback(client, payload, grade=False, config=config)

    recorded = asyncio.run(run())

    assert recorded is not None and recorded.session == SESSION
    [upload] = server.uploads
    assert (upload.tool_use_id, upload.raw_tool_call.tool_name) == ("patch-1", "Edit")
    assert (upload.applied_decision, upload.judged_decision, upload.decision_source) == ("escalate", "escalate", "rule")
    assert (upload.human_decision, upload.tool_status) == ("allow", "completed")
    status = read_status(config)
    assert status.last_review_check is not None and status.last_review_gap is None
    assert (status.last_review_check.confirmed, status.last_review_check.unconfirmed) == (1, 0)
    assert "PRIVATE_MARKER" not in diagnostics_text(config)
