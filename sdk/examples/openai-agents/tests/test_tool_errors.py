"""Calls whose tools failed reach Watcher with the tool message's error set.

Watcher records a call it let through whose later result has no error as
completed, and Responses function_call_output items carry no failure flag, so
the adapter must mark every execution failure it knows of. Refusals and
cancellations are never marked this way: they are reported as decision
statuses (test_configured_policy.py), so their results stay unmarked here.
"""

import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import pytest
from agents import RunContextWrapper, function_tool
from demo.enforce import run_conversation
from demo.observe import DeterministicModel
from watcher_openai_agents.adapter import mark_tool_errors, messages_for_watcher, observe
from watcher_openai_agents.monitoring import Monitor
from watcher_openai_agents.native import execute_tool, failure_error_function

from watcher_sdk import AsyncWatcherClient, WatcherTimeoutError

VERDICT = {"severity_score": None, "severity_label": None, "summary": "Fixture", "explanation": "Fixture"}


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


def enforced(call, decision):
    return {
        "decision": decision,
        "judged_decision": decision,
        "enforcement_mode": "enforce",
        "decision_source": "rule",
        "tool_use_id": call["tool_use_id"],
        "latency_ms": 1,
        "verdict": VERDICT,
    }


def recorder(sent):
    """Allow every call and keep each hook request body; this fixture serves no other endpoint."""

    async def respond(request):
        assert request.url.path == "/v1/hooks/pre-tool-use"
        body = json.loads(request.content)
        sent.append(body)
        call = body["input"]
        if call is None:
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=enforced(call, "allow"))

    return respond


def tool_results(messages):
    return {message["tool_call_id"]: message for message in messages if message["role"] == "tool"}


FAILED_HISTORY = [
    {"role": "user", "content": "Double 2 and 3"},
    {"type": "function_call", "call_id": "double-2", "name": "double", "arguments": '{"value":2}'},
    {"type": "function_call", "call_id": "double-3", "name": "double", "arguments": '{"value":3}'},
    {"type": "function_call_output", "call_id": "double-2", "output": "4"},
    {"type": "function_call_output", "call_id": "double-3", "output": "Tool raised: disk full"},
]


def test_converter_marks_only_the_calls_it_is_told_failed():
    failed = {"type": "unknown", "message": "Disk full"}
    results = tool_results(messages_for_watcher(FAILED_HISTORY, {"double-3": failed}))
    assert results["double-3"]["error"] == failed
    assert results["double-3"]["content"] == "Tool raised: disk full"
    assert "error" not in results["double-2"]


def test_converter_cannot_tell_an_unmarked_failure_from_a_result():
    assert all("error" not in result for result in tool_results(messages_for_watcher(FAILED_HISTORY)).values())


@pytest.mark.asyncio
async def test_observe_sends_supplied_errors_with_the_final_transcript():
    sent = []

    async def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        outcomes = []
        for call in body["input"] or []:
            outcome = enforced(call, "allow")
            outcome.update(decision="deferred", enforcement_mode="observe")
            outcomes.append(outcome)
        return httpx.Response(200, json=outcomes)

    error = {"type": "unknown", "message": "Tool raised"}
    async with client_for(respond) as client:
        await observe(client, "observed", FAILED_HISTORY, {"double-3": error})
    final = tool_results(sent[-1]["messages"])
    assert sent[-1]["input"] is None
    assert final["double-3"]["error"] == error
    assert "error" not in final["double-2"]


@pytest.mark.asyncio
async def test_runner_tool_failure_is_recorded_with_an_error_and_success_without():
    def effect(value):
        if value == 3:
            raise RuntimeError("Disk full")
        return str(value * 2)

    sent = []
    async with client_for(recorder(sent)) as client:
        monitor = Monitor(client, "runner-failure")
        history = await run_conversation(monitor, effect)
    final = tool_results(sent[-1]["messages"])
    assert sent[-1]["input"] is None
    assert final["double-3"]["error"] == {"type": "unknown", "message": "Disk full"}
    assert "Disk full" in final["double-3"]["content"]
    assert final["double-2"] == {"role": "tool", "content": "4", "tool_call_id": "double-2", "function": "double"}
    assert tool_results(messages_for_watcher(history, monitor.errors)) == final


async def dispatch(monitor, tool):
    """Run the dispatch loop the application owns, giving the model a result even for a withheld call."""
    model = DeterministicModel()
    history = [{"role": "user", "content": "Double 2 and 3"}]
    response = await model.get_response(None, history, None, [tool], None, [], None)
    history.extend(item.model_dump(exclude_none=True) for item in response.output)
    outcomes = await asyncio.gather(
        *(execute_tool(monitor, history, tool, call) for call in response.output), return_exceptions=True
    )
    for call, outcome in zip(response.output, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            outcome = {"type": "function_call_output", "call_id": call.call_id, "output": "The call did not run"}
        history.append(outcome)
    response = await model.get_response(None, history, None, [tool], None, [], None)
    history.extend(item.model_dump(exclude_none=True) for item in response.output)
    await monitor.record(history)
    return outcomes


@pytest.mark.asyncio
async def test_dispatched_tool_exception_is_recorded_with_an_error():
    @function_tool(failure_error_function=None)
    def double(value: int) -> str:
        """Double an integer."""
        if value == 3:
            raise RuntimeError("Disk full")
        return str(value * 2)

    sent = []
    async with client_for(recorder(sent)) as client:
        outcomes = await dispatch(Monitor(client, "dispatch-failure"), double)
    assert isinstance(outcomes[1], Exception)
    final = tool_results(sent[-1]["messages"])
    assert final["double-3"]["error"] == {"type": "unknown", "message": "Disk full"}
    assert "error" not in final["double-2"]


@pytest.mark.asyncio
async def test_a_monitoring_failure_is_not_marked_as_a_tool_error():
    """The withheld call never ran: it is reported blocked after record() (test_withheld_calls.py), never as failed."""
    sent = []
    allow = recorder(sent)

    async def respond(request):
        if json.loads(request.content)["input"]["tool_use_id"] == "a":
            raise httpx.ReadTimeout("Fixture timeout", request=request)
        return await allow(request)

    history = [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "function": "double", "arguments": {}}]},
    ]
    async with client_for(respond) as client:
        monitor = Monitor(client, "transport")
        with pytest.raises(WatcherTimeoutError):
            await monitor.before_transcript(history, "a", "double", {})
        history += [
            {"role": "tool", "content": "The call did not run", "tool_call_id": "a"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "b", "function": "double", "arguments": {}}]},
        ]
        await monitor.before_transcript(history, "b", "double", {})
    assert monitor.errors == {}
    assert "error" not in tool_results(sent[-1]["messages"])["a"]


@pytest.mark.asyncio
@pytest.mark.parametrize("supplied", [{}, {"error": None}])
async def test_a_failed_result_gets_its_error_whether_error_is_absent_or_null(supplied):
    """Normalized Inspect messages say "no error" with ``error: None``; that must not hide a known failure."""
    sent = []
    history = [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "function": "double", "arguments": {}}]},
        {"role": "tool", "content": "Tool raised: disk full", "tool_call_id": "a", **supplied},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "b", "function": "double", "arguments": {}}]},
    ]
    async with client_for(recorder(sent)) as client:
        monitor = Monitor(client, "caught-failure")
        monitor.mark_failed("a", "Disk full")
        await monitor.before_transcript(history, "b", "double", {})
    assert tool_results(sent[-1]["messages"])["a"]["error"] == {"type": "unknown", "message": "Disk full"}
    assert history[1].get("error") is None


def test_an_error_already_on_the_message_is_kept():
    existing = {"type": "permission", "message": "Blocked by the sandbox"}
    transcript = [{"role": "tool", "content": "Blocked", "tool_call_id": "a", "error": existing}]
    mark_tool_errors(transcript, {"a": {"type": "unknown", "message": "Disk full"}})
    assert transcript[0]["error"] == existing


@pytest.mark.asyncio
async def test_cancelling_before_watcher_answers_uploads_nothing_until_record():
    """Watcher may not have stored the call yet, so its cancellation is queued for record() (test_withheld_calls.py)."""
    entered, paths = asyncio.Event(), []

    async def respond(request):
        paths.append(request.url.path)
        entered.set()
        await asyncio.Event().wait()

    history = [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "function": "double", "arguments": {}}]},
    ]
    async with client_for(respond) as client:
        monitor = Monitor(client, "cancelled")
        task = asyncio.create_task(monitor.before_transcript(history, "a", "double", {}))
        await asyncio.wait_for(entered.wait(), 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await monitor.report_status("a", "double", {}, "cancelled") is False
    assert paths == ["/v1/hooks/pre-tool-use"]
    assert monitor.unreported == {"a": ("double", {}, "cancelled")}
    assert monitor.errors == {}


def test_failure_function_needs_the_native_tool_context():
    monitor = Monitor(object(), "context")
    with pytest.raises(ValueError):
        failure_error_function(monitor)(RunContextWrapper(context=None), RuntimeError("Disk full"))
    assert monitor.errors == {}
