"""Historical tool context, API batch limits, and final recording for file bridges."""

import json

import httpx
import pytest
from watcher_langchain4j_bridge.bridge import observe_snapshots

from watcher_sdk import AsyncWatcherClient


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_first", [False, True])
async def test_historical_prefix_batch_limit_and_final_tail_after_failure(tmp_path, fail_first):
    calls = [{"id": str(index), "function": "lookup", "arguments": {"index": index}} for index in range(33)]
    messages = [
        {"role": "user", "content": "Look up the entries"},
        {"role": "assistant", "content": "Checking", "tool_calls": calls},
        *[{"role": "tool", "tool_call_id": call["id"], "content": "Future result"} for call in calls],
        {"role": "assistant", "content": "Future final answer"},
    ]
    snapshot = tmp_path / "0.json"
    snapshot.write_text(json.dumps(messages))
    sent = []

    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        if fail_first and len(sent) == 1:
            return httpx.Response(503, json={"detail": "fixture failure"})
        outcomes = [
            {
                "decision": "deferred",
                "judged_decision": "allow",
                "decision_source": "rule",
                "enforcement_mode": "observe",
                "tool_use_id": item["tool_use_id"],
                "latency_ms": 0,
                "verdict": {},
            }
            for item in body["input"]
        ]
        return httpx.Response(200, json=outcomes)

    async with AsyncWatcherClient(
        "https://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as client:
        queue = await observe_snapshots(client, [snapshot], "prefix-test")
    assert [len(item["input"]) for item in sent] == [32, 1, 0]
    assert all(item["messages"] == messages[:2] for item in sent[:2])
    assert sent[-1]["messages"] == messages
    assert queue.error_count == int(fail_first)
    assert len(queue.judgments) == (1 if fail_first else 33)
