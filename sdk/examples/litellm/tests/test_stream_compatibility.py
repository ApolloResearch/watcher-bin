"""Preserve supported native call shapes and provider metadata in incremental streams.

Fixtures model the public wire events, and official SDK accumulators check the
forwarded result. Client calls require approval at item completion; provider-run
tools remain ordinary streamed context and cannot borrow another item's family.
"""

import json
from copy import deepcopy
from typing import Any

import openai
import pytest
from anthropic.lib.streaming._messages import accumulate_event
from anthropic.types import RawMessageStreamEvent
from openai._streaming import SSEDecoder
from openai.lib.streaming.responses._responses import ResponseStreamState
from openai.types.responses import ResponseStreamEvent
from pydantic import TypeAdapter
from watcher_litellm.delivery import StreamDelivery
from watcher_litellm.incremental import IncrementalStream, wire_event
from watcher_litellm.streams import UnsupportedStream, assemble, encode


def responses_body(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "resp_compatibility",
        "object": "response",
        "created_at": 1,
        "model": "fixture",
        "status": "completed",
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "output": items,
    }


def responses_start() -> dict[str, Any]:
    return {
        "type": "response.created",
        "response": {**responses_body([]), "status": "in_progress"},
        "sequence_number": 0,
    }


def native_call(kind: str) -> dict[str, Any]:
    if kind == "local_shell_call":
        return {
            "type": kind,
            "id": "shell_item",
            "call_id": "shell_call",
            "status": "completed",
            "action": {"type": "exec", "command": ["pwd"], "env": {}},
        }
    return {
        "type": "tool_search_call",
        "id": "search_item",
        "call_id": "search_call",
        "execution": "client",
        "status": "completed",
        "arguments": {"query": "lookup", "limit": 1},
    }


def official_responses(output: list[bytes]) -> dict[str, Any]:
    stream = ResponseStreamState(input_tools=[], text_format=openai.omit)
    final = None
    for sse in SSEDecoder().iter_bytes(iter(output)):
        for event in stream.handle_event(TypeAdapter(ResponseStreamEvent).validate_json(sse.data)):
            if event.type == "response.completed":
                final = event.response
    assert final is not None
    return final.model_dump(mode="json")


@pytest.mark.parametrize("kind", ["local_shell_call", "tool_search_call"])
def test_native_client_call_waits_for_item_done_and_approval(kind: str) -> None:
    item = native_call(kind)
    state = IncrementalStream("responses")
    delivery = StreamDelivery("responses")
    delivery.begin_attempt()
    output = [chunk for frame in state.add(responses_start()) for chunk in delivery.emit(frame, state)]
    held = state.add(
        {"type": "response.output_item.added", "output_index": 0, "item": {**item, "status": "in_progress"}}
    )
    assert state.ready() is None
    assert held[0].requires == {0}
    with pytest.raises(UnsupportedStream, match="unevaluated"):
        delivery.emit(held[0], state)

    held += state.add({"type": "response.output_item.done", "output_index": 0, "item": item})
    assert state.ready() == 0
    evaluation = state.evaluation({"input": "Read the current directory."}, 0)
    assert evaluation.response["output"] == [item]
    state.allowed.add(0)
    output.extend(chunk for frame in held for chunk in delivery.emit(frame, state))
    for frame in state.add({"type": "response.completed", "response": responses_body([item])}):
        output.extend(delivery.emit(frame, state))
    state.finish()
    output.extend(delivery.finish(state))

    final = official_responses(output)
    assert final["output"][0]["type"] == kind
    assert final["output"][0]["call_id"] == item["call_id"]
    field = "action" if kind == "local_shell_call" else "arguments"
    assert all(final["output"][0][field][key] == value for key, value in item[field].items())


@pytest.mark.parametrize("kind", ["local_shell_call", "tool_search_call"])
@pytest.mark.parametrize("boundary", ["done", "terminal"])
def test_native_client_call_cannot_change_after_its_executable_fields_are_seen(kind: str, boundary: str) -> None:
    item = native_call(kind)
    changed = deepcopy(item)
    if kind == "local_shell_call":
        changed["action"]["command"] = ["other-command"]
    else:
        # Python considers True == 1; the wire and tool do not.
        changed["arguments"]["limit"] = True
    state = IncrementalStream("responses")
    state.add(responses_start())
    state.add({"type": "response.output_item.added", "output_index": 0, "item": item})
    if boundary == "done":
        event = {"type": "response.output_item.done", "output_index": 0, "item": changed}
    else:
        state.add({"type": "response.output_item.done", "output_index": 0, "item": item})
        state.allowed.add(0)
        event = {"type": "response.completed", "response": responses_body([changed])}
    with pytest.raises(UnsupportedStream, match="changed"):
        state.add(event)


@pytest.mark.parametrize("execution", ["server", None])
def test_tool_search_without_client_execution_remains_unsupported(execution: str | None) -> None:
    state = IncrementalStream("responses")
    state.add(responses_start())
    item = {**native_call("tool_search_call"), "execution": execution}
    with pytest.raises(UnsupportedStream, match="client-executed"):
        state.add({"type": "response.output_item.added", "output_index": 0, "item": item})


@pytest.mark.parametrize("kind", ["local_shell_call", "tool_search_call"])
def test_whole_native_calls_do_not_accept_unrelated_argument_delta_events(kind: str) -> None:
    state = IncrementalStream("responses")
    state.add(responses_start())
    item = native_call(kind)
    state.add({"type": "response.output_item.added", "output_index": 0, "item": item})
    with pytest.raises(UnsupportedStream, match="whole-item"):
        state.add(
            {
                "type": "response.custom_tool_call_input.delta",
                "output_index": 0,
                "item_id": item["id"],
                "delta": "unsafe",
            }
        )


@pytest.mark.parametrize("kind", ["code_interpreter_call", "mcp_call"])
def test_provider_tool_argument_events_stream_without_a_client_tool_gate(kind: str) -> None:
    if kind == "code_interpreter_call":
        field, family, value = "code", "code_interpreter_call_code", "print(1)"
        item = {
            "type": kind,
            "id": "provider_item",
            "container_id": "container",
            "status": "completed",
            "code": value,
            "outputs": [],
        }
    else:
        field, family, value = "arguments", "mcp_call_arguments", '{"query":"fixture"}'
        item = {
            "type": kind,
            "id": "provider_item",
            "name": "lookup",
            "server_label": "remote",
            "status": "completed",
            "arguments": value,
            "output": "found",
        }
    events = [
        responses_start(),
        {"type": "response.output_item.added", "output_index": 0, "item": {**item, field: "", "status": "in_progress"}},
        {"type": f"response.{family}.delta", "output_index": 0, "item_id": "provider_item", "delta": value},
        {"type": f"response.{family}.done", "output_index": 0, "item_id": "provider_item", field: value},
        {"type": "response.output_item.done", "output_index": 0, "item": item},
        {"type": "response.completed", "response": responses_body([item])},
    ]
    state = IncrementalStream("responses")
    output: list[bytes] = []
    for sequence, event in enumerate(events):
        frames = state.add({**event, "sequence_number": sequence})
        assert frames and frames[0].requires == set()
        output.extend(wire_event("responses", frame.data) for frame in frames)
    state.finish()

    final = official_responses(output)
    assert state.calls == []
    assert final["output"][0][field] == value


def test_provider_argument_event_cannot_be_relabelled_as_another_item_family() -> None:
    state = IncrementalStream("responses")
    state.add(responses_start())
    state.add(
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {"type": "web_search_call", "id": "web", "status": "in_progress"},
        }
    )
    with pytest.raises(UnsupportedStream, match="Unsupported Responses event"):
        state.add({"type": "response.mcp_call_arguments.delta", "output_index": 0, "item_id": "web", "delta": "{}"})


def message_body(container: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "id": "msg_container",
        "type": "message",
        "role": "assistant",
        "model": "fixture",
        "content": [],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 3, "output_tokens": 1},
        "container": container,
    }


@pytest.mark.parametrize("container", [None, {"id": "container_1", "expires_at": "2026-10-07T00:00:00Z"}])
def test_messages_container_metadata_survives_stream_assembly_and_encoding(container: dict[str, Any] | None) -> None:
    state = IncrementalStream("messages")
    state.add({"type": "message_start", "message": {**message_body(None), "stop_reason": None}})
    state.add(
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None, "container": container},
            "usage": {"output_tokens": 1},
        }
    )
    state.add({"type": "message_stop"})
    state.finish()
    output = list(encode("messages", state.body))
    assert assemble("messages", output)["container"] == container
    snapshot = None
    for sse in SSEDecoder().iter_bytes(iter(output)):
        event = TypeAdapter(RawMessageStreamEvent).validate_json(sse.data)
        snapshot = accumulate_event(event=event, current_snapshot=snapshot)
    assert snapshot is not None
    assert (snapshot.container.id if snapshot.container is not None else None) == (
        container["id"] if container else None
    )
    final_delta = json.loads(list(SSEDecoder().iter_bytes(iter(output)))[-2].data)
    assert final_delta["delta"]["container"] == container


def test_messages_upstream_ping_before_start_is_dropped_before_the_official_sdk() -> None:
    state = IncrementalStream("messages")
    assert state.add({"type": "ping"}) == []
    output: list[bytes] = []
    for sse in SSEDecoder().iter_bytes(encode("messages", message_body(None))):
        output.extend(wire_event("messages", frame.data) for frame in state.add(json.loads(sse.data)))
    state.finish()
    snapshot = None
    for sse in SSEDecoder().iter_bytes(iter(output)):
        event = TypeAdapter(RawMessageStreamEvent).validate_json(sse.data)
        snapshot = accumulate_event(event=event, current_snapshot=snapshot)
    assert snapshot is not None and snapshot.id == "msg_container" and snapshot.stop_reason == "end_turn"
