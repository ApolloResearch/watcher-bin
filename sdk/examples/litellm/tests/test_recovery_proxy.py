"""Denial recovery through the real LiteLLM Router and official streaming clients.

Both the original completion and every alternative cross the provider HTTP
boundary. The provider advances only on native tool-result feedback, while a
separate Watcher endpoint supplies deterministic policy decisions.
"""

import json
from collections.abc import Iterator
from typing import Any, Literal

import anthropic
import openai
import pytest
from harness import litellm_proxy, serve_in_thread
from incremental_servers import API
from pydantic import BaseModel
from recovery_servers import RecoveryHolder, RecoveryState, provider_app, tool_feedback, watcher_app
from test_incremental_proxy import APIS, Frame, is_error, read_stream


class Reply(BaseModel):
    """The single final response assembled by an official provider SDK."""

    text: str
    call_ids: list[str]
    arguments: list[dict[str, Any]]


@pytest.fixture(scope="module")
def recovery_holder() -> RecoveryHolder:
    return RecoveryHolder()


@pytest.fixture
def recovery(recovery_holder: RecoveryHolder) -> Iterator[RecoveryState]:
    state = RecoveryState()
    recovery_holder.current = state
    recovery_holder.cases[state.case_id] = state
    yield state
    for gate in state.provider_gates:
        gate.set()
    for grade in tuple(state.grades.queue):
        grade.release.set()


@pytest.fixture(scope="module")
def recovery_proxy(recovery_holder: RecoveryHolder, tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    provider = serve_in_thread(provider_app(recovery_holder))
    watcher = serve_in_thread(watcher_app(recovery_holder))
    workdir = tmp_path_factory.mktemp("recovery-proxy")
    (workdir / "recovery_callback.py").write_text(
        "from watcher_litellm.callback import WatcherCallback\n"
        "callback = WatcherCallback(timeout_seconds=2, ping_seconds=0.1)\n"
    )
    models = [
        {
            "model_name": "gpt-test",
            "litellm_params": {"model": "openai/gpt-test", "api_base": f"{provider}/v1", "api_key": "k"},
        },
        {
            "model_name": "claude-test",
            "litellm_params": {"model": "anthropic/claude-test", "api_base": provider, "api_key": "k"},
        },
    ]
    with litellm_proxy(
        models,
        {"WATCHER_API_URL": watcher, "WATCHER_API_KEY": "fixture", "PYTHONPATH": str(workdir)},
        workdir,
        callback="recovery_callback.callback",
    ) as url:
        yield url


def request_reply(
    proxy: str, api: API, stream: bool, case_id: str, *, extra_body: dict[str, Any] | None = None
) -> Reply:
    """Assemble the entire client-visible response using each API's native SDK."""
    if api == "messages":
        with anthropic.Anthropic(
            base_url=proxy, api_key="fixture", max_retries=0, default_headers={"x-watcher-session-id": case_id}
        ) as client:
            if stream:
                with client.messages.stream(
                    model="claude-test",
                    max_tokens=100,
                    messages=[{"role": "user", "content": "Read a file."}],
                    extra_body=extra_body,
                ) as events:
                    message = events.get_final_message()
            else:
                message = client.messages.create(
                    model="claude-test",
                    max_tokens=100,
                    messages=[{"role": "user", "content": "Read a file."}],
                    extra_body=extra_body,
                )
        return Reply(
            text="".join(block.text for block in message.content if block.type == "text"),
            call_ids=[block.id for block in message.content if block.type == "tool_use"],
            arguments=[block.input for block in message.content if block.type == "tool_use"],
        )
    with openai.OpenAI(
        base_url=f"{proxy}/v1", api_key="fixture", max_retries=0, default_headers={"x-watcher-session-id": case_id}
    ) as client:
        if api == "responses":
            if stream:
                with client.responses.stream(model="gpt-test", input="Read a file.", extra_body=extra_body) as events:
                    response = events.get_final_response()
            else:
                response = client.responses.create(model="gpt-test", input="Read a file.", extra_body=extra_body)
            calls = [item for item in response.output if item.type == "function_call"]
            return Reply(
                text=response.output_text,
                call_ids=[call.call_id for call in calls],
                arguments=[json.loads(call.arguments) for call in calls],
            )
        if stream:
            with client.chat.completions.stream(
                model="gpt-test", messages=[{"role": "user", "content": "Read a file."}], extra_body=extra_body
            ) as events:
                completion = events.get_final_completion()
        else:
            completion = client.chat.completions.create(
                model="gpt-test", messages=[{"role": "user", "content": "Read a file."}], extra_body=extra_body
            )
        calls = completion.choices[0].message.tool_calls or []
        arguments = []
        for call in calls:
            assert call.type == "function"
            arguments.append(json.loads(call.function.arguments))
        return Reply(
            text=completion.choices[0].message.content or "",
            call_ids=[call.id for call in calls],
            arguments=arguments,
        )


def delivered_ids(api: API, frames: list[Frame]) -> list[str]:
    """Read executable call headers, excluding IDs quoted in ordinary notice text."""
    if api == "messages":
        return [
            frame.data["content_block"]["id"]
            for frame in frames
            if frame.data.get("type") == "content_block_start" and frame.data["content_block"]["type"] == "tool_use"
        ]
    if api == "responses":
        return [
            frame.data["item"]["call_id"]
            for frame in frames
            if frame.data.get("type") == "response.output_item.added" and frame.data["item"]["type"] == "function_call"
        ]
    return [
        call["id"]
        for frame in frames
        for choice in frame.data.get("choices", [])
        for call in choice["delta"].get("tool_calls") or []
        if call.get("id")
    ]


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("stream", [False, True], ids=["json", "stream"])
@pytest.mark.parametrize("decision", ["deny", "escalate"])
def test_blocked_call_is_replaced_with_one_allowed_alternative(
    recovery_proxy: str, recovery: RecoveryState, api: API, stream: bool, decision: Literal["deny", "escalate"]
) -> None:
    recovery.decisions = {"call_0_0": decision}

    reply = request_reply(recovery_proxy, api, stream, recovery.case_id)

    assert reply.call_ids == ["call_1_0"], reply.model_dump()
    assert reply.arguments == [{"path": "allowed-b"}]
    assert "read_file" in reply.text
    assert "blocked-a" in reply.text
    assert "Fixture blocks call_0_0." in reply.text
    assert len(recovery.provider_requests) == 2
    assert recovery.graded_ids == ["call_0_0", "call_1_0"]
    feedback = tool_feedback(api, recovery.provider_requests[1])
    assert "call_0_0" in feedback
    assert "in this proposal; the gateway withheld them" in feedback["call_0_0"]


@pytest.mark.parametrize(
    ("stream", "start", "end"),
    [
        (False, "prefix-0\n\nWatcher did not approve", "\n\nprefix-1"),
        (True, "prefix-0 \n\nWatcher did not approve", "\n\nprefix-1 "),
    ],
    ids=["json", "stream"],
)
def test_chat_recovery_notices_are_separate_paragraphs(
    recovery_proxy: str, recovery: RecoveryState, stream: bool, start: str, end: str
) -> None:
    reply = request_reply(recovery_proxy, "chat_completions", stream, recovery.case_id)

    assert reply.text.startswith(start)
    assert reply.text.endswith(end)
    assert reply.call_ids == ["call_1_0"]


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("stream", [False, True], ids=["json", "stream"])
@pytest.mark.parametrize("decision", ["deny", "escalate"])
def test_recovery_preserves_forced_tool_selection(
    recovery_proxy: str, recovery: RecoveryState, api: API, stream: bool, decision: Literal["deny", "escalate"]
) -> None:
    recovery.decisions = {"call_0_0": decision}
    schema = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
    if api == "messages":
        tools = [{"name": name, "input_schema": schema} for name in ["read_file", "delete_file"]]
        choice = {"type": "tool", "name": "read_file", "disable_parallel_tool_use": True}
    elif api == "chat_completions":
        tools = [
            {"type": "function", "function": {"name": name, "parameters": schema}}
            for name in ["read_file", "delete_file"]
        ]
        choice = {"type": "function", "function": {"name": "read_file"}}
    else:
        tools = [
            {"type": "function", "name": "read_file", "parameters": schema},
            {"type": "mcp", "server_label": "unused", "server_url": "https://example.invalid/mcp"},
        ]
        choice = {"type": "function", "name": "read_file"}

    reply = request_reply(
        recovery_proxy, api, stream, recovery.case_id, extra_body={"tools": tools, "tool_choice": choice}
    )

    assert reply.call_ids == ["call_1_0"]
    assert reply.arguments == [{"path": "allowed-b"}]
    assert len(recovery.provider_requests) == 2
    assert recovery.provider_requests[0]["tool_choice"] == choice
    assert recovery.provider_requests[1]["tool_choice"] == choice
    assert recovery.provider_requests[1]["tools"] == recovery.provider_requests[0]["tools"]


@pytest.mark.parametrize("api", APIS)
def test_second_alternative_is_allowed_after_two_distinct_denials(
    recovery_proxy: str, recovery: RecoveryState, api: API
) -> None:
    recovery.paths = [["blocked-a"], ["blocked-b"], ["allowed-c"]]
    recovery.decisions = {"call_0_0": "deny", "call_1_0": "deny"}

    reply = request_reply(recovery_proxy, api, True, recovery.case_id)

    assert reply.call_ids == ["call_2_0"]
    assert reply.arguments == [{"path": "allowed-c"}]
    assert len(recovery.provider_requests) == 3
    assert recovery.graded_ids == ["call_0_0", "call_1_0", "call_2_0"]
    feedback = tool_feedback(api, recovery.provider_requests[2])
    assert set(feedback) == {"call_0_0", "call_1_0"}


@pytest.mark.parametrize("api", APIS)
def test_third_blocked_attempt_finishes_normally_without_a_fourth_request(
    recovery_proxy: str, recovery: RecoveryState, api: API
) -> None:
    recovery.paths = [["blocked-a"], ["blocked-b"], ["blocked-c"]]
    recovery.decisions = {"call_0_0": "deny", "call_1_0": "escalate", "call_2_0": "deny"}

    reply = request_reply(recovery_proxy, api, True, recovery.case_id)

    assert reply.call_ids == []
    assert len(recovery.provider_requests) == 3
    assert "blocked-a" in reply.text
    assert "blocked-b" in reply.text
    assert "blocked-c" in reply.text
    assert "read_file" in reply.text
    assert "Fixture blocks call_2_0." in reply.text


@pytest.mark.parametrize("api", APIS)
def test_later_denial_does_not_repeat_or_claim_cancellation_of_an_allowed_call(
    recovery_proxy: str, recovery: RecoveryState, api: API
) -> None:
    recovery.paths = [["allowed-a", "blocked-b"], ["allowed-c"]]
    recovery.decisions = {"call_0_1": "deny"}

    reply = request_reply(recovery_proxy, api, True, recovery.case_id)

    assert reply.call_ids == ["call_0_0", "call_1_0"]
    assert reply.arguments == [{"path": "allowed-a"}, {"path": "allowed-c"}]
    assert recovery.graded_ids == ["call_0_0", "call_0_1", "call_1_0"]
    feedback = tool_feedback(api, recovery.provider_requests[1])
    assert "approved" in feedback["call_0_0"]
    assert "execution result is not yet available" in feedback["call_0_0"]
    assert "cancelled" not in feedback["call_0_0"]
    assert "No tool was run." not in reply.text


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("decision", ["deny", "escalate"])
def test_denied_operation_cannot_be_released_under_a_fresh_call_id(
    recovery_proxy: str, recovery: RecoveryState, api: API, decision: Literal["deny", "escalate"]
) -> None:
    recovery.paths = [["blocked-a"], ["blocked-a"], ["allowed-c"]]
    recovery.decisions["call_0_0"] = decision

    reply = request_reply(recovery_proxy, api, True, recovery.case_id)

    assert reply.call_ids == ["call_2_0"]
    assert reply.arguments == [{"path": "allowed-c"}]
    assert recovery.graded_ids == ["call_0_0", "call_2_0"]
    assert len(recovery.provider_requests) == 3
    repeated_feedback = tool_feedback(api, recovery.provider_requests[2])["call_1_0"]
    assert f'"is_escalation": {str(decision == "escalate").lower()}' in repeated_feedback
    assert "in this proposal; the gateway withheld them" in repeated_feedback


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("decision", ["deny", "escalate"])
def test_recovery_withholds_a_duplicate_within_one_streamed_alternative(
    recovery_proxy: str, recovery: RecoveryState, api: API, decision: Literal["deny", "escalate"]
) -> None:
    recovery.paths = [["blocked-a"], ["allowed-b", "allowed-b"], ["allowed-c"]]
    recovery.decisions = {"call_0_0": decision}

    reply = request_reply(recovery_proxy, api, True, recovery.case_id)

    assert reply.call_ids == ["call_1_0", "call_2_0"]
    assert reply.arguments == [{"path": "allowed-b"}, {"path": "allowed-c"}]
    assert recovery.graded_ids == ["call_0_0", "call_1_0", "call_2_0"]
    assert len(recovery.provider_requests) == 3
    feedback = tool_feedback(api, recovery.provider_requests[2])
    assert "execution result is not yet available" in feedback["call_1_0"]
    assert "already approved and sent to the client" in feedback["call_1_1"]
    assert "must not be executed again" in feedback["call_1_1"]
    assert "No tool was run." not in reply.text


@pytest.mark.parametrize("api", APIS)
def test_original_proposal_can_repeat_allowed_operations(
    recovery_proxy: str, recovery: RecoveryState, api: API
) -> None:
    recovery.paths = [["allowed-a", "allowed-a"]]
    recovery.decisions = {}

    reply = request_reply(recovery_proxy, api, True, recovery.case_id)

    assert reply.call_ids == ["call_0_0", "call_0_1"]
    assert reply.arguments == [{"path": "allowed-a"}, {"path": "allowed-a"}]
    assert recovery.graded_ids == ["call_0_0", "call_0_1"]
    assert len(recovery.provider_requests) == 1


@pytest.mark.parametrize("api", APIS)
def test_original_and_replacement_prefixes_stream_before_their_grades(
    recovery_proxy: str, recovery: RecoveryState, api: API
) -> None:
    recovery.gate_tools = True
    recovery.gate_grades = True
    with read_stream(recovery_proxy, api, recovery.case_id) as reader:
        reader.through(lambda frame: "prefix-0" in frame.wire)
        assert recovery.graded_ids == []
        recovery.provider_gates[0].set()
        first = recovery.grades.get(timeout=10)
        assert first.ids == ["call_0_0"]
        reader.through(lambda frame: frame.is_keepalive)
        assert delivered_ids(api, reader.frames) == []
        first.release.set()
        reader.through(lambda frame: "prefix-1" in frame.wire)
        assert recovery.graded_ids == ["call_0_0"]
        assert delivered_ids(api, reader.frames) == []
        recovery.provider_gates[1].set()
        second = recovery.grades.get(timeout=10)
        assert second.ids == ["call_1_0"]
        reader.through(lambda frame: frame.is_keepalive)
        assert delivered_ids(api, reader.frames) == []
        second.release.set()
        reader.finish()
        assert delivered_ids(api, reader.frames) == ["call_1_0"]
        assert not any(is_error(frame) for frame in reader.frames)
        events = [frame.data for frame in reader.frames if frame.data]
        if api == "messages":
            assert sum(event["type"] == "message_start" for event in events) == 1
            assert sum(event["type"] == "message_stop" for event in events) == 1
            indices = [event["index"] for event in events if event["type"] == "content_block_start"]
            assert indices == list(range(len(indices)))
        elif api == "responses":
            assert sum(event["type"] == "response.created" for event in events) == 1
            assert sum(event["type"] == "response.completed" for event in events) == 1
            sequences = [event["sequence_number"] for event in events]
            assert sequences == sorted(set(sequences))
            indices = [event["output_index"] for event in events if event["type"] == "response.output_item.added"]
            assert indices == list(range(len(indices)))
        else:
            assert len({event["id"] for event in events}) == 1
            assert sum(choice["finish_reason"] is not None for event in events for choice in event["choices"]) == 1


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("fault", ["server_error", "timeout"])
def test_watcher_transport_failure_does_not_generate_an_alternative(
    recovery_proxy: str, recovery: RecoveryState, api: API, fault: str
) -> None:
    recovery.watcher_status = 503 if fault == "server_error" else 200
    recovery.gate_grades = fault == "timeout"
    with read_stream(recovery_proxy, api, recovery.case_id) as reader:
        reader.through(is_error)
        reader.finish()
        assert delivered_ids(api, reader.frames) == []
        assert len(recovery.provider_requests) == 1


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("held_stage", ["provider", "grading"])
def test_recovery_keeps_the_first_refusal_deadline(
    recovery_proxy: str, recovery: RecoveryState, api: API, held_stage: str, record_property: Any
) -> None:
    """The real proxy spends one budget across a slow denial and its streamed alternative."""
    recovery.gate_tools = True
    recovery.gate_grades = True
    recovery.provider_gates[0].set()
    with read_stream(recovery_proxy, api, recovery.case_id) as reader:
        first = recovery.grades.get(timeout=10)
        assert first.ids == ["call_0_0"]
        waited = reader.through(lambda frame: frame.is_keepalive and frame.received - first.started >= 1.1)
        assert delivered_ids(api, reader.frames) == []
        first.release.set()
        reader.through(lambda frame: "prefix-1" in frame.wire)
        second = None
        if held_stage == "grading":
            recovery.provider_gates[1].set()
            second = recovery.grades.get(timeout=10)
            assert second.ids == ["call_1_0"]
        error = reader.through(is_error)
        reader.finish()
        elapsed = error.received - first.started
        remaining = error.received - waited.received
        record_property("recovery_total_seconds", elapsed)
        record_property("recovery_remaining_seconds", remaining)
        assert 1.8 < elapsed < 2.6
        assert remaining < 1.5, "recovery incorrectly restarted the two-second evaluation budget"
        assert "timed out" in error.wire
        assert delivered_ids(api, reader.frames) == []
        assert len(recovery.provider_requests) == 2
        assert any(frame.is_keepalive and frame.received > waited.received for frame in reader.frames)
        if second is not None:
            second.release.set()


@pytest.mark.parametrize("api", APIS)
def test_nonstream_provider_recovery_failure_returns_a_sanitized_502(
    recovery_proxy: str, recovery: RecoveryState, api: API
) -> None:
    recovery.reject_replacements = True
    with pytest.raises((openai.APIStatusError, anthropic.APIStatusError)) as error:
        request_reply(recovery_proxy, api, False, recovery.case_id)
    assert error.value.status_code == 502
    assert "Model response could not be completed during gateway recovery" in str(error.value)
    assert "private provider diagnostic" not in str(error.value)
    assert recovery.graded_ids == ["call_0_0"]
    assert len(recovery.provider_requests) == 2
