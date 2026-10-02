"""Confirm storage independently of successful snapshot submission."""

import asyncio
from copy import deepcopy
from typing import Literal
from uuid import UUID

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, Field, JsonValue
from watcher_github_copilot_cli import recording
from watcher_github_copilot_cli.recording import record_messages
from watcher_github_copilot_cli.transcript import ConvertedSession, SubagentHistory

from watcher_sdk import AsyncWatcherClient, WatcherAPIError

SESSION_ID = "65dc89f8-e94d-4f54-8503-cb218d015a18"
IDENTITY = "github-copilot-cli:68a8d4d3-dfe1-4aa9-b34c-1013640fafc7"
MESSAGES: list[dict[str, JsonValue]] = [
    {"role": "user", "content": "Read the status."},
    {
        "role": "assistant",
        "content": "Checking.",
        "tool_calls": [{"id": "native-call", "function": "view", "arguments": {"path": "status.txt", "line": 1}}],
    },
    {"role": "tool", "tool_call_id": "native-call", "function": "view", "content": "ready"},
    {"role": "assistant", "content": "The status is ready."},
]


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input: list[JsonValue]
    messages: list[dict[str, JsonValue]]
    external_ids: dict[str, str]


class WatcherHTTP(BaseModel):
    messages: list[dict[str, JsonValue]] = Field(default_factory=lambda: deepcopy(MESSAGES))
    requests: list[Snapshot] = Field(default_factory=list)
    is_visible: bool = True
    total: int = 1
    status_code: int = 200
    read_status_code: int = 200
    hidden_reads: int = 0
    trajectory_session_id: str = SESSION_ID
    is_hanging: bool = False

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if self.is_hanging:
            await asyncio.Event().wait()
        if self.status_code != 200:
            return httpx.Response(self.status_code, json={"detail": "Synthetic unavailable request"})
        if request.url.path == "/api/v1/hooks/pre-tool-use":
            self.requests.append(Snapshot.model_validate_json(request.content))
            return httpx.Response(200, json=[])
        if request.url.path == "/api/v1/sessions/search":
            if self.read_status_code != 200:
                return httpx.Response(self.read_status_code, json={"detail": "Synthetic unavailable readback"})
            if not self.is_visible or self.hidden_reads > 0:
                self.hidden_reads -= 1
                return httpx.Response(200, json={"sessions": [], "total": 0, "limit": 2, "offset": 0})
            return httpx.Response(
                200,
                json={
                    "sessions": [
                        {
                            "session_id": SESSION_ID,
                            "agent_platform": "other",
                            "trajectory_count": 1,
                            "message_count": len(self.messages),
                            "started_at": "2026-09-29T12:00:00Z",
                            "ended_at": "2026-09-29T12:00:01Z",
                            "latest_trajectory_id": "stored-trajectory",
                        }
                    ],
                    "total": self.total,
                    "limit": 2,
                    "offset": 0,
                },
            )
        assert request.url.path == f"/api/v1/sessions/{SESSION_ID}/trajectories/stored-trajectory"
        return httpx.Response(
            200,
            json={
                "trajectory_id": "stored-trajectory",
                "session_id": self.trajectory_session_id,
                "source": "watcher-hook",
                "messages": self.messages,
                "grades": [],
                "metadata": {},
                "created_at": "2026-09-29T12:00:01Z",
            },
        )


async def deliver(server: WatcherHTTP, timeout_seconds: float, messages: list[dict[str, JsonValue]] = MESSAGES) -> UUID:
    http = httpx.AsyncClient(base_url="http://watcher.test/api/", transport=httpx.MockTransport(server.handle))
    async with AsyncWatcherClient("http://watcher.test/api", httpx_client=http, max_retries=0) as client:
        return await record_messages(client, IDENTITY, messages, timeout_seconds=timeout_seconds)


def test_snapshot_is_confirmed_after_delayed_storage() -> None:
    server = WatcherHTTP(hidden_reads=1)
    assert asyncio.run(deliver(server, 2)) == UUID(SESSION_ID)
    assert server.requests == [Snapshot(input=[], messages=MESSAGES, external_ids={"other": IDENTITY})]


def test_server_enrichment_and_later_turn_do_not_prevent_replay() -> None:
    server = WatcherHTTP()
    server.messages[0]["id"] = "server-message"
    server.messages.extend([{"role": "user", "content": "Thanks."}, {"role": "assistant", "content": "Done."}])
    assert asyncio.run(deliver(server, 1)) == UUID(SESSION_ID)


def test_reasoning_and_freeform_tools_are_confirmed_despite_server_defaults() -> None:
    patch = "*** Begin Patch\n*** Update File: status.txt\n*** End Patch\n"
    reasoning: dict[str, JsonValue] = {
        "type": "reasoning",
        "reasoning": "",
        "summary": "Patch the file.",
        "redacted": True,
    }
    call: dict[str, JsonValue] = {
        "id": "custom_call",
        "function": "apply_patch",
        "arguments": {"input": patch},
        "type": "custom",
    }
    result: dict[str, JsonValue] = {
        "role": "tool",
        "tool_call_id": "custom_call",
        "function": "apply_patch",
        "content": "Modified",
    }
    sent: list[dict[str, JsonValue]] = [
        {"role": "user", "content": "Update the status."},
        {"role": "assistant", "content": [reasoning], "tool_calls": [call]},
        result,
    ]
    stored: list[dict[str, JsonValue]] = [
        {"role": "user", "content": "Update the status."},
        {
            "role": "assistant",
            "content": [{**reasoning, "signature": None, "internal": None}],
            "tool_calls": [{**call, "parse_error": None, "view": None}],
        },
        result,
    ]
    assert asyncio.run(deliver(WatcherHTTP(messages=stored), 1, sent)) == UUID(SESSION_ID)


@pytest.mark.parametrize("fault", ["final-text", "result-id", "result-content", "argument-type", "order", "truncation"])
def test_accepted_but_incorrect_history_is_never_confirmed(
    fault: Literal["final-text", "result-id", "result-content", "argument-type", "order", "truncation"],
) -> None:
    server = WatcherHTTP()
    if fault == "final-text":
        server.messages[-1]["content"] = "A different answer."
    elif fault == "result-id":
        server.messages[2]["tool_call_id"] = "unrelated-call"
    elif fault == "result-content":
        server.messages[2]["content"] = "failed"
    elif fault == "argument-type":
        server.messages[1]["tool_calls"] = [
            {"id": "native-call", "function": "view", "arguments": {"path": "status.txt", "line": True}}
        ]
    elif fault == "order":
        server.messages[1], server.messages[2] = server.messages[2], server.messages[1]
    else:
        server.messages.pop()
    with pytest.raises(TimeoutError):
        asyncio.run(deliver(server, 0.1))


def test_successful_hook_without_session_write_scope_is_not_delivery() -> None:
    with pytest.raises(TimeoutError):
        asyncio.run(deliver(WatcherHTTP(is_visible=False), 0.1))


@pytest.mark.parametrize("status_code", [401, 403, 503])
def test_rejected_requests_raise_without_confirmation(status_code: int) -> None:
    with pytest.raises(WatcherAPIError):
        asyncio.run(deliver(WatcherHTTP(status_code=status_code), 1))


@pytest.mark.parametrize("status_code", [403, 503])
def test_failed_readback_after_accepted_submission_is_not_confirmation(status_code: int) -> None:
    server = WatcherHTTP(read_status_code=status_code)
    with pytest.raises(WatcherAPIError):
        asyncio.run(deliver(server, 1))
    assert server.requests == [Snapshot(input=[], messages=MESSAGES, external_ids={"other": IDENTITY})]


def test_hung_service_respects_total_deadline() -> None:
    with pytest.raises(TimeoutError):
        asyncio.run(deliver(WatcherHTTP(is_hanging=True), 0.1))


def test_ambiguous_session_identity_is_refused() -> None:
    with pytest.raises(ValueError, match="multiple Watcher sessions"):
        asyncio.run(deliver(WatcherHTTP(total=2), 1))


def test_trajectory_from_another_session_is_refused() -> None:
    with pytest.raises(ValueError, match="another session"):
        asyncio.run(deliver(WatcherHTTP(trajectory_session_id="other"), 1))


def test_subagents_are_recorded_newest_first_and_a_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []

    async def fake_record(
        client: AsyncWatcherClient, identity: str, messages: list[dict[str, JsonValue]], *, timeout_seconds: float
    ) -> UUID:
        started.append(identity.rsplit(":", 1)[-1])
        if identity.endswith(":agent:broken"):
            raise TimeoutError
        return UUID(SESSION_ID)

    monkeypatch.setattr(recording, "record_messages", fake_record)
    session = ConvertedSession(
        MESSAGES,
        [SubagentHistory(name, [{"role": "assistant", "content": name}]) for name in ("oldest", "broken", "newest")],
    )

    async def run() -> None:
        async with AsyncWatcherClient("http://unused.test/api", max_retries=0) as client:
            await recording.record_session(client, UUID(SESSION_ID), session, timeout_seconds=5)

    with pytest.raises(recording.PartialRecordingError) as raised:
        asyncio.run(run())
    assert started == [SESSION_ID, "newest", "broken", "oldest"]
    assert raised.value.recorded.session == UUID(SESSION_ID)
    assert set(raised.value.recorded.subagents) == {"newest", "oldest"}
    assert "1 subagent histories were not" in str(raised.value)
