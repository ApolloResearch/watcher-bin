"""Native tools follow applied Watcher decisions through the public SDK."""

import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import pytest
from demo.enforce import run_conversation
from demo.observe import run_conversation as run_observed
from watcher_camel.adapter import messages_for_watcher, observe
from watcher_camel.monitoring import Monitor, ToolBlocked

from watcher_sdk import AsyncWatcherClient


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


def outcome(call, decision="allow"):
    return {
        "decision": decision,
        "judged_decision": decision,
        "enforcement_mode": "enforce",
        "decision_source": "rule",
        "tool_use_id": call["tool_use_id"],
        "latency_ms": 1,
        "verdict": {"severity_score": None, "severity_label": None, "summary": "Fixture", "explanation": "Fixture"},
    }


def response(body):
    return httpx.Response(200, json=[] if body["input"] is None else outcome(body["input"]))


def effect_for(path):
    def double(value):
        with path.open("a") as output:
            output.write(str(value) + "\n")
        return str(value * 2)

    return double


@pytest.mark.asyncio
async def test_native_allow_executes_and_records_actual_ids_results_and_final_answer(tmp_path):
    sent = []

    async def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        assert "require_recording" not in request.url.params
        if body["input"] is not None:
            assert not any(
                message["role"] == "assistant" and message["content"] == "4 and 6" for message in body["messages"]
            )
            assert body["mode"] == "full"
            assert body.get("settings_overrides") is None
        return response(body)

    path = tmp_path / "side-effects"
    async with client_for(respond) as client:
        messages = await run_conversation(Monitor(client, "native"), effect_for(path))
    assert sorted(path.read_text().splitlines()) == ["2", "3"]
    transcript = messages_for_watcher(messages)
    assert sent[-1]["input"] is None
    assert sent[-1]["messages"] == transcript
    assert transcript[-1] == {"role": "assistant", "content": "4 and 6"}
    calls = [body["input"] for body in sent if body["input"] is not None]
    assert len(calls) >= 2
    results = {message["tool_call_id"]: message["content"] for message in transcript if message["role"] == "tool"}
    for call in calls:
        expected = str(call["tool_input"]["value"] * 2) if "value" in call["tool_input"] else "4 and 6"
        assert results[call["tool_use_id"]] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "deny",
        "escalate",
        "deferred",
        "paused",
        "wrong_id",
        "missing_id",
        "no_judgment",
        "grading_error",
        "bypass",
        "observe",
        "transport",
        "http",
        "admin_lock",
    ],
)
async def test_native_failures_never_reach_the_tool_side_effect(failure, tmp_path, record_property):
    requests = []

    async def respond(request):
        body = json.loads(request.content)
        if body["input"] is None:
            return response(body)
        requests.append(body)
        if failure == "transport":
            raise httpx.ReadTimeout("Fixture timeout", request=request)
        if failure in ("http", "admin_lock"):
            return httpx.Response(
                503 if failure == "http" else 422,
                json={"detail": [{"loc": ["body"], "msg": "Fixture rejection", "type": "value_error"}]},
            )
        result = outcome(body["input"])
        if failure in ("deny", "escalate", "deferred"):
            result["decision"] = failure
            result["judged_decision"] = "deny" if failure == "deferred" else failure
        elif failure in ("paused", "observe"):
            result["enforcement_mode"] = failure
        elif failure == "wrong_id":
            result["tool_use_id"] = "someone-elses-call"
        elif failure == "missing_id":
            result.pop("tool_use_id")
        elif failure == "no_judgment":
            result.pop("judged_decision")
        elif failure == "grading_error":
            result["grading_error"] = "Fixture error"
        elif failure == "bypass":
            result["decision_source"] = "bypass"
        return httpx.Response(200, json=result)

    path = tmp_path / "side-effects"
    behavior = "returned"
    async with client_for(respond) as client:
        try:
            await run_conversation(
                Monitor(client, "failure", enforcement="enforce" if failure == "admin_lock" else "server"),
                effect_for(path),
            )
        except Exception as error:
            behavior = type(error).__name__
    record_property("native_behavior", behavior)
    record_property("grading_requests", len(requests))
    assert (behavior == "returned") is False
    assert len({body["input"]["tool_use_id"] for body in requests}) == len(requests)
    assert len(requests) <= 2, "The deterministic model must not silently retry rejected calls"
    assert requests, "The native path must actually reach Watcher before this proves enforcement"
    assert not path.exists(), "A rejected or incomplete decision executed a native tool"


@pytest.mark.asyncio
async def test_pending_native_decision_means_no_side_effect(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()

    async def respond(request):
        body = json.loads(request.content)
        if body["input"] is not None:
            entered.set()
            await release.wait()
        return response(body)

    path = tmp_path / "side-effects"
    async with client_for(respond) as client:
        task = asyncio.create_task(run_conversation(Monitor(client, "pending"), effect_for(path)))
        try:
            await asyncio.wait_for(entered.wait(), 20)
            assert not task.done()
            assert not path.exists()
        finally:
            release.set()
        await asyncio.wait_for(task, 30)
    assert sorted(path.read_text().splitlines()) == ["2", "3"]


@pytest.mark.asyncio
async def test_retained_observation_runs_tools_even_when_watcher_judges_deny():
    messages = await run_observed()
    transcript = messages_for_watcher(messages)
    assert any(message["role"] == "tool" and message["content"] == "4" for message in transcript)

    async def respond(request):
        body = json.loads(request.content)
        results = []
        for call in body["input"] or []:
            result = outcome(call, "deny")
            result.update(decision="deferred", enforcement_mode="observe")
            results.append(result)
        return httpx.Response(200, json=results)

    async with client_for(respond) as client:
        results = await observe(client, "observed", messages)
    assert results and all(result.judged_decision == "deny" for result in results)


@pytest.mark.asyncio
async def test_mismatched_or_already_completed_input_is_never_submitted():
    async def respond(request):
        pytest.fail("Invalid tool identities must not reach Watcher")

    history = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "a", "function": "double", "arguments": {"value": 2}}],
        }
    ]
    async with client_for(respond) as client:
        monitor = Monitor(client, "identities")
        for call_id, name, arguments in [
            ("missing", "double", {"value": 2}),
            ("a", "wrong", {"value": 2}),
            ("a", "double", {"value": 3}),
        ]:
            with pytest.raises(ToolBlocked):
                await monitor.before_transcript(history, call_id, name, arguments)
        history.append({"role": "tool", "content": "4", "tool_call_id": "a"})
        with pytest.raises(ToolBlocked):
            await monitor.before_transcript(history, "a", "double", {"value": 2})


@pytest.mark.asyncio
@pytest.mark.parametrize("number, boolean", [(0, False), (1, True)])
async def test_boolean_arguments_do_not_match_numbers_before_sdk_submission(number, boolean):
    async def respond(request):
        pytest.fail("JSON literal type mismatches must fail before reaching Watcher")

    history = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "typed", "function": "double", "arguments": {"nested": [number]}}],
        }
    ]
    async with client_for(respond) as client:
        with pytest.raises(ToolBlocked):
            await Monitor(client, "typed").before_transcript(history, "typed", "double", {"nested": [boolean]})


@pytest.mark.asyncio
async def test_native_mixed_outcomes(tmp_path, record_property):
    sent = []

    async def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        call = body["input"]
        if call is None:
            return response(body)
        decision = "allow" if call["tool_input"].get("value") == 2 else "deny"
        return httpx.Response(200, json=outcome(call, decision))

    path = tmp_path / "side-effects"
    behavior = "returned"
    async with client_for(respond) as client:
        existing_tasks = asyncio.all_tasks()
        try:
            await run_conversation(Monitor(client, "mixed"), effect_for(path))
        except Exception as error:
            behavior = type(error).__name__
        siblings = asyncio.all_tasks() - existing_tasks
        if siblings:
            await asyncio.wait_for(asyncio.gather(*siblings, return_exceptions=True), 10)
    effects = path.read_text().splitlines() if path.exists() else []
    calls = [body["input"] for body in sent if body["input"] is not None]
    final_recorded = any(body["input"] is None for body in sent)
    record_property("native_behavior", behavior)
    record_property("side_effects", json.dumps(effects))
    record_property("grading_requests", len(calls))
    record_property("final_recorded", final_recorded)
    assert 1 <= len(calls) <= 2
    assert "3" not in effects
    assert set(effects) <= {"2"}
    assert (behavior == "returned") is False
    assert final_recorded is False
