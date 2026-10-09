"""Run a real LiteLLM proxy between SDK clients, a scripted provider and a fake Watcher.

The proxy is the installed ``litellm`` CLI in a subprocess, loading the
packaged callback exactly as a deployment would. The provider and Watcher
stand-ins run in threads of the test process so tests can change their
behavior and inspect what they received.
"""

import json
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import litellm
import pytest
from watcher_litellm.streams import API, encode

sys.path.insert(0, str(Path(__file__).parent))

from harness import litellm_proxy, serve_in_thread  # noqa: E402
from servers import ProviderState, WatcherState, provider_app, watcher_app  # noqa: E402


@pytest.fixture
def text_only_replan(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supply a provider's text-only alternative for in-process callback contract tests."""

    async def generate(api: API, request: dict[str, Any], data: dict[str, Any], *, stream: bool = False) -> Any:
        response: dict[str, Any]
        if api == "messages":
            response = {
                "id": "msg_alternative",
                "type": "message",
                "role": "assistant",
                "model": "m",
                "content": [{"type": "text", "text": "A permitted alternative."}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 2},
            }
        else:
            response = {
                "id": "chatcmpl_alternative",
                "object": "chat.completion",
                "created": 1,
                "model": "fixture",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "A permitted alternative."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            }
        if not stream:
            return response

        async def events() -> AsyncIterator[Any]:
            for event in encode(api, response):
                if api == "messages":
                    yield event
                else:
                    yield litellm.ModelResponseStream(**json.loads(event.decode().removeprefix("data: ")))

        return events()

    monkeypatch.setattr("watcher_litellm.callback.complete_replan", generate)


@pytest.fixture(scope="session")
def provider_state() -> ProviderState:
    return ProviderState()


@pytest.fixture(scope="session")
def watcher_state() -> WatcherState:
    return WatcherState()


@pytest.fixture
def reset_states(provider_state: ProviderState, watcher_state: WatcherState) -> None:
    vars(provider_state).update(vars(ProviderState()))
    vars(watcher_state).update(vars(WatcherState()))


@pytest.fixture(scope="session")
def proxy_url(
    provider_state: ProviderState, watcher_state: WatcherState, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[str]:
    provider = serve_in_thread(provider_app(provider_state))
    watcher = serve_in_thread(watcher_app(watcher_state))
    model_list = [
        {
            "model_name": "gpt-test",
            "litellm_params": {"model": "openai/gpt-test", "api_base": f"{provider}/v1", "api_key": "k"},
        },
        {
            "model_name": "claude-test",
            "litellm_params": {"model": "anthropic/claude-test", "api_base": provider, "api_key": "k"},
        },
    ]
    env = {"WATCHER_API_URL": watcher, "WATCHER_API_KEY": "test-key"}
    with litellm_proxy(model_list, env, tmp_path_factory.mktemp("proxy")) as url:
        yield url
