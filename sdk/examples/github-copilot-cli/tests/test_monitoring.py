"""Retrospective assessment: batch boundaries, historical prefixes and the latest turn only."""

import asyncio
import json
from copy import deepcopy

import httpx
import pytest
from pydantic import JsonValue
from watcher_github_copilot_cli.monitoring import assess

from watcher_sdk import AsyncWatcherClient, WatcherError


def assessed(
    messages: list[dict[str, JsonValue]], *, start: int = 0, fail: bool = False, budget: float = 40
) -> list[dict[str, JsonValue]]:
    """Assess ``messages`` against a fixture Watcher and return the request bodies it received."""
    requests: list[dict[str, JsonValue]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if fail:
            return httpx.Response(503, json={"detail": "synthetic unavailable observation"})
        outcomes = [
            {
                "tool_use_id": item["tool_use_id"],
                "decision": "deferred",
                "enforcement_mode": "observe",
                "judged_decision": "deny",
                "decision_source": "triage",
                "verdict": {},
                "latency_ms": 1,
            }
            for item in body["input"]
        ]
        return httpx.Response(200, json=outcomes)

    async def run() -> None:
        http = httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        async with AsyncWatcherClient(httpx_client=http, max_retries=0) as client:
            await assess(client, "native:id", messages, start=start, budget_seconds=budget)

    asyncio.run(run())
    return requests


def test_batch_limit_and_historical_context() -> None:
    calls: list[JsonValue] = [{"id": f"t{i}", "function": "tool", "arguments": {"n": i}} for i in range(65)]
    messages: list[dict[str, JsonValue]] = [
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": "", "tool_calls": calls},
        {"role": "tool", "content": "result", "tool_call_id": "t0"},
        {"role": "assistant", "content": "final"},
    ]
    original = deepcopy(messages)
    requests = assessed(messages)
    assert [len(request["input"]) for request in requests if isinstance(request["input"], list)] == [32, 32, 1]
    assert all(request["messages"] == messages[:2] for request in requests)
    assert all(request["mode"] == "triage_only" for request in requests)
    assert all("settings_overrides" not in request and not request.get("ephemeral") for request in requests)
    assert messages == original


def test_only_the_latest_turn_is_assessed() -> None:
    messages: list[dict[str, JsonValue]] = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "old", "function": "view", "arguments": {}}]},
        {"role": "tool", "content": "result", "tool_call_id": "old"},
        {"role": "assistant", "content": "done"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "new", "function": "view", "arguments": {}}]},
        {"role": "tool", "content": "result", "tool_call_id": "new"},
        {"role": "assistant", "content": "done again"},
    ]
    [request] = assessed(messages, start=4)
    assert request["input"] == [{"tool_use_id": "new", "tool_name": "view", "tool_input": {}}]
    assert request["messages"] == messages[:6]


def test_a_failed_judgment_raises() -> None:
    messages: list[dict[str, JsonValue]] = [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "t", "function": "tool", "arguments": {}}]},
        {"role": "assistant", "content": "final"},
    ]
    with pytest.raises(WatcherError):
        assessed(messages, fail=True)


def test_a_text_only_turn_sends_nothing() -> None:
    assert assessed([{"role": "assistant", "content": "final"}]) == []


@pytest.mark.parametrize("budget", [0, -1, 41, float("nan"), float("inf")])
def test_invalid_budgets_do_not_contact_watcher(budget: float) -> None:
    with pytest.raises(ValueError, match="budget"):
        assessed([{"role": "assistant", "content": "final"}], budget=budget)


def test_each_request_may_outlast_watchers_ten_second_triage_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    timeouts: list[object] = []

    async def record(**options: object) -> list[object]:
        timeouts.append(options["timeout"])
        return []

    async def run() -> None:
        async with AsyncWatcherClient("http://unused.test") as client:
            monkeypatch.setattr(client, "pre_tool_use_hook", record)
            call: dict[str, JsonValue] = {"id": "t", "function": "view", "arguments": {}}
            with pytest.raises(ValueError, match="incomplete"):
                await assess(client, "native:id", [{"role": "assistant", "content": "", "tool_calls": [call]}])

    asyncio.run(run())
    [timeout] = timeouts
    assert isinstance(timeout, float) and timeout > 30
