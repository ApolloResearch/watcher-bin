"""Run a real LiteLLM proxy between SDK clients, a scripted provider and a fake Watcher.

The proxy is the installed ``litellm`` CLI in a subprocess, loading the
packaged callback exactly as a deployment would. The provider and Watcher
stand-ins run in threads of the test process so tests can change their
behavior and inspect what they received.
"""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from harness import litellm_proxy, serve_in_thread  # noqa: E402
from servers import ProviderState, WatcherState, provider_app, watcher_app  # noqa: E402


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
