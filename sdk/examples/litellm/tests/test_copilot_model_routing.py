"""Native Responses dispatch for GPT models matched by a family route."""

import json
from collections.abc import Iterator

import httpx
import litellm
import pytest
from fastapi import HTTPException
from litellm import Router
from litellm.llms.github_copilot.per_user_auth import GithubCopilotUserSession
from watcher_litellm.copilot import NativeRequest, current_request, provider_callback
from watcher_litellm.copilot_sessions import Conversation


@pytest.fixture
def native_copilot_request() -> Iterator[NativeRequest]:
    identity = NativeRequest(
        user_id="github:1",
        user_email="alice@example.test",
        conversation=Conversation(external_id="root", parent_external_id=None),
        provider_session=GithubCopilotUserSession(token="test-token", api_base="https://api.githubcopilot.com"),
        provider_headers={},
    )
    token = current_request.set(identity)
    try:
        yield identity
    finally:
        current_request.reset(token)


@pytest.mark.parametrize("catalog_mode", ["chat", None])
async def test_native_gpt_family_route_keeps_responses_transport(
    monkeypatch: pytest.MonkeyPatch, native_copilot_request: NativeRequest, catalog_mode: str | None
) -> None:
    model = "gpt-future-test"
    monkeypatch.setattr(litellm, "model_cost", litellm.model_cost.copy())
    monkeypatch.setattr(litellm, "callbacks", [provider_callback])

    async def reject_chat(**kwargs: object) -> object:
        pytest.fail("native Responses request was converted to Chat Completions")

    monkeypatch.setattr(litellm, "acompletion", reject_chat)
    if catalog_mode is not None:
        litellm.register_model(
            {
                f"github_copilot/{model}": {
                    "mode": catalog_mode,
                    "litellm_provider": "github_copilot",
                    "input_cost_per_token": 0.125,
                }
            },
            persist_across_reloads=False,
        )
    router = Router(
        model_list=[
            {
                "model_name": "gpt-*",
                "litellm_params": {
                    "model": "github_copilot/gpt-*",
                    "github_copilot_auth_type": "per_user_oauth",
                    "litellm_credential_name": "native-copilot",
                },
                "model_info": {"mode": "responses"},
            }
        ],
        num_retries=0,
    )
    requests: list[httpx.Request] = []

    def provider(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/responses"
        return httpx.Response(
            200,
            json={
                "id": "resp_family",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": model,
                "output": [],
                "usage": {"input_tokens": 1, "output_tokens": 0, "total_tokens": 1},
            },
        )

    async def send(client: httpx.AsyncClient, request: httpx.Request, **kwargs: object) -> httpx.Response:
        response = provider(request)
        response.request = request
        return response

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    response = await router.aresponses(model=model, input="hello")
    assert response.output == []
    assert len(requests) == 1
    payload: dict[str, object] = json.loads(requests[0].content)
    assert payload["model"] == model
    assert payload["input"] == "hello"
    assert "messages" not in payload
    if catalog_mode is not None:
        assert litellm.model_cost[f"github_copilot/{model}"]["input_cost_per_token"] == 0.125


@pytest.mark.parametrize(
    ("call_type", "model", "is_native"),
    [
        ("acompletion", "gpt-guard-test", True),
        ("aanthropic_messages", "gpt-guard-test", True),
        (None, "gpt-guard-test", True),
        ("aresponses", "gpt-guard-test", False),
        ("aresponses", "gemini-guard-test", True),
    ],
)
async def test_model_mode_is_unchanged_outside_native_gpt_responses(
    monkeypatch: pytest.MonkeyPatch,
    native_copilot_request: NativeRequest,
    call_type: str | None,
    model: str,
    is_native: bool,
) -> None:
    key = f"github_copilot/{model}"
    monkeypatch.setattr(litellm, "model_cost", litellm.model_cost.copy())
    litellm.register_model({key: {"mode": "chat", "litellm_provider": "github_copilot"}}, persist_across_reloads=False)
    token = current_request.set(native_copilot_request if is_native else None)
    kwargs: dict[str, object] = {"model": key}
    try:
        await provider_callback.async_pre_call_deployment_hook(kwargs, call_type)
    finally:
        current_request.reset(token)
    assert litellm.model_cost[key]["mode"] == "chat"
    if not is_native:
        assert kwargs == {"model": key}


async def test_native_model_mode_does_not_override_another_provider(
    monkeypatch: pytest.MonkeyPatch, native_copilot_request: NativeRequest
) -> None:
    key = "github_copilot/gpt-guard-test"
    monkeypatch.setattr(litellm, "model_cost", litellm.model_cost.copy())
    litellm.register_model({key: {"mode": "chat", "litellm_provider": "github_copilot"}}, persist_across_reloads=False)
    kwargs: dict[str, object] = {"model": key, "custom_llm_provider": "openai"}
    with pytest.raises(HTTPException, match="must use the GitHub Copilot provider"):
        await provider_callback.async_pre_call_deployment_hook(kwargs, "aresponses")
    assert litellm.model_cost[key]["mode"] == "chat"
