"""Require an unambiguous decision for every call before gateway delivery."""

from copy import deepcopy

import httpx
import pytest
from watcher_portkey.bridge import UnsupportedExchange, evaluate

from watcher_sdk import AsyncWatcherClient


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["reverse", "missing", "unknown", "duplicate", "error", "reused-response-id"])
async def test_id_only_decisions_cover_every_delivered_call(case):
    calls = [
        {"type": "function", "id": identifier, "function": {"name": "read_file", "arguments": "{}"}}
        for identifier in ("call-first", "call-second")
    ]
    # A completed call in history may legitimately share a response ID. The
    # response itself and its decisions must still be uniquely matchable.
    request = {
        "model": "fixture",
        "messages": [
            {"role": "user", "content": "Read again"},
            {"role": "assistant", "content": None, "tool_calls": [deepcopy(calls[0])]},
            {"role": "tool", "tool_call_id": "call-first", "content": "Previous result"},
        ],
    }
    response = {
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": None, "tool_calls": calls},
            }
        ]
    }
    outputs = [
        {
            "tool_use_id": call["id"],
            "decision": "allow",
            "judged_decision": "allow",
            "decision_source": "rule",
            "enforcement_mode": "enforce",
            "verdict": {},
            "latency_ms": 0,
        }
        for call in reversed(calls)
    ]
    if case == "missing":
        outputs.pop()
    elif case == "unknown":
        outputs[0]["tool_use_id"] = "unknown"
    elif case == "duplicate":
        outputs[1] = deepcopy(outputs[0])
    elif case == "error":
        outputs[0] = {"tool_use_id": outputs[0]["tool_use_id"], "status_code": 503, "detail": "fixture"}
    elif case == "reused-response-id":
        calls[1]["id"] = calls[0]["id"]
        outputs[0]["tool_use_id"] = calls[0]["id"]
        outputs[0].update(decision="deny", judged_decision="deny")
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(200, json=outputs)

    async with AsyncWatcherClient(
        "http://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="http://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as watcher:
        if case == "reused-response-id":
            with pytest.raises(UnsupportedExchange, match="Duplicate"):
                await evaluate(watcher, request, response, conversation_id="portkey:fixture-exchange")
            assert sent == []
        else:
            assert await evaluate(watcher, request, response, conversation_id="portkey:fixture-exchange") is (
                case == "reverse"
            )
            assert len(sent) == 1
