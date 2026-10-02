"""Fixtures for tests that need a real Watcher server and real providers."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from common import GATEWAY, WATCHER_URL, apply_policy  # noqa: E402


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/live/" in str(item.path):
            item.add_marker(pytest.mark.live)
            if not (WATCHER_URL and GATEWAY):
                item.add_marker(
                    pytest.mark.skip(reason="set WATCHER_LIVE_API_URL and WATCHER_LIVE_GATEWAY_URL to run live tests")
                )


@pytest.fixture(scope="session")
def live_policy() -> None:
    apply_policy()
