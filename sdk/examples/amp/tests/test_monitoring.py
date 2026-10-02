"""Observation policy, batch boundaries and failure-path tail flushing."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
from watcher_amp.monitoring import observe


class Client:
    def __init__(self, fail=False):
        self.requests = []
        self.fail = fail

    async def pre_tool_use_hook(self, **kwargs):
        self.requests.append(kwargs)
        if self.fail and kwargs["input"]:
            raise ValueError("synthetic unavailable observation")
        return [
            SimpleNamespace(
                to_dict=lambda item=item: {
                    "tool_use_id": item["tool_use_id"],
                    "decision": "deferred",
                    "enforcement_mode": "observe",
                    "judged_decision": "deny",
                    "decision_source": "triage",
                }
            )
            for item in kwargs["input"]
        ]


def test_batch_limit_historical_context_and_tail():
    calls = [{"id": f"t{i}", "function": "tool", "arguments": {"n": i}} for i in range(65)]
    messages = [
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": "", "tool_calls": calls},
        {"role": "tool", "content": "result", "tool_call_id": "t0"},
        {"role": "assistant", "content": "final"},
    ]
    original = deepcopy(messages)
    client = Client()
    asyncio.run(observe(client, "native:id", messages))
    assert [len(request["input"]) for request in client.requests] == [32, 32, 1, 0]
    assert all(request["messages"] == messages[:2] for request in client.requests[:-1])
    assert all("settings_overrides" not in request for request in client.requests[:-1])
    assert client.requests[-1]["messages"] == messages
    assert messages == original


def test_tail_is_flushed_when_judgment_fails():
    client = Client(fail=True)
    messages = [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "t", "function": "tool", "arguments": {}}]},
        {"role": "assistant", "content": "final"},
    ]
    with pytest.raises(ValueError, match="unavailable"):
        asyncio.run(observe(client, "native:id", messages))
    assert client.requests[-1]["input"] == []
    assert client.requests[-1]["messages"] == messages


def test_text_only_turn_still_flushes():
    client = Client()
    asyncio.run(observe(client, "native:id", [{"role": "assistant", "content": "final"}]))
    assert len(client.requests) == 1
    assert client.requests[0]["input"] == []
