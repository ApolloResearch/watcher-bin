"""Native identity admission and durable task mapping, using real PostgreSQL."""

import asyncio
import gzip
import json
from collections.abc import AsyncIterator, Iterator, Mapping
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

import asyncpg
import httpx
import pytest
import yaml
import zstandard
from fastapi import HTTPException
from litellm.proxy._types import UserAPIKeyAuth
from starlette.requests import Request
from starlette.responses import JSONResponse
from structlog.testing import capture_logs
from testcontainers.community.postgres import PostgresContainer
from watcher_litellm import copilot, copilot_migrate
from watcher_litellm.copilot import CopilotGateway, authenticate, current_request, provider_callback
from watcher_litellm.copilot_sessions import Conversation, register_task

from watcher_sdk import AsyncWatcherClient


@pytest.fixture
async def github_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(github_response)) as github:
        yield github


async def forbidden_inference(scope, receive, send):
    pytest.fail("rejected request reached provider")


@pytest.mark.parametrize(
    ("body", "extra_headers", "status"),
    [
        (b"not-json", {}, 400),
        (b"[]", {}, 400),
        (b"{}", {}, 400),
        (b'{"model": 42}', {}, 400),
        (b'{"model": "m"}', {"x-client-session-id": "invalid"}, 400),
        (b'{"model": "m"}', {"x-agent-task-id": "invalid"}, 400),
        (b'{"model": "m"}', {"x-parent-agent-id": "invalid"}, 400),
        (b"broken", {"content-encoding": "gzip"}, 400),
        (gzip.compress(b'{"model": "m"}')[:-5], {"content-encoding": "gzip"}, 400),
        (b"broken", {"content-encoding": "zstd"}, 400),
        (b'{"model": "m"}', {"content-encoding": "br"}, 415),
    ],
)
async def test_invalid_native_body_is_rejected_before_inference(body, extra_headers, status):
    async with httpx.AsyncClient(transport=httpx.MockTransport(github_response)) as github:
        gateway = CopilotGateway(forbidden_inference, {"1": "alice@example.test"}, github)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://gateway") as client:
            response = await client.post("/copilot/responses", content=body, headers={**headers(), **extra_headers})
    assert response.status_code == status


async def test_deeply_nested_json_is_rejected_before_registration(github_client):
    depth = 100_000
    body = b'{"model":"m","input":' + b"[" * depth + b"0" + b"]" * depth + b"}"
    gateway = CopilotGateway(forbidden_inference, {"1": "alice@example.test"}, github_client)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://gateway") as client:
        response = await client.post("/copilot/responses", content=body, headers=headers())
    assert response.status_code == 400
    assert response.json() == {"error": "Invalid native Copilot request"}


@pytest.mark.parametrize("path", ["/copilot/responses", "/copilot/auto", "/copilot/meta", "/copilot/models"])
@pytest.mark.parametrize("encoding", ["identity", "gzip", "zstd"])
async def test_request_limit_applies_before_and_after_decompression(monkeypatch, encoding, path):
    monkeypatch.setattr(copilot, "_MAX_BODY", 100)
    body = b"x" * 101
    if encoding == "gzip":
        body = gzip.compress(body)
    elif encoding == "zstd":
        body = zstandard.ZstdCompressor().compress(body)
    async with httpx.AsyncClient(transport=httpx.MockTransport(github_response)) as github:
        gateway = CopilotGateway(forbidden_inference, {"1": "alice@example.test"}, github)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://gateway") as client:
            response = await client.request(
                "GET" if path in {"/copilot/meta", "/copilot/models"} else "POST",
                path,
                content=body,
                headers={**headers(), "content-encoding": encoding},
            )
    assert response.status_code == 413


@pytest.mark.parametrize("path", ["/copilot/responses", "/copilot/auto", "/copilot/meta", "/copilot/models"])
@pytest.mark.parametrize("authorization, status", [("", 401), ("Bearer invalid", 401)])
@pytest.mark.parametrize("encoding", ["identity", "gzip", "zstd"])
async def test_unverified_account_never_reads_or_decodes_the_body(path, authorization, status, encoding):
    async def request_body():
        pytest.fail("unverified account read its body before rejecting the account")
        yield b"unreachable"

    async with httpx.AsyncClient(transport=httpx.MockTransport(github_response)) as github:
        gateway = CopilotGateway(forbidden_inference, {"1": "alice@example.test"}, github)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://gateway") as client:
            response = await client.request(
                "GET" if path in {"/copilot/meta", "/copilot/models"} else "POST",
                path,
                content=request_body(),
                headers={**headers(), "authorization": authorization, "content-encoding": encoding},
            )
    assert response.status_code == status


@pytest.mark.parametrize("path", ["/copilot/responses", "/copilot/auto", "/copilot/meta", "/copilot/models"])
@pytest.mark.parametrize(
    "authorization", [b"Bearer \xe9abc", b"Bearer abc def", b"Bearer abc\tdef", b"Bearer abc\x00def"]
)
async def test_invalid_bearer_bytes_are_rejected_before_github(path, authorization):
    def forbidden_github(request):
        pytest.fail("invalid credential reached GitHub")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden_github)) as github:
        gateway = CopilotGateway(forbidden_inference, {"1": "alice@example.test"}, github)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://gateway") as client:
            response = await client.request(
                "GET" if path in {"/copilot/meta", "/copilot/models"} else "POST",
                path,
                headers=[(b"authorization", authorization)],
            )
    assert response.status_code == 401
    assert response.json() == {"error": "GitHub bearer credential required"}


@pytest.mark.parametrize("failure", ["403", "500", "missing-id", "non-json", "invalid-id", "network"])
async def test_github_failure_never_reaches_inference(failure):
    def github_response(request):
        if failure == "network":
            raise httpx.ConnectError("not reachable", request=request)
        if failure == "missing-id":
            return httpx.Response(200, json={})
        if failure == "invalid-id":
            return httpx.Response(200, json={"id": "1"})
        if failure == "non-json":
            return httpx.Response(200, text="upstream error alice-secret")
        return httpx.Response(int(failure))

    async with httpx.AsyncClient(transport=httpx.MockTransport(github_response)) as github:
        gateway = CopilotGateway(forbidden_inference, {"1": "alice@example.test"}, github)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://gateway") as client:
            response = await client.post("/copilot/responses", json={"model": "m"}, headers=headers())
    assert (
        response.status_code
        == {"403": 401, "500": 503, "missing-id": 503, "non-json": 503, "invalid-id": 503, "network": 503}[failure]
    )


async def test_unavailable_task_storage_fails_closed(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/unavailable")
    async with httpx.AsyncClient(transport=httpx.MockTransport(github_response)) as github:
        gateway = CopilotGateway(forbidden_inference, {"1": "alice@example.test"}, github)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://gateway") as client:
            response = await client.post("/copilot/responses", json={"model": "m"}, headers=headers())
    assert response.status_code == 503


async def test_missing_database_configuration_is_a_logged_server_error(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    async with httpx.AsyncClient(transport=httpx.MockTransport(github_response)) as github:
        gateway = CopilotGateway(forbidden_inference, {"1": "alice@example.test"}, github)
        with capture_logs() as logs:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=gateway), base_url="http://gateway"
            ) as client:
                response = await client.post("/copilot/responses", json={"model": "m"}, headers=headers())
    assert response.status_code == 503
    assert response.json() == {"error": "Copilot session storage unavailable"}
    assert logs == [{"event": "copilot_session_storage_unavailable", "error_type": "KeyError", "log_level": "warning"}]


async def test_postgres_connect_timeout_reports_storage_not_github(monkeypatch):
    writers = []

    def accept_without_reply(reader, writer):
        writers.append(writer)

    server = await asyncio.start_server(accept_without_reply, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    monkeypatch.setenv("DATABASE_URL", f"postgresql://test:test@127.0.0.1:{port}/unavailable?sslmode=disable")
    try:
        async with asyncio.timeout(15), httpx.AsyncClient(transport=httpx.MockTransport(github_response)) as github:
            gateway = CopilotGateway(forbidden_inference, {"1": "alice@example.test"}, github)
            with capture_logs() as logs:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=gateway), base_url="http://gateway"
                ) as client:
                    response = await client.post("/copilot/responses", json={"model": "m"}, headers=headers())
        assert response.status_code == 503
        assert response.json() == {"error": "Copilot session storage unavailable"}
        assert logs == [
            {"event": "copilot_session_storage_unavailable", "error_type": "TimeoutError", "log_level": "warning"}
        ]
    finally:
        server.close()
        for writer in writers:
            writer.close()
            await writer.wait_closed()
        await server.wait_closed()


@pytest.mark.parametrize("path", ["/copilot/meta", "/copilot/models", "/copilot/auto"])
async def test_chunked_discovery_body_is_bounded_before_forwarding(monkeypatch, path, github_client):
    monkeypatch.setattr(copilot, "_MAX_BODY", 100)

    async def chunks():
        yield b"a" * 60
        yield b"b" * 60

    gateway = CopilotGateway(forbidden_inference, {"1": "alice@example.test"}, github_client)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://gateway") as client:
        response = await client.request(
            "POST" if path.endswith("auto") else "GET",
            path,
            content=chunks(),
            headers=headers(),
        )
    assert response.status_code == 413


@pytest.mark.parametrize("path", ["/copilot/meta", "/copilot/models"])
async def test_get_discovery_refuses_a_request_body(path, github_client):
    gateway = CopilotGateway(forbidden_inference, {"1": "alice@example.test"}, github_client)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://gateway") as client:
        response = await client.request("GET", path, content=b"{}", headers=headers())
    assert response.status_code == 400


@pytest.mark.parametrize("encoding", ["identity", "gzip", "zstd"])
async def test_auto_forwards_only_the_decoded_bounded_body(encoding, github_client):
    payload = b'{"model": "auto"}'
    body = payload
    if encoding == "gzip":
        body = gzip.compress(payload)
    elif encoding == "zstd":
        body = zstandard.ZstdCompressor().compress(payload)

    async def downstream(scope, receive, send):
        request = Request(scope, receive)
        assert await request.body() == payload
        assert request.headers["content-length"] == str(len(payload))
        assert "content-encoding" not in request.headers
        await JSONResponse({"ok": True})(scope, receive, send)

    gateway = CopilotGateway(downstream, {"1": "alice@example.test"}, github_client)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://gateway") as client:
        response = await client.post("/copilot/auto", content=body, headers={**headers(), "content-encoding": encoding})
    assert response.status_code == 200


@pytest.mark.requires_docker
async def test_runtime_github_client_verifies_against_fixed_host(monkeypatch, database_url):
    def verified_host(request):
        assert str(request.url) == "https://api.github.com/user"
        return github_response(request)

    github = httpx.AsyncClient(transport=httpx.MockTransport(verified_host))

    def github_client(*, timeout):
        assert timeout == 20
        return github

    async def downstream(scope, receive, send):
        user = await authenticate(Request(scope, receive), "")
        await JSONResponse({"email": user.user_email})(scope, receive, send)

    gateway = CopilotGateway(downstream, {"1": "alice@example.test"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://gateway") as client:
        monkeypatch.setattr(copilot.httpx, "AsyncClient", github_client)
        response = await client.post("/copilot/responses", json={"model": "m"}, headers=headers())
    assert response.json() == {"email": "alice@example.test"}


@pytest.mark.parametrize(
    "path",
    ["/copilot/meta", "/copilot/auto", "/copilot/responses", "/copilot/v1/messages", "/copilot/chat/completions"],
)
async def test_wrong_native_method_is_rejected(path):
    gateway = CopilotGateway(forbidden_inference, {"1": "alice@example.test"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://gateway") as client:
        response = await client.put(path, headers=headers())
    assert response.status_code == 405


async def test_master_key_cannot_open_non_native_inference():
    request = Request({"type": "http", "path": "/responses", "headers": []})
    with pytest.raises(HTTPException, match="native Copilot"):
        await authenticate(request, "master-key")


async def test_gateway_health_lifespan_and_websocket_policy():
    called = []

    async def downstream(scope, receive, send):
        called.append(scope["type"])
        if scope["type"] == "http":
            await authenticate(Request(scope, receive), "")
            await JSONResponse({"ok": True})(scope, receive, send)

    gateway = CopilotGateway(downstream, {"1": "alice@example.test"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://gateway") as client:
        assert (await client.get("/health/readiness")).status_code == 200

    async def receive():
        pytest.fail("unexpected receive")

    messages = []

    async def send(message):
        messages.append(message)

    await gateway({"type": "lifespan"}, receive, send)
    await gateway({"type": "websocket"}, receive, send)
    assert called == ["http", "lifespan"]
    assert messages == [{"type": "websocket.close", "code": 1008}]


def test_operator_mapping_must_use_github_ids_and_valid_emails():
    with pytest.raises(ValueError, match="numeric"):
        CopilotGateway(forbidden_inference, {"alice": "alice@example.test"})
    with pytest.raises(HTTPException):
        CopilotGateway(forbidden_inference, {"1": "invalid-email"})


def native_identity(provider_headers: dict[str, str]) -> copilot.NativeRequest:
    return copilot.NativeRequest(
        user_id="github:1",
        user_email="alice@example.test",
        conversation=Conversation(external_id="root", parent_external_id=None),
        provider_session=copilot.GithubCopilotUserSession(token="private", api_base="https://api.githubcopilot.com"),
        provider_headers=provider_headers,
    )


async def test_credentials_are_only_supplied_to_copilot_provider():
    kwargs = {"custom_llm_provider": "openai"}
    assert await provider_callback.async_pre_call_deployment_hook(kwargs) is kwargs
    reset = current_request.set(native_identity({}))
    try:
        for refused in (
            kwargs,
            {"model": "openai/gpt-6-luna"},
            {"custom_llm_provider": "openai", "model": "github_copilot/m"},
        ):
            with pytest.raises(HTTPException, match="GitHub Copilot provider"):
                await provider_callback.async_pre_call_deployment_hook(refused)
            assert "github_copilot_user_session" not in refused
        chat = await provider_callback.async_pre_call_deployment_hook({"model": "github_copilot/gemini-3.8-flash"})
    finally:
        current_request.reset(reset)
    assert chat["github_copilot_user_session"].token == "private"


def test_packaged_model_list_keeps_copilot_routing_rules():
    entries = yaml.safe_load(files("watcher_litellm").joinpath("copilot.yaml").read_text())["model_list"]
    for entry in entries:
        name, params = entry["model_name"], entry["litellm_params"]
        assert params["model"].startswith("github_copilot/")
        assert params["litellm_credential_name"] == "native-copilot"
        assert params["github_copilot_auth_type"] == "per_user_oauth"
        if name.startswith(("gpt", "grok", "mai")):
            assert entry["model_info"]["mode"] == "responses"
        if name.startswith("gemini"):
            assert "reasoning_effort" in params["allowed_openai_params"]
    names = {entry["model_name"] for entry in entries}
    # GPT falls back to its family route; Claude and Gemini use only family routes.
    assert {name for name in names if "*" in name} == {"gpt-*", "claude-*", "gemini-*"}
    assert "gpt-6-luna" in names, "Auto and Copilot's explore subagent use gpt-6-luna"


TOOL_USE_TURN = [
    {"role": "user", "content": "list files"},
    {"role": "assistant", "content": [{"type": "tool_use", "id": "t", "name": "bash", "input": {"command": "ls"}}]},
]
TOOL_RESULT = {"type": "tool_result", "tool_use_id": "t", "content": "denied", "is_error": True}


@pytest.mark.parametrize(
    ("client_headers", "messages", "initiator"),
    [
        ({"x-initiator": "user"}, [{"role": "user", "content": [{"type": "text", "text": "hi"}]}], "user"),
        (
            {"x-initiator": "user"},
            [*TOOL_USE_TURN, {"role": "user", "content": [TOOL_RESULT, {"type": "text", "text": "and"}]}],
            "user",
        ),
        ({"x-initiator": "user"}, [*TOOL_USE_TURN, {"role": "user", "content": [TOOL_RESULT]}], "agent"),
        ({}, [*TOOL_USE_TURN, {"role": "user", "content": [TOOL_RESULT]}], None),
    ],
)
async def test_tool_result_continuations_are_sent_as_agent_initiated(
    client_headers: dict[str, str], messages: list[dict[str, object]], initiator: str | None
) -> None:
    identity = native_identity(dict(client_headers))
    reset = current_request.set(identity)
    try:
        provider = await provider_callback.async_pre_call_deployment_hook(
            {"custom_llm_provider": "github_copilot", "messages": messages}
        )
    finally:
        current_request.reset(reset)
    assert provider["extra_headers"].get("x-initiator") == initiator
    assert identity.provider_headers == client_headers


@pytest.mark.requires_docker
def test_native_config_and_separate_migration_commands(postgres, monkeypatch, capsys):
    from watcher_litellm.config import copilot_main

    monkeypatch.setenv("DATABASE_URL", postgres)
    copilot_migrate.main()
    copilot_migrate.main()  # Upgrade jobs can safely be retried.
    copilot_main()
    emitted = capsys.readouterr().out
    assert "watcher_litellm.copilot.authenticate" in emitted
    assert "watcher_litellm.callback.watcher_callback" in emitted
    for route in ("/copilot/responses", "/copilot/v1/messages", "/copilot/chat/completions"):
        assert route not in emitted  # Inference cannot be a pass-through.


async def test_native_entry_point_loads_operator_configuration(tmp_path, monkeypatch):
    users = tmp_path / "users.yaml"
    monkeypatch.setenv("WATCHER_AUTH_MODE", "api_key")
    copilot._gateway.cache_clear()
    with pytest.raises(ValueError, match="WATCHER_AUTH_MODE"):
        copilot._gateway()
    monkeypatch.setenv("WATCHER_AUTH_MODE", "proxy")
    monkeypatch.setenv("WATCHER_COPILOT_USERS_FILE", str(users))
    users.write_text("[]")
    with pytest.raises(ValueError, match="ID-to-email mapping"):
        copilot._gateway()
    users.write_text("1: alice@example.test\n")
    with pytest.raises(ValueError, match="quoted numeric"):
        copilot._gateway()
    users.write_text("'1': alice@example.test\n")
    try:
        messages = []

        async def receive():
            pytest.fail("websocket must be refused before receiving")

        async def send(message):
            messages.append(message)

        await copilot.app({"type": "websocket"}, receive, send)
        assert messages == [{"type": "websocket.close", "code": 1008}]
    finally:
        copilot._gateway.cache_clear()


@pytest.mark.parametrize("contents", [None, "{}"])
def test_native_entry_point_allows_no_email_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contents: str | None
) -> None:
    monkeypatch.setenv("WATCHER_AUTH_MODE", "proxy")
    if contents is None:
        monkeypatch.delenv("WATCHER_COPILOT_USERS_FILE", raising=False)
    else:
        users = tmp_path / "users.yaml"
        users.write_text(contents)
        monkeypatch.setenv("WATCHER_COPILOT_USERS_FILE", str(users))
    copilot._gateway.cache_clear()
    try:
        assert copilot._gateway().users == {}
    finally:
        copilot._gateway.cache_clear()


@pytest.fixture(scope="module")
def postgres() -> Iterator[str]:
    with PostgresContainer("postgres:18.1", driver="asyncpg") as database:
        yield f"postgresql://{database.username}:{database.password}@{database.get_container_host_ip()}:{database.get_exposed_port(5432)}/{database.dbname}"


@pytest.fixture
async def database_url(postgres: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", postgres)
    connection = await asyncpg.connect(postgres)
    try:
        sql = Path(__file__).parents[1] / "src/watcher_litellm/copilot-schema.sql"
        await connection.execute(sql.read_text())
    finally:
        await connection.close()
    return postgres


@pytest.mark.requires_docker
async def test_roots_resume_and_children_keep_distinct_durable_identities(database_url: str) -> None:
    user = UserAPIKeyAuth(user_id="github:1", user_email="alice@example.test")
    root_id, root_task, child_task = uuid4(), uuid4(), uuid4()
    root = await register_task(user, root_id, root_task, None)
    child = await register_task(user, root_id, child_task, root_task)
    # Each call opens a new connection, as independent replicas would.
    resumed = await register_task(user, root_id, uuid4(), None)
    repeated_child = await register_task(user, root_id, child_task, root_task)
    sibling = await register_task(user, root_id, uuid4(), root_task)
    other_user = await register_task(
        UserAPIKeyAuth(user_id="github:2", user_email="bob@example.test"), root_id, root_task, None
    )
    assert root.external_id == resumed.external_id
    assert child == repeated_child
    assert child.parent_external_id == root.external_id
    assert sibling.parent_external_id == root.external_id
    assert len({root.external_id, child.external_id, sibling.external_id, other_user.external_id}) == 4


@pytest.mark.requires_docker
async def test_ancestry_cannot_be_replaced_or_claimed_across_accounts(database_url: str) -> None:
    user = UserAPIKeyAuth(user_id="github:1", user_email="alice@example.test")
    root_id, root_task, child_task = uuid4(), uuid4(), uuid4()
    await register_task(user, root_id, root_task, None)
    await register_task(user, root_id, child_task, root_task)
    with pytest.raises(HTTPException, match="ancestry changed"):
        await register_task(user, root_id, child_task, None)
    with pytest.raises(HTTPException, match="parent task is unknown"):
        await register_task(
            UserAPIKeyAuth(user_id="github:2", user_email="bob@example.test"), root_id, uuid4(), root_task
        )


@pytest.mark.requires_docker
async def test_concurrent_replicas_register_the_same_task_idempotently(database_url: str) -> None:
    user = UserAPIKeyAuth(user_id="github:1", user_email="alice@example.test")
    root, task = uuid4(), uuid4()
    first, second = await asyncio.gather(register_task(user, root, task, None), register_task(user, root, task, None))
    assert first == second


def github_response(request: httpx.Request) -> httpx.Response:
    if request.headers.get("authorization") == "Bearer alice-secret":
        return httpx.Response(200, json={"id": 1, "login": "ignored", "email": "untrusted@example.test"})
    if request.headers.get("authorization") == "Bearer unmapped-secret":
        return httpx.Response(200, json={"id": 99})
    return httpx.Response(401)


def headers() -> dict[str, str]:
    return {
        "authorization": "Bearer alice-secret",
        "x-client-session-id": str(uuid4()),
        "x-agent-task-id": str(uuid4()),
        "copilot-session-token": "selection-secret",
        "x-forwarded-user": "forged@example.test",
        "x-auth-proxy-token": "forged-token",
    }


BASH_SCHEMA = {"type": "object", "properties": {"command": {"type": "string"}}}
# Native path, LiteLLM route, a request in the shape native Copilot sends, and the
# format-specific client headers that must reach GitHub.
NATIVE_FORMATS = [
    (
        "/copilot/responses",
        "/responses",
        {
            "model": "gpt-6-luna",
            "input": [
                {"role": "user", "content": "hi"},
                # A provider-run search Copilot echoes back, with the client tools it loaded.
                {
                    "type": "tool_search_output",
                    "execution": "server",
                    "status": "completed",
                    "tools": [
                        {
                            "type": "namespace",
                            "name": "pizza",
                            "tools": [
                                {"type": "function", "name": "pizza-list_menu", "defer_loading": True},
                                {"type": "custom", "name": "pizza-edit", "format": {"type": "text"}},
                            ],
                        }
                    ],
                },
            ],
            "tools": [
                {"type": "function", "name": "bash", "parameters": BASH_SCHEMA},
                {"type": "custom", "name": "apply_patch", "format": {"type": "text"}},
                # Deferred MCP tools and the search that loads them, as Copilot sends them.
                {
                    "type": "namespace",
                    "name": "pizza",
                    "tools": [
                        {"type": "function", "name": "pizza-list_menu", "defer_loading": True},
                        {"type": "custom", "name": "pizza-edit", "format": {"type": "text"}},
                    ],
                },
                {"type": "tool_search"},
            ],
        },
        set(),
    ),
    (
        "/copilot/v1/messages",
        "/v1/messages",
        {
            "model": "claude-sonnet-5.5",
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [
                {"name": "bash", "input_schema": BASH_SCHEMA},
                {"type": "custom", "name": "view", "input_schema": {}},
            ],
            "thinking": {"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}},
        },
        {"anthropic-beta", "x-initiator"},
    ),
    (
        "/copilot/chat/completions",
        "/chat/completions",
        {
            "model": "gemini-3.8-flash",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [{"type": "function", "function": {"name": "bash", "parameters": BASH_SCHEMA}}],
            "reasoning_effort": "low",
            "snippy": {"enabled": False},
        },
        set(),
    ),
]


@pytest.mark.parametrize(
    ("path", "target", "native_body", "format_headers", "encoding"),
    [(*NATIVE_FORMATS[0], encoding) for encoding in ("identity", "gzip", "zstd")]
    + [(*native_format, "identity") for native_format in NATIVE_FORMATS[1:]],
)
@pytest.mark.requires_docker
@pytest.mark.parametrize(
    ("users", "expected_email"),
    [({"1": "alice@example.test"}, "alice@example.test"), ({}, None), ({"99": "bob@example.test"}, None)],
)
async def test_native_request_supplies_verified_identity_and_private_credentials(
    database_url: str,
    encoding: str,
    path: str,
    target: str,
    native_body: dict,
    format_headers: set[str],
    users: dict[str, str],
    expected_email: str | None,
) -> None:
    captured = []

    async def downstream(scope, receive, send):
        request = Request(scope, receive)
        user = await authenticate(request, "")
        identity = current_request.get()
        assert identity is not None
        assert user.user_id == "github:1"
        provider = await provider_callback.async_pre_call_deployment_hook({"custom_llm_provider": "github_copilot"})
        captured.append(
            {
                "path": scope["path"],
                "raw_path": scope["raw_path"],
                "email": user.user_email,
                "headers": dict(request.headers),
                "body": await request.json(),
                "repr": repr(identity),
                "dump": identity.model_dump(),
                "provider": provider,
            }
        )
        await JSONResponse({"ok": True})(scope, receive, send)

    async with httpx.AsyncClient(transport=httpx.MockTransport(github_response)) as github:
        app = CopilotGateway(downstream, users, github)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway") as client:
            body = json.dumps({**native_body, "metadata": {"user": "forged"}}).encode()
            if encoding == "gzip":
                body = gzip.compress(body)
            elif encoding == "zstd":
                body = zstandard.ZstdCompressor().compress(body)
            response = await client.post(
                path,
                content=body,
                headers={
                    **headers(),
                    "content-encoding": encoding,
                    "user-agent": "copilot/1.0.109 (linux)",
                    "anthropic-version": "2099-01-01",
                    "anthropic-beta": "thinking-binding-controls-2026-08-01",
                    "x-initiator": "agent",
                },
            )
    assert response.status_code == 200
    assert (captured[0]["path"], captured[0]["raw_path"]) == (target, target.encode())
    assert captured[0]["email"] == expected_email
    assert captured[0]["body"] == native_body
    assert set(captured[0]["headers"]) == {"content-type", "content-length", "user-agent"}
    forwarded = set(captured[0]["provider"]["extra_headers"])
    assert forwarded & {"anthropic-version", "anthropic-beta", "x-initiator"} == format_headers
    assert captured[0]["headers"]["user-agent"] == "copilot/1.0.109 (linux)"
    assert "secret" not in captured[0]["repr"]
    assert "secret" not in json.dumps(captured[0]["dump"])
    assert captured[0]["provider"]["github_copilot_user_session"].token == "alice-secret"
    assert captured[0]["provider"]["extra_headers"]["copilot-session-token"] == "selection-secret"
    assert current_request.get() is None


@pytest.mark.parametrize(
    ("authorization", "path", "extra_body", "status"),
    [
        ("Bearer invalid", "/copilot/responses", {}, 401),
        ("", "/copilot/responses", {}, 401),
        ("Bearer alice-secret", "/responses", {}, 404),
        ("Bearer alice-secret", "/v1/responses", {}, 404),
        ("Bearer alice-secret", "/chat/completions", {}, 404),
        ("Bearer alice-secret", "/copilot/responses", {"api_base": "https://attacker.invalid"}, 400),
        ("Bearer alice-secret", "/copilot/responses", {"extra_headers": {"Authorization": "forged"}}, 400),
        ("Bearer alice-secret", "/copilot/responses", {"litellm_metadata": {}}, 400),
    ],
)
async def test_untrusted_requests_never_reach_inference(
    authorization: str, path: str, extra_body: dict, status: int
) -> None:
    async def forbidden(scope, receive, send):
        pytest.fail("rejected request reached provider")

    async with httpx.AsyncClient(transport=httpx.MockTransport(github_response)) as github:
        app = CopilotGateway(forbidden, {"1": "alice@example.test"}, github)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway") as client:
            response = await client.post(
                path,
                json={"model": "gpt-6-luna", "input": "hi", **extra_body},
                headers={**headers(), "authorization": authorization},
            )
    assert response.status_code == status


UNSUPPORTED_FIELDS = "Unsupported native request fields: "
UNSUPPORTED_TOOLS = "Unsupported native tool types: "
UNSUPPORTED_MODEL = "Unsupported native model name"
HOSTED_NAMESPACE = {"type": "namespace", "name": "x", "tools": [{"type": "web_search"}]}


def loaded_tools(tool: Mapping[str, object]) -> dict[str, object]:
    return {"type": "tool_search_output", "execution": "server", "status": "completed", "tools": [tool]}


@pytest.mark.parametrize(
    ("path", "extra_body", "error"),
    [
        # Another format's fields, LiteLLM routing overrides and options the callback cannot gate.
        ("/copilot/v1/messages", {"input": "hi"}, UNSUPPORTED_FIELDS + "input"),
        ("/copilot/v1/messages", {"api_base": "https://attacker.invalid"}, UNSUPPORTED_FIELDS + "api_base"),
        (
            "/copilot/v1/messages",
            {"mcp_servers": [{"type": "url", "url": "https://mcp.invalid", "name": "x"}]},
            UNSUPPORTED_FIELDS + "mcp_servers",
        ),
        ("/copilot/v1/messages", {"context_management": {"edits": []}}, UNSUPPORTED_FIELDS + "context_management"),
        ("/copilot/chat/completions", {"input": "hi"}, UNSUPPORTED_FIELDS + "input"),
        (
            "/copilot/chat/completions",
            {"extra_headers": {"authorization": "forged"}, "api_key": "forged"},
            UNSUPPORTED_FIELDS + "api_key, extra_headers",
        ),
        (
            "/copilot/chat/completions",
            {"allowed_openai_params": ["anything"]},
            UNSUPPORTED_FIELDS + "allowed_openai_params",
        ),
        (
            "/copilot/chat/completions",
            {"functions": [{"name": "bash", "parameters": {}}]},
            UNSUPPORTED_FIELDS + "functions",
        ),
        ("/copilot/chat/completions", {"n": 2}, UNSUPPORTED_FIELDS + "n"),
        ("/copilot/responses", {"messages": []}, UNSUPPORTED_FIELDS + "messages"),
        # Comma lists, control characters and provider prefixes are not plain model names.
        ("/copilot/chat/completions", {"model": "m,m"}, UNSUPPORTED_MODEL),
        ("/copilot/v1/messages", {"model": "claude-test\nX"}, UNSUPPORTED_MODEL),
        ("/copilot/responses", {"model": "openai/gpt-6-luna"}, UNSUPPORTED_MODEL),
        # Provider-hosted, ungated or malformed tools.
        (
            "/copilot/v1/messages",
            {"tools": [{"type": "web_search_20250305", "name": "web_search"}]},
            UNSUPPORTED_TOOLS + "web_search_20250305",
        ),
        ("/copilot/v1/messages", {"tools": ["bash"]}, UNSUPPORTED_TOOLS + "str"),
        ("/copilot/v1/messages", {"tools": [{"type": ["custom"], "name": "x"}]}, UNSUPPORTED_TOOLS + "list"),
        ("/copilot/v1/messages", {"tools": [{"type": {"a": 1}, "name": "x"}]}, UNSUPPORTED_TOOLS + "dict"),
        (
            "/copilot/chat/completions",
            {"tools": [{"type": "custom", "custom": {"name": "bash"}}]},
            UNSUPPORTED_TOOLS + "custom",
        ),
        ("/copilot/chat/completions", {"tools": {"type": "function"}}, "Native tools must be a list"),
        ("/copilot/chat/completions", {"tools": [{"function": {"name": "bash"}}]}, UNSUPPORTED_TOOLS + "untyped"),
        ("/copilot/chat/completions", {"tools": [{"type": ["function"]}]}, UNSUPPORTED_TOOLS + "list"),
        (
            "/copilot/responses",
            {"tools": [{"type": "mcp", "server_label": "x", "server_url": "litellm_proxy"}]},
            UNSUPPORTED_TOOLS + "mcp",
        ),
        ("/copilot/responses", {"tools": [{"type": "web_search"}]}, UNSUPPORTED_TOOLS + "web_search"),
        ("/copilot/responses", {"tools": [{"name": "bash"}]}, UNSUPPORTED_TOOLS + "untyped"),
        ("/copilot/responses", {"tools": [{"type": []}]}, UNSUPPORTED_TOOLS + "list"),
        # A namespace may group only client tools, and tool search exists only on Responses.
        ("/copilot/responses", {"tools": [HOSTED_NAMESPACE]}, UNSUPPORTED_TOOLS + "namespace.web_search"),
        ("/copilot/responses", {"tools": [{"type": "namespace", "name": "x"}]}, UNSUPPORTED_TOOLS + "namespace"),
        ("/copilot/chat/completions", {"tools": [{"type": "tool_search"}]}, UNSUPPORTED_TOOLS + "tool_search"),
        ("/copilot/v1/messages", {"tools": [HOSTED_NAMESPACE]}, UNSUPPORTED_TOOLS + "namespace"),
        (
            "/copilot/responses",
            {"tools": [{"type": "namespace", "name": "desk", "tools": "invalid"}]},
            UNSUPPORTED_TOOLS + "namespace",
        ),
        (
            "/copilot/responses",
            {"tools": [{"type": "namespace", "name": "desk", "tools": [{"type": ["function"]}]}]},
            UNSUPPORTED_TOOLS + "namespace.list",
        ),
        ("/copilot/v1/messages", {"tools": [{"type": "tool_search"}]}, UNSUPPORTED_TOOLS + "tool_search"),
        ("/copilot/chat/completions", {"tools": [{"type": "namespace", "tools": []}]}, UNSUPPORTED_TOOLS + "namespace"),
        # A tool search output in the input may load only client tools.
        (
            "/copilot/responses",
            {"input": [loaded_tools({"type": "mcp", "server_label": "x", "server_url": "litellm_proxy"})]},
            UNSUPPORTED_TOOLS + "input.mcp",
        ),
        (
            "/copilot/responses",
            {"input": [loaded_tools({"type": "web_search"})]},
            UNSUPPORTED_TOOLS + "input.web_search",
        ),
        (
            "/copilot/responses",
            {"input": [loaded_tools(HOSTED_NAMESPACE)]},
            UNSUPPORTED_TOOLS + "input.namespace.web_search",
        ),
        (
            "/copilot/responses",
            {"input": [{"type": "tool_search_output", "execution": "server", "tools": {"type": "function"}}]},
            UNSUPPORTED_TOOLS + "input.tool_search_output",
        ),
    ],
)
async def test_each_format_accepts_only_its_own_fields_and_client_tools(path, extra_body, error, github_client):
    gateway = CopilotGateway(forbidden_inference, {"1": "alice@example.test"}, github_client)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://gateway") as client:
        response = await client.post(path, json={"model": "m", **extra_body}, headers=headers())
    assert response.status_code == 400
    assert response.json() == {"error": error}


async def test_refusals_log_only_fixed_reasons_and_counts(github_client):
    gateway = CopilotGateway(forbidden_inference, {"1": "alice@example.test"}, github_client)
    long_name = "x" * 200
    with capture_logs() as logs:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://gateway") as client:
            fields = await client.post(
                "/copilot/responses",
                json={"model": "m", "api_base": "https://secret.invalid", long_name: 1},
                headers=headers(),
            )
            header = await client.post(
                "/copilot/responses", json={"model": "m"}, headers={**headers(), "x-agent-task-id": "secret-value"}
            )
    assert fields.status_code == header.status_code == 400
    assert header.json() == {"error": "Invalid native Copilot header: x-agent-task-id"}
    refused = [entry for entry in logs if entry["event"] == "copilot_request_refused"]
    assert [entry["rejected_count"] for entry in refused] == [2, 1]
    assert all("names" not in entry for entry in refused)
    assert long_name[:64] not in json.dumps(refused)
    assert "secret" not in json.dumps(refused)


@pytest.mark.parametrize("path", ["/copilot/meta", "/copilot/models", "/copilot/auto"])
async def test_discovery_uses_stock_routes_without_gateway_identity_headers(
    path: str, github_client: httpx.AsyncClient
) -> None:
    async def downstream(scope, receive, send):
        request = Request(scope, receive)
        await authenticate(request, "")
        assert request.headers["authorization"] == "Bearer alice-secret"
        assert "x-forwarded-user" not in request.headers
        assert "x-auth-proxy-token" not in request.headers
        await JSONResponse({"path": request.url.path})(scope, receive, send)

    app = CopilotGateway(downstream, {"1": "alice@example.test"}, github_client)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway") as client:
        response = await client.request("POST" if path.endswith("auto") else "GET", path, headers=headers())
    assert response.status_code == 200
    assert response.json() == {"path": path}


@pytest.mark.parametrize("is_child", [False, True])
@pytest.mark.parametrize("email", ["alice@example.test", None])
async def test_callback_carries_native_parent_without_extra_requests(monkeypatch, is_child, email):
    from watcher_litellm.callback import WatcherCallback

    captures = []

    def watcher(request):
        assert request.url.path.endswith("pre-tool-use")
        captures.append(json.loads(request.content))
        return httpx.Response(200, json=[])

    monkeypatch.setenv("WATCHER_AUTH_MODE", "proxy")
    identity = copilot.NativeRequest(
        user_id="github:1",
        user_email=email,
        conversation=Conversation(
            external_id="native-child" if is_child else "native-root",
            parent_external_id="native-root" if is_child else None,
        ),
        provider_session=copilot.GithubCopilotUserSession(token="private", api_base="https://api.githubcopilot.com"),
        provider_headers={},
    )
    reset = current_request.set(identity)

    def watcher_client():
        transport = httpx.AsyncClient(base_url="http://watcher", transport=httpx.MockTransport(watcher))
        return AsyncWatcherClient("http://watcher", httpx_client=transport)

    try:
        response = {"id": "r", "output": []}
        assert (
            await WatcherCallback(watcher_client).async_post_call_success_hook(
                {
                    "model": "m",
                    "proxy_server_request": {
                        "url": "http://gateway/responses",
                        "headers": {},
                        "body": {"model": "m", "input": "hello"},
                    },
                },
                UserAPIKeyAuth(user_id=identity.user_id, user_email=identity.user_email),
                response,
            )
            is response
        )
    finally:
        current_request.reset(reset)
    (body,) = captures
    assert body["conversation"] == {"namespace": "other", "id": "native-child" if is_child else "native-root"}
    assert body.get("parent_conversation") == ({"namespace": "other", "id": "native-root"} if is_child else None)
    assert body["external_ids"] == {"github_copilot_cli": None}
    assert body["source"] == {"type": "gateway", "name": "litellm"}
    assert body.get("user") is None


@pytest.mark.parametrize("rate_headers", [{"x-ratelimit-remaining": "0"}, {"retry-after": "60"}])
async def test_github_rate_limit_is_retryable_and_never_reaches_inference(rate_headers):
    def limited(request):
        return httpx.Response(403, headers=rate_headers)

    async with httpx.AsyncClient(transport=httpx.MockTransport(limited)) as github:
        gateway = CopilotGateway(forbidden_inference, {"1": "alice@example.test"}, github)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://gateway") as client:
            response = await client.post("/copilot/responses", json={"model": "m"}, headers=headers())
    assert response.status_code == 503
    assert "rate limited" in response.json()["error"]
