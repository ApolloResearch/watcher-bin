"""Bounded queue failure, ordering, and recording acknowledgement contracts."""

import asyncio
import json

import httpx
import pytest
from watcher_mastra_bridge.observation import ObservationQueue

from watcher_sdk import AsyncWatcherClient


@pytest.mark.asyncio
async def test_full_queue_drops_newest_snapshot_visibly():
    received = []

    def handler(request):
        received.append(json.loads(request.content))
        return httpx.Response(200, json=[])

    async with AsyncWatcherClient(
        "https://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as watcher:
        queue = ObservationQueue(watcher, "queue-test")
        for index in range(33):
            queue.enqueue([{"role": "user", "content": str(index)}], [])
        assert len(queue.tasks) == 32
        assert queue.errors == ["ObservationQueueFull"]
        await queue.flush()
    assert len(received) == 32
    assert received[-1]["messages"][0]["content"] == "31"
    assert queue.error_count == 1
    assert queue.tasks == []


@pytest.mark.asyncio
async def test_submission_order_is_preserved_while_first_request_waits():
    started = asyncio.Event()
    release = asyncio.Event()
    received = []

    async def handler(request):
        payload = json.loads(request.content)
        received.append(payload["messages"][0]["content"])
        if len(received) == 1:
            started.set()
            await asyncio.wait_for(release.wait(), 2)
        return httpx.Response(200, json=[])

    async with AsyncWatcherClient(
        "https://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as watcher:
        queue = ObservationQueue(watcher, "queue-test")
        first = [{"role": "user", "content": "first"}]
        queue.enqueue(first, [])
        first[0]["content"] = "mutated"
        queue.enqueue([{"role": "assistant", "content": "final"}], [])
        await asyncio.wait_for(started.wait(), 1)
        assert received == ["first"]
        release.set()
        await queue.flush()
    assert received == ["first", "final"]


@pytest.mark.asyncio
async def test_successful_submission_does_not_require_receipt_header():
    def handler(request):
        assert "require_recording" not in request.url.params
        return httpx.Response(200, json=[])

    async with AsyncWatcherClient(
        "https://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as watcher:
        queue = ObservationQueue(watcher, "queue-test")
        queue.enqueue([{"role": "assistant", "content": "final"}], [])
        await queue.flush()
    assert queue.errors == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcomes,expected",
    [
        ([{"status_code": 422, "detail": "refused", "tool_use_id": "call-a"}], "HookCallError:422"),
        ([], "OutcomeCountMismatch"),
        ([{"status_code": 422, "detail": "refused", "tool_use_id": "wrong-id"}], "OutcomeIdentityMismatch"),
    ],
)
async def test_batch_refusal_or_wrong_identity_is_not_a_judgment(outcomes, expected):
    def handler(request):
        return httpx.Response(200, json=outcomes)

    async with AsyncWatcherClient(
        "https://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as watcher:
        queue = ObservationQueue(watcher, "queue-test")
        queue.enqueue(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": "call-a", "function": "lookup", "arguments": {}, "type": "function"}],
                }
            ],
            [{"tool_use_id": "call-a", "tool_name": "lookup", "tool_input": {}}],
        )
        await queue.flush()
    assert queue.errors == [expected]
    assert queue.judgments == []


def test_error_history_is_bounded_while_total_count_is_retained():
    queue = ObservationQueue(None, "queue-test")  # ty: ignore[invalid-argument-type]  # Counters do not access the client.
    for index in range(140):
        queue.fail(str(index))
    assert len(queue.errors) == 128
    assert queue.errors[0] == "12"
    assert queue.errors[-1] == "139"
    assert queue.error_count == 140


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [httpx.ReadError, httpx.RemoteProtocolError, httpx.WriteError])
async def test_transport_failure_does_not_poison_later_snapshots(error_type):
    attempted = []
    received = []

    def handler(request):
        content = json.loads(request.content)["messages"][0]["content"]
        attempted.append(content)
        if content == "first":
            raise error_type("connection interrupted", request=request)
        received.append(content)
        return httpx.Response(200, json=[])

    async with AsyncWatcherClient(
        "https://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as watcher:
        queue = ObservationQueue(watcher, "queue-test")
        queue.enqueue([{"role": "user", "content": "first"}], [])
        queue.enqueue([{"role": "assistant", "content": "second"}], [])
        queue.enqueue([{"role": "assistant", "content": "final"}], [])
        await queue.flush()
    assert attempted == ["first", "second", "final"]
    assert received == ["second", "final"]
    assert queue.errors == [error_type.__name__]
    assert queue.error_count == 1
    assert queue.tasks == []


@pytest.mark.asyncio
async def test_flush_waits_for_later_snapshot_after_transport_failure():
    second_started = asyncio.Event()
    release = asyncio.Event()
    received = []

    async def handler(request):
        content = json.loads(request.content)["messages"][0]["content"]
        if content == "first":
            raise httpx.ReadError("connection interrupted", request=request)
        second_started.set()
        await asyncio.wait_for(release.wait(), 2)
        received.append(content)
        return httpx.Response(200, json=[])

    async with AsyncWatcherClient(
        "https://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as watcher:
        queue = ObservationQueue(watcher, "queue-test")
        queue.enqueue([{"role": "user", "content": "first"}], [])
        queue.enqueue([{"role": "assistant", "content": "final"}], [])
        flushed = asyncio.create_task(queue.flush())
        await asyncio.wait_for(second_started.wait(), 1)
        assert not flushed.done()
        release.set()
        await asyncio.wait_for(flushed, 1)
    assert received == ["final"]
    assert queue.errors == ["ReadError"]
    assert queue.error_count == 1


@pytest.mark.asyncio
async def test_cancelled_submission_is_counted_without_losing_later_snapshot():
    received = []

    def handler(request):
        content = json.loads(request.content)["messages"][0]["content"]
        if content == "first":
            raise asyncio.CancelledError()
        received.append(content)
        return httpx.Response(200, json=[])

    async with AsyncWatcherClient(
        "https://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as watcher:
        queue = ObservationQueue(watcher, "queue-test")
        queue.enqueue([{"role": "user", "content": "first"}], [])
        queue.enqueue([{"role": "assistant", "content": "final"}], [])
        await queue.flush()
    assert received == ["final"]
    assert queue.errors == ["CancelledError"]
    assert queue.error_count == 1


@pytest.mark.asyncio
async def test_cancelled_completed_submission_is_counted_before_next_enqueue():
    received = []

    def handler(request):
        content = json.loads(request.content)["messages"][0]["content"]
        if content == "first":
            raise asyncio.CancelledError()
        received.append(content)
        return httpx.Response(200, json=[])

    async with AsyncWatcherClient(
        "https://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as watcher:
        queue = ObservationQueue(watcher, "queue-test")
        queue.enqueue([{"role": "user", "content": "first"}], [])
        await asyncio.gather(queue.tasks[0], return_exceptions=True)
        queue.enqueue([{"role": "assistant", "content": "final"}], [])
        await queue.flush()
    assert received == ["final"]
    assert queue.errors == ["CancelledError"]
    assert queue.error_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,judgment",
    [("bypass", None), ("not_evaluated", None), ("grading_error", "allow"), ("rule", None)],
)
async def test_bypassed_or_failed_monitoring_is_not_a_completed_judgment(source, judgment):
    def handler(request):
        return httpx.Response(
            200,
            json=[
                {
                    "tool_use_id": "call-a",
                    "decision": "deferred",
                    "decision_source": source,
                    "enforcement_mode": "observe",
                    "judged_decision": judgment,
                    "latency_ms": 0,
                    "verdict": {"explanation": "Monitoring fixture"},
                }
            ],
        )

    async with AsyncWatcherClient(
        "https://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as watcher:
        queue = ObservationQueue(watcher, "queue-test")
        queue.enqueue(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": "call-a", "function": "lookup", "arguments": {}}],
                }
            ],
            [{"tool_name": "lookup", "tool_input": {}, "tool_use_id": "call-a"}],
        )
        await queue.flush()
    assert queue.errors == ["IncompleteJudgment"]
    assert queue.error_count == 1
    assert queue.judgments == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,decision,judged,source",
    [
        ("enforce", "deny", "deny", "triage"),
        ("enforce", "escalate", "escalate", "triage"),
        ("observe", "deferred", "deny", "triage"),
        ("paused", "deferred", None, "bypass"),
        ("enforce", "allow", "allow", "grading_error"),
    ],
)
async def test_queue_inherits_policy_without_changing_completed_actions(mode, decision, judged, source):
    def respond(request):
        body = json.loads(request.content)
        assert "settings_overrides" not in body
        outcomes = []
        for call in body["input"]:
            item = {
                "tool_use_id": call["tool_use_id"],
                "enforcement_mode": mode,
                "decision": decision,
                "judged_decision": judged,
                "decision_source": source,
                "verdict": {},
                "latency_ms": 1,
            }
            if source == "grading_error":
                item["grading_error"] = {"code": "timeout", "message": "fixture timeout"}
            outcomes.append(item)
        return httpx.Response(200, json=outcomes)

    async with AsyncWatcherClient(
        httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
    ) as client:
        queue = ObservationQueue(client, "inherited-policy")
        queue.enqueue(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": "call-a", "function": "lookup", "arguments": {}}],
                }
            ],
            [{"tool_use_id": "call-a", "tool_name": "lookup", "tool_input": {}}],
        )
        await queue.flush()
    assert len(queue.judgments) == (0 if mode == "paused" or source == "grading_error" else 1)
    assert queue.errors == (["GradingFailurePolicyApplied"] if source == "grading_error" else [])
