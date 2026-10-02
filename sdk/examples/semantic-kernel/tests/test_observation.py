"""Public SDK transport regressions for post-run monitoring semantics."""

import json
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from watcher_semantic_kernel.adapter import IncompleteObservationError, observe_transcript

from watcher_sdk import AsyncWatcherClient, WatcherAPIError

HISTORY = json.loads((Path(__file__).parent / "fixtures/history.json").read_text())


def result_for(call):
    return {
        "decision": "deferred",
        "judged_decision": "allow",
        "decision_source": "rule",
        "enforcement_mode": "observe",
        "tool_use_id": call["tool_use_id"],
        "verdict": {"severity_score": None, "severity_label": None, "summary": "Observed", "explanation": "fixture"},
        "latency_ms": 1,
    }


@asynccontextmanager
async def client_for(respond):
    async with (
        httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(respond)) as transport,
        AsyncWatcherClient(
            "https://watcher.invalid",
            httpx_client=transport,
            manage_external_httpx_client_lifecycle=False,
            max_retries=0,
        ) as client,
    ):
        yield client


@pytest.mark.asyncio
async def test_tools_use_historical_prefixes_and_final_tail_is_recorded():
    before = deepcopy(HISTORY)
    sent = []

    async def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        assert "require_recording" not in request.url.params
        outcomes = [result_for(call) for call in body["input"] or []]
        for outcome in outcomes:
            outcome["judged_decision"] = {"a": "allow", "b": "deny", "c": "escalate"}[outcome["tool_use_id"]]
        return httpx.Response(200, json=outcomes)

    async with client_for(respond) as client:
        outcomes = await observe_transcript(client, "history", HISTORY)
    assert before == HISTORY
    assert [outcome.judged_decision for outcome in outcomes] == ["allow", "deny", "escalate"]
    assert len(sent) == 3
    assert sent[0]["messages"] == HISTORY[:2]
    assert sent[1]["messages"] == HISTORY[:5]
    assert sent[2]["messages"] == HISTORY
    assert sent[2]["input"] is None
    assert "FUTURE" not in json.dumps(sent[0])
    assert "FUTURE" not in json.dumps(sent[1])
    assert [call["tool_use_id"] for call in sent[0]["input"]] == ["a", "b"]
    assert [call["tool_use_id"] for call in sent[1]["input"]] == ["c"]
    assert all(body["external_ids"] == {"other": "semantic-kernel:history"} for body in sent)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "empty",
        "short",
        "scalar",
        "missing_id",
        "wrong_id",
        "duplicate_id",
        "wrong_order",
        "item_error",
        "paused",
        "no_judgment",
        "grading_error",
        "applied_allow",
        "bypass",
    ],
)
async def test_incomplete_outcomes_raise_and_still_flush_the_final_tail(case):
    sent = []

    async def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        if body["input"] is None:
            return httpx.Response(200, json=[])
        outcomes = [result_for(call) for call in body["input"]]
        if case == "empty":
            outcomes = []
        elif case == "short":
            outcomes = outcomes[:1]
        elif case == "scalar":
            outcomes = outcomes[0]
        elif case == "missing_id":
            outcomes[0].pop("tool_use_id")
        elif case == "wrong_id":
            outcomes[0]["tool_use_id"] = "wrong"
        elif case == "duplicate_id":
            outcomes[1]["tool_use_id"] = "a"
        elif case == "wrong_order":
            outcomes.reverse()
        elif case == "item_error":
            outcomes[0] = {"status_code": 503, "detail": "No judgment", "tool_use_id": "a"}
        elif case == "paused":
            outcomes[0]["enforcement_mode"] = "paused"
            outcomes[0]["judged_decision"] = None
        elif case == "no_judgment":
            outcomes[0].pop("judged_decision")
        elif case == "grading_error":
            outcomes[0]["decision_source"] = "grading_error"
        elif case == "applied_allow":
            outcomes[0]["decision"] = "allow"
        elif case == "bypass":
            outcomes[0]["decision_source"] = "bypass"
        return httpx.Response(200, json=outcomes)

    async with client_for(respond) as client:
        with pytest.raises(IncompleteObservationError):
            await observe_transcript(client, "history", HISTORY)
    assert len(sent) == 2
    assert sent[-1]["input"] is None
    assert sent[-1]["messages"] == HISTORY


@pytest.mark.asyncio
async def test_judgment_http_error_does_not_drop_the_final_tail():
    sent = []

    async def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        if body["input"] is not None:
            return httpx.Response(503, json={"detail": "Judgment failed"})
        return httpx.Response(200, json=[])

    async with client_for(respond) as client:
        with pytest.raises(WatcherAPIError):
            await observe_transcript(client, "history", HISTORY)
    assert len(sent) == 2
    assert sent[-1]["input"] is None
    assert sent[-1]["messages"][-1] == {"role": "assistant", "content": "FUTURE ANSWER"}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["http_error", "unexpected_outcome"])
async def test_final_recording_failure_is_not_advertised_as_completed_observation(failure):
    async def respond(request):
        body = json.loads(request.content)
        if body["input"] is not None:
            return httpx.Response(200, json=[result_for(call) for call in body["input"]])
        if failure == "http_error":
            return httpx.Response(503, json={"detail": "Submission failed"})
        return httpx.Response(200, json=[result_for({"tool_use_id": "unexpected"})])

    async with client_for(respond) as client:
        with pytest.raises(WatcherAPIError if failure == "http_error" else IncompleteObservationError):
            await observe_transcript(client, "history", HISTORY)


@pytest.mark.asyncio
async def test_more_than_32_parallel_calls_keep_the_same_prefix_across_batches():
    calls = [{"id": f"parallel-{index}", "function": "read_file", "arguments": {"index": index}} for index in range(33)]
    history = [
        {"role": "user", "content": "Read files"},
        {"role": "assistant", "content": "", "tool_calls": calls},
        {"role": "assistant", "content": "FUTURE ANSWER"},
    ]
    sent = []

    async def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        return httpx.Response(200, json=[result_for(call) for call in body["input"] or []])

    async with client_for(respond) as client:
        outcomes = await observe_transcript(client, "parallel", history)
    assert len(outcomes) == 33
    assert [len(body["input"]) for body in sent if body["input"] is not None] == [32, 1]
    assert sent[0]["messages"] == sent[1]["messages"] == history[:2]
    assert sent[-1]["messages"] == history


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,decision,judged,source",
    [
        ("enforce", "allow", "allow", "rule"),
        ("enforce", "deny", "deny", "triage"),
        ("enforce", "escalate", "escalate", "triage"),
        ("observe", "deferred", "deny", "triage"),
        ("paused", "deferred", None, "bypass"),
        ("enforce", "allow", "allow", "grading_error"),
    ],
)
async def test_retrospective_assessment_inherits_server_policy(mode, decision, judged, source):
    sent = []

    async def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        assert "settings_overrides" not in body
        outcomes = []
        for call in body["input"] or []:
            item = result_for(call)
            item.update(enforcement_mode=mode, decision=decision, judged_decision=judged, decision_source=source)
            if source == "grading_error":
                item["grading_error"] = {"code": "timeout", "message": "fixture timeout"}
            outcomes.append(item)
        return httpx.Response(200, json=outcomes)

    async with client_for(respond) as client:
        outcomes = await observe_transcript(client, "inherited-history", HISTORY)
    assert len(outcomes) == 3
    assert all(str(outcome.enforcement_mode) == mode for outcome in outcomes)
    assert sent[-1]["input"] is None and sent[-1]["messages"] == HISTORY
