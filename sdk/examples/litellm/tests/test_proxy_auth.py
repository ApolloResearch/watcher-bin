"""Authenticated gateway identities cannot be replaced by client-supplied attribution."""

import json

import httpx
import pytest
from fastapi import HTTPException
from litellm.constants import LITELLM_PROXY_MASTER_KEY_ALIAS
from litellm.proxy._types import UserAPIKeyAuth
from watcher_litellm.callback import WatcherCallback
from watcher_litellm.proxy_auth import account_email, account_session, proxy_client

from watcher_sdk import AsyncWatcherClient
from watcher_sdk.capture import ConversationIdentity


@pytest.mark.parametrize(
    "user",
    [
        UserAPIKeyAuth(user_email="dev@example.com"),
        UserAPIKeyAuth(user_id="default_user_id", user_email="dev@example.com"),
        UserAPIKeyAuth(user_id="id", user_email="missing-domain"),
        UserAPIKeyAuth(user_id="id", user_email="jürgen@example.de"),
        UserAPIKeyAuth(user_id="id", user_email="dev@example.com\r\nx-admin: true"),
        UserAPIKeyAuth(user_id="id", user_email="dev@example.com", api_key=LITELLM_PROXY_MASTER_KEY_ALIAS),
    ],
)
def test_proxy_auth_refuses_unattributed_or_administrator_credentials(user: UserAPIKeyAuth) -> None:
    with pytest.raises(HTTPException) as refused:
        account_email(user)
    assert refused.value.status_code == 401


def test_account_identity_survives_key_rotation_and_separates_shared_session_ids() -> None:
    alice = UserAPIKeyAuth(user_id="alice", user_email="Alice@Example.com", api_key="old")
    rotated = UserAPIKeyAuth(user_id="alice", user_email="alice@example.com", api_key="new")
    bob = UserAPIKeyAuth(user_id="bob", user_email="bob@example.com")
    assert account_email(alice) == "alice@example.com"
    assert account_session(alice, "same-conversation") == account_session(rotated, "same-conversation")
    assert account_session(alice, "same-conversation") != account_session(bob, "same-conversation")
    assert account_session(alice, "another-conversation") != account_session(alice, "same-conversation")


async def test_proxy_client_uses_server_headers_and_closes_its_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WATCHER_API_URL", "http://watcher")
    monkeypatch.setenv("WATCHER_PROXY_AUTH_TOKEN", "server-owned-secret")
    monkeypatch.setenv("WATCHER_PROXY_HEADER_USER", "x-company-user")
    monkeypatch.setenv("WATCHER_PROXY_HEADER_ROLE", "x-company-role")
    requests = []
    clients = []
    http_client = httpx.AsyncClient

    def capture(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"version": "test", "git_sha": None})

    def with_transport(**kwargs: object) -> httpx.AsyncClient:
        client = http_client(**kwargs, transport=httpx.MockTransport(capture))
        clients.append(client)
        return client

    monkeypatch.setattr("watcher_litellm.proxy_auth.httpx.AsyncClient", with_transport)
    async with proxy_client(UserAPIKeyAuth(user_id="alice", user_email="Alice@Example.com")) as client:
        assert (await client.version()).version == "test"
    assert requests[0].headers["x-auth-proxy-token"] == "server-owned-secret"
    assert requests[0].headers["x-company-user"] == "alice@example.com"
    assert requests[0].headers["x-company-role"] == "member"
    assert "authorization" not in requests[0].headers
    assert clients[0].is_closed


@pytest.mark.parametrize("is_proxy", [False, True])
@pytest.mark.parametrize(
    "identity_headers,identity",
    [
        ({"x-watcher-session-id": "shared"}, ConversationIdentity(namespace="other", id="litellm:shared")),
        (
            {"user-agent": "claude-cli/2.1", "x-claude-code-session-id": "00000000-0000-4000-8000-000000000001"},
            ConversationIdentity(namespace="claude_code", id="00000000-0000-4000-8000-000000000001"),
        ),
        (
            {
                "user-agent": "claude-cli/2.1",
                "x-claude-code-session-id": "00000000-0000-4000-8000-000000000001",
                "x-claude-code-agent-id": "child-1",
            },
            ConversationIdentity(
                namespace="claude_code", id='subagent:["00000000-0000-4000-8000-000000000001","child-1"]'
            ),
        ),
        (
            {"user-agent": "opencode/1", "x-opencode-session-id": "shared"},
            ConversationIdentity(namespace="opencode", id="shared"),
        ),
    ],
)
async def test_callback_attributes_only_the_authenticated_account(
    monkeypatch: pytest.MonkeyPatch,
    is_proxy: bool,
    identity_headers: dict[str, str],
    identity: ConversationIdentity,
) -> None:
    monkeypatch.setenv("WATCHER_AUTH_MODE", "proxy" if is_proxy else "api_key")
    requests = []

    def capture(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=[])

    def client() -> AsyncWatcherClient:
        http = httpx.AsyncClient(base_url="http://watcher", transport=httpx.MockTransport(capture))
        return AsyncWatcherClient("http://watcher", httpx_client=http)

    user = UserAPIKeyAuth(user_id="alice", user_email="alice@example.com")
    data = {
        "model": "fixture",
        "messages": [{"role": "user", "content": "Hello"}],
        "proxy_server_request": {
            "url": "http://proxy/v1/chat/completions",
            "headers": {**identity_headers, "x-forwarded-user": "bob@example.com"},
            "body": {"messages": [{"role": "user", "content": "Hello"}], "user": "bob@example.com"},
        },
    }
    if is_proxy:
        monkeypatch.setenv("WATCHER_API_URL", "http://watcher")
        monkeypatch.setenv("WATCHER_PROXY_AUTH_TOKEN", "server-owned-secret")
        http_client = httpx.AsyncClient

        def with_transport(**kwargs: object) -> httpx.AsyncClient:
            return http_client(**kwargs, transport=httpx.MockTransport(capture))

        monkeypatch.setattr("watcher_litellm.proxy_auth.httpx.AsyncClient", with_transport)
    callback = WatcherCallback(None if is_proxy else client)
    await callback.async_pre_call_hook(user, None, data, "completion")
    response = {"choices": [{"message": {"role": "assistant", "content": "Hi"}, "finish_reason": "stop"}]}
    assert await callback.async_post_call_success_hook(data, user, response) == response
    assert len(requests) == 1
    assert requests[0].get("user") == (None if is_proxy else "alice@example.com")
    if is_proxy:
        session_id = identity.id if identity.namespace == "other" else f"{identity.namespace}:{identity.id}"
        expected = {"namespace": "other", "id": account_session(user, session_id)}
    else:
        expected = identity.model_dump()
    assert requests[0]["conversation"] == expected
    assert requests[0]["source"] == {"type": "gateway", "name": "litellm"}
    assert "external_ids" not in requests[0]


def test_empty_proxy_token_fails_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WATCHER_PROXY_AUTH_TOKEN", " ")
    with pytest.raises(ValueError, match="must not be empty"):
        proxy_client(UserAPIKeyAuth(user_id="alice", user_email="alice@example.com"))


async def test_proxy_auth_rejects_unattributed_requests_before_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WATCHER_AUTH_MODE", "proxy")
    data = {"proxy_server_request": {"url": "http://proxy/responses", "body": {}}}
    with pytest.raises(HTTPException) as refused:
        await WatcherCallback().async_pre_call_hook(UserAPIKeyAuth(), None, data, "responses")
    assert refused.value.status_code == 401


@pytest.mark.parametrize("setting", ["WATCHER_API_URL", "WATCHER_PROXY_AUTH_TOKEN"])
@pytest.mark.parametrize("value", [None, " "])
async def test_missing_proxy_configuration_is_rejected_before_generation(
    monkeypatch: pytest.MonkeyPatch, setting: str, value: str | None
) -> None:
    monkeypatch.setenv("WATCHER_AUTH_MODE", "proxy")
    monkeypatch.setenv("WATCHER_API_URL", "http://watcher")
    monkeypatch.setenv("WATCHER_PROXY_AUTH_TOKEN", "secret")
    if value is None:
        monkeypatch.delenv(setting)
    else:
        monkeypatch.setenv(setting, value)
    data = {"proxy_server_request": {"url": "http://proxy/responses", "body": {}}}
    user = UserAPIKeyAuth(user_id="alice", user_email="alice@example.com")
    with pytest.raises(HTTPException, match=setting) as refused:
        await WatcherCallback().async_pre_call_hook(user, None, data, "responses")
    assert refused.value.status_code == 503
