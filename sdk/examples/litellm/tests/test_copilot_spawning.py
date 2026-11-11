"""Check exact Copilot task correlation and immutable spawning relationships."""

import asyncio
import json
import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import asyncpg
import httpx
import pytest
from fastapi import HTTPException
from litellm.proxy._types import UserAPIKeyAuth
from pydantic import JsonValue, TypeAdapter
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send
from testcontainers.postgres import PostgresContainer
from watcher_litellm.copilot import CopilotGateway, current_request
from watcher_litellm.copilot_migrate import migrate
from watcher_litellm.copilot_sessions import Conversation, child_prompt_digest, register_task, spawning_calls
from watcher_litellm.replan import ToolCall, client_tool_details
from watcher_litellm.streams import API

from watcher_sdk import AsyncWatcherClient


def child_body(prompt: str, api: API = "responses") -> dict[str, JsonValue]:
    return {
        "input" if api == "responses" else "messages": [
            {"role": "system", "content": "system"},
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text" if api == "responses" else "text",
                        "text": "<current_datetime>2026-11-11T16:34:18.066+00:00</current_datetime>\n\n" + prompt,
                    }
                ],
            },
        ]
    }


def parent_calls(call_id: str, prompt: str, mode: str = "sync", api: API = "responses") -> list[ToolCall]:
    arguments: dict[str, JsonValue] = {"agent_type": "general-purpose", "mode": mode, "prompt": prompt}
    response: dict[str, JsonValue]
    if api == "responses":
        response = {
            "output": [
                {"type": "function_call", "name": "task", "call_id": call_id, "arguments": json.dumps(arguments)}
            ]
        }
    elif api == "messages":
        response = {"content": [{"type": "tool_use", "name": "task", "id": call_id, "input": arguments}]}
    else:
        response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "type": "function",
                                "id": call_id,
                                "function": {"name": "task", "arguments": json.dumps(arguments)},
                            }
                        ],
                    }
                }
            ]
        }
    return client_tool_details(api, response)


@pytest.mark.parametrize("mode", ["sync", "background"])
@pytest.mark.parametrize("api", ["responses", "messages", "chat_completions"])
def test_exact_child_prompt_matches_parent_task(mode: str, api: API) -> None:
    prompt = "Read the requested file.\nPreserve whitespace."
    calls = spawning_calls(parent_calls("call_spawn", prompt, mode, api))
    assert len(calls) == 1
    assert calls[0].tool_use_id == "call_spawn"
    assert calls[0].prompt_digest == child_prompt_digest(child_body(prompt, api))
    assert calls[0].prompt_digest != child_prompt_digest(child_body(prompt + " ", api))


@pytest.mark.parametrize(
    "content",
    [
        "Read the file",
        "<current_datetime>invalid</current_datetime>\n\nRead the file",
        "<current_datetime>2026-11-11T16:34:18+00:00</current_datetime>\nRead the file",
        "prefix<current_datetime>2026-11-11T16:34:18+00:00</current_datetime>\n\nRead the file",
    ],
)
def test_unknown_child_wrapper_has_no_digest(content: str) -> None:
    assert child_prompt_digest({"input": [{"role": "user", "content": content}]}) is None


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"input": "prompt"},
        {"input": [{"role": "system", "content": "x"}]},
        {"input": [{"role": "user", "content": [{"type": "input_image", "image_url": "x"}]}]},
    ],
)
def test_unknown_child_shape_has_no_digest(body: dict[str, JsonValue]) -> None:
    assert child_prompt_digest(body) is None


def test_non_task_or_malformed_parent_calls_are_not_candidates() -> None:
    assert spawning_calls([ToolCall(tool_use_id="other", tool_name="bash", tool_input={})]) == []
    assert spawning_calls([ToolCall(tool_use_id="spawn", tool_name="task", tool_input="broken")]) == []
    assert spawning_calls([ToolCall(tool_use_id="spawn", tool_name="task", tool_input={})]) == []
    assert spawning_calls([]) == []


def test_namespaced_task_is_not_a_builtin_spawning_call() -> None:
    calls = client_tool_details(
        "responses",
        {
            "output": [
                {
                    "type": "function_call",
                    "name": "task",
                    "namespace": "desk",
                    "call_id": "mcp",
                    "arguments": '{"prompt":"read"}',
                }
            ]
        },
    )
    assert spawning_calls(calls) == []


@pytest.mark.parametrize("api", ["responses", "messages", "chat_completions"])
def test_child_uses_only_its_initial_user_message(api: API) -> None:
    key = "input" if api == "responses" else "messages"
    body = child_body("read", api)
    items = body[key]
    assert isinstance(items, list)
    items.insert(1, {"role": "user", "content": "A different initial prompt"})
    assert child_prompt_digest(body) is None


@pytest.fixture(scope="module")
def postgres() -> Iterator[str]:
    with PostgresContainer("postgres:18.1", driver="asyncpg") as database:
        yield f"postgresql://{database.username}:{database.password}@{database.get_container_host_ip()}:{database.get_exposed_port(5432)}/{database.dbname}"


@pytest.fixture
async def database_url(postgres: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", postgres)
    connection = await asyncpg.connect(postgres)
    try:
        schema = Path(__file__).parents[1] / "src/watcher_litellm/copilot-schema.sql"
        await connection.execute(schema.read_text())
        await connection.execute(schema.read_text())
    finally:
        await connection.close()
    return postgres


@pytest.mark.requires_docker
@pytest.mark.parametrize("mode", ["sync", "background"])
@pytest.mark.parametrize("parent_api", ["responses", "messages", "chat_completions"])
@pytest.mark.parametrize("child_api", ["responses", "messages", "chat_completions"])
async def test_child_matches_across_connections_and_resume(
    database_url: str, mode: str, parent_api: API, child_api: API
) -> None:
    user = UserAPIKeyAuth(user_id="github:1", user_email="alice@example.test")
    session, parent_id, child_id = uuid4(), uuid4(), uuid4()
    parent = await register_task(user, session, parent_id, None)
    await parent.record_spawning_calls(parent_calls("spawn", "read file", mode, parent_api))
    child = await register_task(user, session, child_id, parent_id, child_body("read file", child_api))
    assert await child.spawning_tool_use_id() == "spawn"
    resumed = await register_task(user, session, child_id, parent_id, {})
    assert await resumed.spawning_tool_use_id() == "spawn"
    await parent.record_spawning_calls(parent_calls("later", "read file", mode, parent_api))
    assert await resumed.spawning_tool_use_id() == "spawn"
    second_child = await register_task(user, session, uuid4(), parent_id, child_body("read file", child_api))
    assert await second_child.spawning_tool_use_id() is None


@pytest.mark.requires_docker
async def test_ambiguous_unknown_and_different_parent_never_link(database_url: str) -> None:
    user = UserAPIKeyAuth(user_id="github:1", user_email="alice@example.test")
    session, parent_id = uuid4(), uuid4()
    parent = await register_task(user, session, parent_id, None)
    await parent.record_spawning_calls(parent_calls("a", "same"))
    await parent.record_spawning_calls(parent_calls("b", "same"))
    ambiguous = await register_task(user, session, uuid4(), parent_id, child_body("same"))
    unknown = await register_task(user, session, uuid4(), parent_id, child_body("unknown"))
    assert await ambiguous.spawning_tool_use_id() is None
    assert await unknown.spawning_tool_use_id() is None
    resumed_parent_id = uuid4()
    await register_task(user, session, resumed_parent_id, None)
    after_resume = await register_task(user, session, uuid4(), resumed_parent_id, child_body("same"))
    assert await after_resume.spawning_tool_use_id() is None
    new_parent = await register_task(user, session, resumed_parent_id, None)
    await new_parent.record_spawning_calls(parent_calls("new-spawn", "same"))
    assert await after_resume.spawning_tool_use_id() == "new-spawn"
    await parent.record_spawning_calls(parent_calls("a", "same"))
    assert await ambiguous.spawning_tool_use_id() is None


@pytest.mark.requires_docker
async def test_late_candidate_can_link_but_changed_call_is_refused(database_url: str) -> None:
    user = UserAPIKeyAuth(user_id="github:1", user_email="alice@example.test")
    session, parent_id = uuid4(), uuid4()
    parent = await register_task(user, session, parent_id, None)
    child = await register_task(user, session, uuid4(), parent_id, child_body("read"))
    assert await child.spawning_tool_use_id() is None
    await asyncio.gather(
        parent.record_spawning_calls(parent_calls("spawn", "read")),
        parent.record_spawning_calls(parent_calls("spawn", "read")),
    )
    assert await child.spawning_tool_use_id() == "spawn"
    with pytest.raises(HTTPException, match="spawning call changed"):
        await parent.record_spawning_calls(parent_calls("spawn", "different"))
    assert await child.spawning_tool_use_id() == "spawn"


@pytest.mark.requires_docker
@pytest.mark.parametrize("pending_hash", [None, ""])
async def test_relationship_retries_same_id_until_parent_message_exists(
    database_url: str, monkeypatch: pytest.MonkeyPatch, pending_hash: str | None
) -> None:
    user = UserAPIKeyAuth(user_id="github:1", user_email="alice@example.test")
    session, parent_task = uuid4(), uuid4()
    parent = await register_task(user, session, parent_task, None)
    await parent.record_spawning_calls(parent_calls("spawn", "read"))
    child = await register_task(user, session, uuid4(), parent_task, child_body("read"))
    parent_id, child_id = str(uuid4()), str(uuid4())
    relationships: list[dict[str, JsonValue]] = []

    async def no_delay(delay: float) -> None:
        return None

    def watcher(request: httpx.Request) -> httpx.Response:
        body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
        if request.method == "PUT":
            relationships.append(body)
            return httpx.Response(
                200,
                json={
                    "relationship_id": str(uuid4()),
                    "parent_session_id": parent_id,
                    "child_session_id": child_id,
                    "created_at": "2026-11-11T00:00:00Z",
                    "spawning_tool_use_id": body["spawning_tool_use_id"],
                    "spawning_message_trajectory_hash": "stored" if len(relationships) == 3 else pending_hash,
                },
            )
        is_child = child.external_id in request.content.decode()
        return httpx.Response(
            200,
            json={
                "sessions": [
                    {
                        "session_id": child_id if is_child else parent_id,
                        "agent_platform": "other",
                        "trajectory_count": 1,
                        "message_count": 1,
                        "started_at": "2026-11-11T00:00:00Z",
                        "ended_at": "2026-11-11T00:00:00Z",
                    }
                ],
                "total": 1,
                "limit": 2,
                "offset": 0,
            },
        )

    monkeypatch.setattr("watcher_litellm.copilot_sessions.asyncio.sleep", no_delay)
    http = httpx.AsyncClient(base_url="http://watcher", transport=httpx.MockTransport(watcher))
    async with AsyncWatcherClient("http://watcher", httpx_client=http) as client:
        await child.link(client)
    assert len(relationships) == 3
    assert all(body["spawning_tool_use_id"] == "spawn" for body in relationships)
    assert all(body["parent_session_id"] == parent_id for body in relationships)


@pytest.mark.requires_docker
async def test_missing_initial_wrapper_cannot_be_replaced_on_resume(database_url: str) -> None:
    user = UserAPIKeyAuth(user_id="github:1", user_email="alice@example.test")
    session, parent_id, child_id = uuid4(), uuid4(), uuid4()
    parent = await register_task(user, session, parent_id, None)
    await parent.record_spawning_calls(parent_calls("spawn", "read"))
    await register_task(user, session, child_id, parent_id, {})
    resumed = await register_task(user, session, child_id, parent_id, child_body("read"))
    assert await resumed.spawning_tool_use_id() is None


@pytest.mark.requires_docker
async def test_migration_keeps_old_replica_inserts_working(database_url: str) -> None:
    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute(
            "INSERT INTO watcher_copilot_tasks (root_id, task_id, external_id) VALUES ($1, $2, $3)",
            "old-root",
            uuid4(),
            "old-root-alias",
        )
        assert await connection.fetchval(
            "SELECT prompt_digest IS NULL AND spawning_tool_use_id IS NULL FROM watcher_copilot_tasks WHERE root_id=$1",
            "old-root",
        )
    finally:
        await connection.close()


@pytest.mark.requires_docker
@pytest.mark.parametrize("api", ["responses", "messages", "chat_completions"])
async def test_native_child_request_registers_its_prompt(database_url: str, api: API) -> None:
    user = UserAPIKeyAuth(user_id="github:1", user_email="alice@example.test")
    session, parent_id = uuid4(), uuid4()
    parent = await register_task(user, session, parent_id, None)
    await parent.record_spawning_calls(parent_calls("spawn", "read"))
    captured: list[str | None] = []

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        identity = current_request.get()
        assert identity is not None
        captured.append(await identity.conversation.spawning_tool_use_id())
        await JSONResponse({"ok": True})(scope, receive, send)

    def github(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": 1})

    async with httpx.AsyncClient(transport=httpx.MockTransport(github)) as github_client:
        gateway = CopilotGateway(downstream, {"1": "alice@example.test"}, github_client)
        async with httpx.AsyncClient(base_url="http://gateway", transport=httpx.ASGITransport(app=gateway)) as http:
            path = {
                "responses": "/copilot/responses",
                "messages": "/copilot/v1/messages",
                "chat_completions": "/copilot/chat/completions",
            }[api]
            response = await http.post(
                path,
                json={"model": "m", **child_body("read", api)},
                headers={
                    "authorization": "Bearer test",
                    "x-client-session-id": str(session),
                    "x-agent-task-id": str(uuid4()),
                    "x-parent-agent-id": str(parent_id),
                },
            )
    assert response.status_code == 200
    assert captured == ["spawn"]


@pytest.mark.parametrize("is_linked", [False, True])
async def test_link_timeout_only_succeeds_after_relationship_exists(
    is_linked: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent_id, child_id = str(uuid4()), str(uuid4())
    child = Conversation(external_id="child", parent_external_id="parent")

    async def spawning_id(self: Conversation) -> str:
        return "spawn"

    async def timeout(delay: float) -> None:
        raise TimeoutError

    def watcher(request: httpx.Request) -> httpx.Response:
        if not is_linked:
            raise TimeoutError
        if request.method == "PUT":
            return httpx.Response(
                200,
                json={
                    "relationship_id": str(uuid4()),
                    "parent_session_id": parent_id,
                    "child_session_id": child_id,
                    "created_at": "2026-11-11T00:00:00Z",
                    "spawning_tool_use_id": "spawn",
                    "spawning_message_trajectory_hash": None,
                },
            )
        return httpx.Response(
            200,
            json={
                "sessions": [
                    {
                        "session_id": child_id,
                        "agent_platform": "other",
                        "trajectory_count": 1,
                        "message_count": 1,
                        "started_at": "2026-11-11T00:00:00Z",
                        "ended_at": "2026-11-11T00:00:00Z",
                    }
                ],
                "total": 1,
                "limit": 2,
                "offset": 0,
            },
        )

    monkeypatch.setattr(Conversation, "spawning_tool_use_id", spawning_id)
    monkeypatch.setattr("watcher_litellm.copilot_sessions.asyncio.sleep", timeout)
    http = httpx.AsyncClient(base_url="http://watcher", transport=httpx.MockTransport(watcher))
    async with AsyncWatcherClient("http://watcher", httpx_client=http) as client:
        if is_linked:
            await child.link(client)
        else:
            with pytest.raises(TimeoutError):
                await child.link(client)


async def legacy_registration(parent: Conversation) -> None:
    connection = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        await connection.execute(
            """INSERT INTO watcher_copilot_tasks (root_id, task_id, parent_id, external_id)
            VALUES ($1, $2, NULL, $1)
            ON CONFLICT (root_id, task_id) DO UPDATE SET external_id=watcher_copilot_tasks.external_id
            WHERE watcher_copilot_tasks.parent_id IS NOT DISTINCT FROM EXCLUDED.parent_id
            RETURNING external_id""",
            parent.root_id,
            parent.task_id,
        )
    finally:
        await connection.close()


@pytest.mark.requires_docker
async def test_old_parent_response_cannot_match_a_different_recorded_call(database_url: str) -> None:
    user = UserAPIKeyAuth(user_id="github:1", user_email="alice@example.test")
    session, parent_id = uuid4(), uuid4()
    parent = await register_task(user, session, parent_id, None)
    await parent.record_spawning_calls(parent_calls("recorded-call", "same prompt"))
    known = await register_task(user, session, uuid4(), parent_id, child_body("same prompt"))
    assert await known.spawning_tool_use_id() == "recorded-call"
    await legacy_registration(parent)
    assert await known.spawning_tool_use_id() == "recorded-call"
    child = await register_task(user, session, uuid4(), parent_id, child_body("same prompt"))
    assert await child.spawning_tool_use_id() is None


@pytest.mark.requires_docker
async def test_old_registration_permanently_disables_parent_after_new_requests(database_url: str) -> None:
    user = UserAPIKeyAuth(user_id="github:1", user_email="alice@example.test")
    session, parent_id = uuid4(), uuid4()
    parent = await register_task(user, session, parent_id, None)
    await legacy_registration(parent)
    resumed = await register_task(user, session, parent_id, None)
    await resumed.record_spawning_calls(parent_calls("new-call", "old unrecorded prompt"))
    delayed = await register_task(user, session, uuid4(), parent_id, child_body("old unrecorded prompt"))
    assert await delayed.spawning_tool_use_id() is None


@pytest.mark.requires_docker
async def test_concurrent_old_and_new_registrations_disable_later_children(database_url: str) -> None:
    user = UserAPIKeyAuth(user_id="github:1", user_email="alice@example.test")
    session, parent_id = uuid4(), uuid4()
    parent = await register_task(user, session, parent_id, None)
    await parent.record_spawning_calls(parent_calls("recorded", "read"))
    await asyncio.gather(legacy_registration(parent), register_task(user, session, parent_id, None))
    await register_task(user, session, parent_id, None)
    child = await register_task(user, session, uuid4(), parent_id, child_body("read"))
    assert await child.spawning_tool_use_id() is None


@pytest.mark.requires_docker
async def test_parent_first_inserted_by_old_replica_never_enables_correlation(database_url: str) -> None:
    user = UserAPIKeyAuth(user_id="github:1", user_email="alice@example.test")
    session, old_parent_id = uuid4(), uuid4()
    root = await register_task(user, session, uuid4(), None)
    old_parent = Conversation(
        external_id=root.external_id, parent_external_id=None, root_id=root.root_id, task_id=old_parent_id
    )
    await legacy_registration(old_parent)
    parent = await register_task(user, session, old_parent_id, None)
    await parent.record_spawning_calls(parent_calls("new-call", "old prompt"))
    child = await register_task(user, session, uuid4(), old_parent_id, child_body("old prompt"))
    assert await child.spawning_tool_use_id() is None


@pytest.mark.requires_docker
async def test_migration_upgrades_legacy_rows_and_preserves_new_links(
    postgres: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    schema = "legacy_" + uuid4().hex
    legacy_url = postgres + "?search_path=" + schema
    monkeypatch.setenv("DATABASE_URL", legacy_url)
    admin = await asyncpg.connect(postgres)
    try:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        connection = await asyncpg.connect(legacy_url)
        try:
            await connection.execute(
                """CREATE TABLE watcher_copilot_tasks (
                    root_id text NOT NULL,
                    task_id uuid NOT NULL,
                    parent_id uuid,
                    external_id text NOT NULL,
                    PRIMARY KEY (root_id, task_id),
                    FOREIGN KEY (root_id, parent_id) REFERENCES watcher_copilot_tasks (root_id, task_id),
                    CHECK (parent_id IS DISTINCT FROM task_id)
                )"""
            )
            old_parent = Conversation(
                external_id="old-root", parent_external_id=None, root_id="old-root", task_id=uuid4()
            )
            await legacy_registration(old_parent)
            await connection.execute(
                "INSERT INTO watcher_copilot_tasks (root_id, task_id, parent_id, external_id) VALUES ($1, $2, $3, $4)",
                old_parent.root_id,
                uuid4(),
                old_parent.task_id,
                "old-child",
            )
        finally:
            await connection.close()

        await migrate()
        await legacy_registration(old_parent)
        user = UserAPIKeyAuth(user_id="github:1", user_email="alice@example.test")
        session, parent_id = uuid4(), uuid4()
        parent = await register_task(user, session, parent_id, None)
        await parent.record_spawning_calls(parent_calls("spawn", "read"))
        child = await register_task(user, session, uuid4(), parent_id, child_body("read"))
        assert await child.spawning_tool_use_id() == "spawn"

        await migrate()
        assert await child.spawning_tool_use_id() == "spawn"
        connection = await asyncpg.connect(legacy_url)
        try:
            records = await connection.fetch(
                "SELECT external_id, correlation_safe, prompt_digest, spawning_tool_use_id"
                " FROM watcher_copilot_tasks WHERE root_id='old-root' ORDER BY external_id"
            )
            assert [record["external_id"] for record in records] == ["old-child", "old-root"]
            assert all(not record["correlation_safe"] for record in records)
            assert all(record["prompt_digest"] is None and record["spawning_tool_use_id"] is None for record in records)
        finally:
            await connection.close()
    finally:
        await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.close()
