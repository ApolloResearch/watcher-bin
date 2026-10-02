"""Verify that execution binds to the exact JSON types shown to the monitor."""

import json
from copy import deepcopy

import httpx
import pytest
from watcher_google_genai.monitoring import Monitor, Withheld

from watcher_sdk import AsyncWatcherClient


@pytest.mark.asyncio
@pytest.mark.parametrize("recorded,executed", [(False, 0), (True, 1), (0, False), (1, True), (1, 1.0)])
async def test_nested_json_type_mutation_cannot_reach_grading_or_execution(tmp_path, recorded, executed):
    requests = []

    def handler(request):
        requests.append(request)
        payload = json.loads(request.content)
        outcomes = [
            {
                "decision": "allow",
                "judged_decision": "allow",
                "decision_source": "rule",
                "enforcement_mode": "enforce",
                "verdict": {},
                "latency_ms": 1,
                "tool_use_id": item["tool_use_id"],
            }
            for item in payload["input"]
        ]
        return httpx.Response(200, json=outcomes)

    async def side_effect(**arguments):
        (tmp_path / "effect").write_text("executed")
        return arguments

    arguments = {"nested": [{"value": recorded}]}
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "binding-id", "function": "weather", "arguments": arguments, "type": "function"}],
        }
    ]
    pending = {"tool_use_id": "binding-id", "tool_name": "weather", "tool_input": deepcopy(arguments)}
    pending["tool_input"]["nested"][0]["value"] = executed
    async with AsyncWatcherClient(
        "https://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as watcher:
        with pytest.raises(Withheld, match="identity does not match"):
            await Monitor(watcher, "binding-session").dispatch(messages, [pending], {"weather": side_effect})
    assert requests == []
    assert not (tmp_path / "effect").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [{"values": (1, 2)}, {1: "nonstring-key"}, {"value": float("nan")}])
async def test_python_only_argument_shape_cannot_reach_execution(tmp_path, arguments):
    async def side_effect(**values):
        (tmp_path / "effect").write_text("executed")
        return values

    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "invalid-id", "function": "weather", "arguments": arguments, "type": "function"}],
        }
    ]
    pending = {"tool_use_id": "invalid-id", "tool_name": "weather", "tool_input": deepcopy(arguments)}
    async with AsyncWatcherClient(
        "https://watcher.invalid",
        httpx_client=httpx.AsyncClient(
            base_url="https://watcher.invalid",
            transport=httpx.MockTransport(lambda request: pytest.fail("Non-JSON arguments must not reach the server")),
        ),
    ) as watcher:
        with pytest.raises((Withheld, ValueError)):
            await Monitor(watcher, "invalid-session").dispatch(messages, [pending], {"weather": side_effect})
    assert not (tmp_path / "effect").exists()
