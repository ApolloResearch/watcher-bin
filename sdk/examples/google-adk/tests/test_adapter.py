"""Exercise native framework execution and the public Watcher SDK transport."""

import json
from copy import deepcopy

import httpx
import pytest
from demo.observe import run_conversation
from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types
from watcher_google_adk.adapter import IncompleteObservationError, messages_for_watcher, observe

from watcher_sdk import AsyncWatcherClient, WatcherValidationError


@pytest.mark.asyncio
async def test_native_tools_and_final_answer_reach_monitor():
    history = await run_conversation()
    before = deepcopy(history)
    transcript = messages_for_watcher(history)
    assert transcript[0] == {"role": "system", "content": 'You are an agent. Your internal name is "example".'}
    assert transcript[1] == {"role": "user", "content": "Double 2 and 3"}
    assert transcript[-1] == {"role": "assistant", "content": "4 and 6"}
    calls = [call for message in transcript for call in message.get("tool_calls", [])]
    assert calls == [
        {"id": "double-2", "function": "double", "arguments": {"value": 2}},
        {"id": "double-3", "function": "double", "arguments": {"value": 3}},
    ]
    results = [message for message in transcript if message["role"] == "tool"]
    assert results == [
        {"role": "tool", "content": "4", "tool_call_id": "double-2", "function": "double"},
        {"role": "tool", "content": "6", "tool_call_id": "double-3", "function": "double"},
    ]
    sent = []

    async def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        assert "require_recording" not in request.url.params
        outcomes = [
            {
                "decision": "deferred",
                "judged_decision": "allow",
                "decision_source": "rule",
                "enforcement_mode": "observe",
                "tool_use_id": call["tool_use_id"],
                "verdict": {
                    "severity_score": None,
                    "severity_label": None,
                    "summary": "Allowed",
                    "explanation": "fixture",
                },
                "latency_ms": 1,
            }
            for call in body["input"] or []
        ]
        return httpx.Response(200, json=outcomes)

    async with (
        httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(respond)) as transport,
        AsyncWatcherClient(
            "https://watcher.invalid", httpx_client=transport, manage_external_httpx_client_lifecycle=False
        ) as client,
    ):
        await observe(client, "one", history[:-1])
        outcomes = await observe(client, "one", history)
    assert history == before
    final_uploads = [body for body in sent if body["input"] is None]
    evaluations = [body for body in sent if body["input"] is not None]
    last_inputs = [call for body in evaluations for call in body["input"]][-len(outcomes) :]
    assert len(final_uploads) == 2
    assert final_uploads[0]["messages"] == transcript[:-1]
    assert final_uploads[1]["messages"] == transcript
    assert final_uploads[1]["external_ids"] == {"other": "google-adk:one"}
    assert last_inputs == [
        {"tool_name": "double", "tool_input": {"value": 2}, "tool_use_id": "double-2"},
        {"tool_name": "double", "tool_input": {"value": 3}, "tool_use_id": "double-3"},
    ]
    assert "settings_overrides" not in evaluations[-1]
    assert final_uploads[1]["input"] is None
    assert [item.judged_decision for item in outcomes] == ["allow", "allow"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing-outcomes", "http-error"])
async def test_observation_failure_does_not_reexecute_native_tools(failure):
    history = await run_conversation()

    async def respond(request):
        return (
            httpx.Response(200, json=[])
            if failure == "missing-outcomes"
            else httpx.Response(422, json={"detail": [{"loc": ["body"], "msg": "rejected", "type": "value_error"}]})
        )

    async with (
        httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(respond)) as transport,
        AsyncWatcherClient(
            "https://watcher.invalid", httpx_client=transport, manage_external_httpx_client_lifecycle=False
        ) as client,
    ):
        with pytest.raises(IncompleteObservationError if failure == "missing-outcomes" else WatcherValidationError):
            await observe(client, "one", history)
    assert messages_for_watcher(history)[-1]["content"] == "4 and 6"


@pytest.mark.asyncio
async def test_complete_snapshots_not_delta_are_required():
    history = await run_conversation()
    with pytest.raises(ValueError):
        messages_for_watcher(history[-2:])
    assert messages_for_watcher(history)[-1]["content"] == "4 and 6"


@pytest.mark.asyncio
async def test_source_is_not_mutated_by_conversion():
    history = await run_conversation()
    before = deepcopy(history)
    messages = messages_for_watcher(history)
    for item in messages:
        for call in item.get("tool_calls", []):
            call["arguments"]["value"] = 99
    assert history == before


def test_unknown_native_message_rejected():
    with pytest.raises(ValueError):
        messages_for_watcher([object()])


@pytest.mark.asyncio
async def test_empty_identity_rejected_before_network():
    async with AsyncWatcherClient("https://watcher.invalid") as client:
        with pytest.raises(ValueError):
            await observe(client, "", [])


def test_empty_history_supported():
    assert messages_for_watcher([]) == []


class DictionaryResultModel(BaseLlm):
    """Request one argument-free native tool, then finish after its dictionary result."""

    async def generate_content_async(self, llm_request, stream=False):
        if any(part.function_response for content in llm_request.contents for part in content.parts or []):
            content = types.Content(role="model", parts=[types.Part(text="Done")])
        else:
            content = types.Content(
                role="model",
                parts=[types.Part(function_call=types.FunctionCall(id="status-call", name="status", args=None))],
            )
        yield LlmResponse(content=content)


@pytest.mark.asyncio
async def test_native_adk_dictionary_tool_and_absent_arguments():
    def status() -> dict:
        """Return a structured native tool result without arguments."""
        return {"status": "ok", "value": 4, "nested": {"ready": True}}

    runner = InMemoryRunner(
        agent=LlmAgent(name="dictionary_example", model=DictionaryResultModel(model="deterministic"), tools=[status]),
        app_name="dictionary-example",
    )
    session = await runner.session_service.create_session(app_name="dictionary-example", user_id="test")
    async for _event in runner.run_async(
        user_id="test",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="Get status")]),
    ):
        pass
    session = await runner.session_service.get_session(
        app_name="dictionary-example",
        user_id="test",
        session_id=session.id,
    )
    assert session is not None
    history = [event.content for event in session.events if event.content is not None]
    transcript = messages_for_watcher(history)
    calls = [call for message in transcript for call in message.get("tool_calls", [])]
    assert calls == [{"id": "status-call", "function": "status", "arguments": {}}]
    result = next(message for message in transcript if message["role"] == "tool")
    assert result["tool_call_id"] == "status-call"
    assert json.loads(result["content"]) == status()
    assert transcript[-1] == {"role": "assistant", "content": "Done"}


@pytest.mark.parametrize("payload", [{"nested": [1, True, None]}, [1, "two"], 4, None])
def test_adk_wrapped_json_results_are_serialized_losslessly(payload):
    history = [
        types.Content(
            role="model", parts=[types.Part(function_call=types.FunctionCall(id="x", name="status", args=None))]
        ),
        types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id="x",
                        name="status",
                        response={"result": payload},
                    )
                )
            ],
        ),
    ]
    before = deepcopy(history)
    transcript = messages_for_watcher(history)
    assert transcript[0]["tool_calls"][0]["arguments"] == {}
    assert json.loads(transcript[1]["content"]) == payload
    assert history == before


def _function_response_history(response):
    """One argument-free native call answered by the given ADK function response object."""
    return [
        types.Content(
            role="model", parts=[types.Part(function_call=types.FunctionCall(id="x", name="status", args=None))]
        ),
        types.Content(
            role="user",
            parts=[types.Part(function_response=types.FunctionResponse(id="x", name="status", response=response))],
        ),
    ]


@pytest.mark.parametrize(
    "response, message",
    [
        ({"error": "Tool execution was denied"}, "Tool execution was denied"),
        (
            {"error": "Invoking `double()` failed with an internal error."},
            "Invoking `double()` failed with an internal error.",
        ),
        ({"error": {"code": 403, "reason": "denied"}}, '{"code": 403, "reason": "denied"}'),
    ],
)
def test_adk_error_responses_mark_the_tool_message_and_keep_their_content(response, message):
    history = _function_response_history(response)
    before = deepcopy(history)
    result = messages_for_watcher(history)[1]
    assert result["error"] == {"type": "unknown", "message": message}
    assert json.loads(result["content"]) == response
    assert history == before


@pytest.mark.parametrize(
    "response", [{"result": "4"}, {"status": "ok"}, {"error": None}, {"error": ""}, {"result": {"error": "x"}}]
)
def test_adk_responses_without_a_truthy_error_key_have_no_tool_error(response):
    assert "error" not in messages_for_watcher(_function_response_history(response))[1]


class MissingArgumentModel(BaseLlm):
    """Call a tool without its mandatory argument, then finish after ADK's error response."""

    async def generate_content_async(self, llm_request, stream=False):
        if any(part.function_response for content in llm_request.contents for part in content.parts or []):
            content = types.Content(role="model", parts=[types.Part(text="Could not double")])
        else:
            content = types.Content(
                role="model",
                parts=[types.Part(function_call=types.FunctionCall(id="double-missing", name="double", args={}))],
            )
        yield LlmResponse(content=content)


@pytest.mark.asyncio
async def test_native_adk_refusal_reaches_watcher_as_a_tool_error():
    effects = []

    def double(value: int) -> str:
        """Return twice the supplied integer."""
        effects.append(value)
        return str(value * 2)

    runner = InMemoryRunner(
        agent=LlmAgent(name="refusal_example", model=MissingArgumentModel(model="deterministic"), tools=[double]),
        app_name="refusal-example",
    )
    session = await runner.session_service.create_session(app_name="refusal-example", user_id="test")
    async for _event in runner.run_async(
        user_id="test",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="Double something")]),
    ):
        pass
    session = await runner.session_service.get_session(
        app_name="refusal-example", user_id="test", session_id=session.id
    )
    assert session is not None
    history = [event.content for event in session.events if event.content is not None]
    sent = []

    async def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        return httpx.Response(
            200,
            json=[
                {
                    "decision": "deferred",
                    "judged_decision": "allow",
                    "decision_source": "rule",
                    "enforcement_mode": "observe",
                    "tool_use_id": call["tool_use_id"],
                    "verdict": {
                        "severity_score": None,
                        "severity_label": None,
                        "summary": "Allowed",
                        "explanation": "fixture",
                    },
                    "latency_ms": 1,
                }
                for call in body["input"] or []
            ],
        )

    async with (
        httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(respond)) as transport,
        AsyncWatcherClient(
            "https://watcher.invalid", httpx_client=transport, manage_external_httpx_client_lifecycle=False
        ) as client,
    ):
        await observe(client, "refusal", history)
    assert effects == []
    result = next(message for message in sent[-1]["messages"] if message["role"] == "tool")
    assert result["tool_call_id"] == "double-missing"
    assert result["error"]["type"] == "unknown"
    assert "mandatory input parameters are not present" in result["error"]["message"]
    assert json.loads(result["content"]) == {"error": result["error"]["message"]}


PLACEHOLDER = {"error": "This tool call requires confirmation, please approve or reject."}


def confirmation_history(answer=None, final=None):
    """ADK's events for one call that asked for confirmation, as a real 2.8 run writes them.

    ``answer`` is the confirmation response (None: unanswered) and ``final`` the
    original call's response after it.
    """
    request = types.FunctionCall(
        id="confirm-1",
        name="adk_request_confirmation",
        args={
            "originalFunctionCall": {"id": "double-2", "name": "double", "args": {"value": 2}},
            "toolConfirmation": {"hint": "Approve?", "confirmed": False},
        },
    )
    history = [
        types.Content(role="user", parts=[types.Part(text="Double 2")]),
        types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(id="double-2", name="double", args={"value": 2}))],
        ),
        types.Content(role="model", parts=[types.Part(function_call=request)]),
        types.Content(
            role="user",
            parts=[
                types.Part(function_response=types.FunctionResponse(id="double-2", name="double", response=PLACEHOLDER))
            ],
        ),
    ]
    if answer is not None:
        history += [
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id="confirm-1", name="adk_request_confirmation", response=answer
                        )
                    )
                ],
            ),
            types.Content(
                role="user",
                parts=[
                    types.Part(function_response=types.FunctionResponse(id="double-2", name="double", response=final))
                ],
            ),
        ]
    return history


@pytest.mark.parametrize(
    "answer, final, expected",
    [
        ({"confirmed": False}, {"error": "This tool call is rejected."}, '{"error": "This tool call is rejected."}'),
        (
            {"response": '{"confirmed": false}'},
            {"error": "This tool call is rejected."},
            '{"error": "This tool call is rejected."}',
        ),
        ({"confirmed": True}, {"result": "4"}, "4"),
    ],
)
def test_confirmation_keeps_only_the_final_result_and_never_marks_a_rejection(answer, final, expected):
    transcript = messages_for_watcher(confirmation_history(answer, final))
    assert transcript == [
        {"role": "user", "content": "Double 2"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "double-2", "function": "double", "arguments": {"value": 2}}],
        },
        {"role": "tool", "content": expected, "tool_call_id": "double-2", "function": "double"},
    ]


def replayed(answer, response=None):
    """A replayed confirmation answer, followed by ADK's response to it when it gives one."""
    history = [
        types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id="confirm-1", name="adk_request_confirmation", response=answer
                    )
                )
            ],
        )
    ]
    if response is not None:
        history.append(
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(id="double-2", name="double", response=response)
                    )
                ],
            )
        )
    return history


def test_a_replayed_approval_keeps_the_result_of_the_first():
    history = confirmation_history({"confirmed": True}, {"result": "4"}) + replayed({"confirmed": True})
    assert messages_for_watcher(history)[-1] == {
        "role": "tool",
        "content": "4",
        "tool_call_id": "double-2",
        "function": "double",
    }


def test_answers_replayed_after_a_rejection_keep_one_unmarked_refusal():
    rejection = {"error": "This tool call is rejected."}
    history = (
        confirmation_history({"confirmed": False}, rejection)
        + replayed({"confirmed": True})
        + replayed({"confirmed": False}, rejection)
    )
    results = [message for message in messages_for_watcher(history) if message["role"] == "tool"]
    assert results == [
        {"role": "tool", "content": json.dumps(rejection), "tool_call_id": "double-2", "function": "double"}
    ]


REJECTION = {"error": "This tool call is rejected."}


@pytest.mark.parametrize("confirmations, refused", [({"double-2": False}, True), (None, False), ({}, False)])
def test_a_refused_approval_then_an_accepted_rejection(confirmations, refused):
    """The callback refused the approval, so ADK wrote nothing until the later rejection.

    The callback's record says the rejection took effect, so its response is
    ADK's refusal. Without that record the answers are mixed and the result
    keeps its ``error``, as it does for a call the record does not name.
    """
    history = confirmation_history() + replayed({"confirmed": True}) + replayed({"confirmed": False}, REJECTION)
    results = [message for message in messages_for_watcher(history, confirmations) if message["role"] == "tool"]
    expected: dict = {
        "role": "tool",
        "content": json.dumps(REJECTION),
        "tool_call_id": "double-2",
        "function": "double",
    }
    if not refused:
        expected["error"] = {"type": "unknown", "message": REJECTION["error"]}
    assert results == [expected]


@pytest.mark.parametrize("confirmations", [{"double-2": True}, None])
def test_a_failed_run_keeps_its_error_when_a_refused_rejection_lands_before_it(confirmations):
    """An approved tool is still running when a replayed rejection arrives; the callback refuses it.

    The run then fails through on_tool_error_callback. Its result follows the
    rejection in the history but answers the approval.
    """
    history = (
        confirmation_history() + replayed({"confirmed": True}) + replayed({"confirmed": False}, {"error": "Disk full"})
    )
    result = messages_for_watcher(history, confirmations)[-1]
    assert result["error"] == {"type": "unknown", "message": "Disk full"}


def test_a_tool_that_fails_after_its_confirmation_is_still_an_execution_failure():
    result = messages_for_watcher(confirmation_history({"confirmed": True}, {"error": "Disk full"}))[-1]
    assert result["error"] == {"type": "unknown", "message": "Disk full"}


def test_an_unanswered_confirmation_leaves_the_call_without_a_result():
    transcript = messages_for_watcher(confirmation_history())
    assert [message["role"] for message in transcript] == ["user", "assistant"]
    assert transcript[1]["tool_calls"] == [{"id": "double-2", "function": "double", "arguments": {"value": 2}}]


def test_malformed_confirmations_are_rejected():
    orphan = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id="unknown", name="adk_request_confirmation", response={"confirmed": True}
                )
            )
        ],
    )
    with pytest.raises(ValueError, match="without its request"):
        messages_for_watcher([orphan])
    request = types.Content(
        role="model",
        parts=[types.Part(function_call=types.FunctionCall(id="c", name="adk_request_confirmation", args={}))],
    )
    with pytest.raises(ValueError, match="without its original call"):
        messages_for_watcher([request])


@pytest.mark.asyncio
async def test_observe_refuses_a_rejected_confirmation_it_cannot_report_but_imports_an_approved_one():
    sent = []

    async def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        return httpx.Response(
            200,
            json=[
                {
                    "decision": "deferred",
                    "judged_decision": "allow",
                    "decision_source": "rule",
                    "enforcement_mode": "observe",
                    "tool_use_id": call["tool_use_id"],
                    "verdict": {
                        "severity_score": None,
                        "severity_label": None,
                        "summary": "Fixture",
                        "explanation": "Fixture",
                    },
                    "latency_ms": 1,
                }
                for call in body["input"] or []
            ],
        )

    rejected = confirmation_history({"confirmed": False}, {"error": "This tool call is rejected."})
    approved = confirmation_history({"confirmed": True}, {"result": "4"})
    async with (
        httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(respond)) as transport,
        AsyncWatcherClient(
            "https://watcher.invalid", httpx_client=transport, manage_external_httpx_client_lifecycle=False
        ) as client,
    ):
        with pytest.raises(ValueError, match="rejected tool confirmation"):
            await observe(client, "rejected", rejected)
        assert sent == []
        await observe(client, "approved", approved)
    assert sent[-1]["messages"] == messages_for_watcher(approved)
