"""Validate complete and incremental Responses arguments through the public callback.

The done event may carry the first arguments, but it cannot revise previously
streamed input. Item completion and a Watcher allow remain separate barriers.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from test_incremental_safety import (
    USER,
    WatcherPeer,
    collect,
    decoded,
    rejected,
    request_data,
    response_added,
    response_done,
    response_item,
)
from test_stream_compatibility import official_responses, responses_body, responses_start
from watcher_litellm.callback import WatcherCallback


@pytest.fixture(params=["function_call", "custom_tool_call"])
def call(request: pytest.FixtureRequest) -> dict[str, Any]:
    """An ordinary Codex shell call, or the equivalent free-form custom tool."""
    item = response_item("call_0", '{"cmd":"cat notes.txt"}', "exec_command")
    if request.param == "custom_tool_call":
        del item["arguments"]
        item.update(type="custom_tool_call", input="cat notes.txt")
    return item


def argument_event(item: dict[str, Any], suffix: str, value: Any) -> dict[str, Any]:
    field = "arguments" if item["type"] == "function_call" else "input"
    family = "function_call_arguments" if field == "arguments" else "custom_tool_call_input"
    return {
        "type": f"response.{family}.{suffix}",
        "output_index": 0,
        "item_id": item["id"],
        **({"name": item["name"]} if suffix == "done" and field == "arguments" else {}),
        "delta" if suffix == "delta" else field: value,
    }


@pytest.mark.parametrize("argument_source", ["done", "deltas", "added"])
async def test_arguments_wait_for_item_completion_and_watcher_allow(call: dict[str, Any], argument_source: str) -> None:
    """Neither completed arguments nor a pending evaluation may expose the call."""
    field = "arguments" if call["type"] == "function_call" else "input"
    peer = WatcherPeer()
    arguments_done = asyncio.Event()
    finish_item = asyncio.Event()
    events = [
        responses_start(),
        response_added(0, {**call, field: call[field] if argument_source == "added" else "", "status": "in_progress"}),
    ]
    if argument_source == "deltas":
        events += [argument_event(call, "delta", call[field][:5]), argument_event(call, "delta", call[field][5:])]
    events.append(argument_event(call, "done", call[field]))
    tail = [response_done(0, call), {"type": "response.completed", "response": responses_body([call])}]

    async def provider() -> AsyncIterator[dict[str, Any]]:
        for event in events:
            yield event
        arguments_done.set()
        await finish_item.wait()
        for event in tail:
            yield event

    output: list[bytes] = []

    async def consume() -> None:
        async for chunk in WatcherCallback(peer.client).async_post_call_streaming_iterator_hook(
            USER, provider(), request_data("responses")
        ):
            output.append(chunk)

    task = asyncio.create_task(consume())
    try:
        async with asyncio.timeout(3):
            await arguments_done.wait()
            assert peer.requests == []
            assert [event["type"] for event in decoded(output)] == ["response.created"]
            finish_item.set()
            evaluation = await peer.entered.get()
            assert evaluation["response_body"]["output"] == [call]
            assert [event["type"] for event in decoded(output)] == ["response.created"]
            peer.decide("call_0", "allow")
            await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    final = official_responses(output)["output"][0]
    assert final[field] == call[field]
    assert final["name"] == call["name"]
    assert final["call_id"] == call["call_id"]
    assert len(peer.requests) == 1
    assert [event["type"] for event in decoded(output)] == [event["type"] for event in events + tail]


@pytest.mark.parametrize(
    ("prior_event_type", "function_arguments", "custom_input"),
    [
        pytest.param("added", "other", "other", id="added"),
        pytest.param("added", None, None, id="null-added"),
        pytest.param("delta", "other", "other", id="delta"),
        pytest.param("delta", '{"cmd', "cat n", id="partial-delta"),
        pytest.param("delta", "", "", id="empty-delta"),
        pytest.param("done", "other", "other", id="done"),
        pytest.param("done", "", "", id="empty-done"),
    ],
)
async def test_done_cannot_replace_previously_supplied_arguments(
    call: dict[str, Any], prior_event_type: str, function_arguments: str | None, custom_input: str | None
) -> None:
    field = "arguments" if call["type"] == "function_call" else "input"
    prior_value = function_arguments if call["type"] == "function_call" else custom_input
    peer = WatcherPeer()
    events = [responses_start(), response_added(0, {**call, field: prior_value if prior_event_type == "added" else ""})]
    if prior_event_type != "added":
        events.append(argument_event(call, prior_event_type, prior_value))
    events += [argument_event(call, "done", call[field]), response_done(0, call)]

    output = await rejected(WatcherCallback(peer.client), "responses", events)

    assert peer.requests == []
    assert [event["type"] for event in output] == ["response.created", "error"]


async def test_interleaved_calls_can_mix_incremental_and_done_only_arguments(call: dict[str, Any]) -> None:
    peer = WatcherPeer()
    peer.decide("call_0", "allow")
    peer.decide("call_1", "allow")
    field = "arguments" if call["type"] == "function_call" else "input"
    second = {**call, "id": "fc_call_1", "call_id": "call_1", field: call[field].replace("notes", "other")}
    events = [
        responses_start(),
        response_added(0, {**call, field: ""}),
        argument_event(call, "delta", call[field][:5]),
        response_added(1, {**second, field: ""}),
        {**argument_event(second, "done", second[field]), "output_index": 1},
        response_done(1, second),
        argument_event(call, "delta", call[field][5:]),
        argument_event(call, "done", call[field]),
        response_done(0, call),
        {"type": "response.completed", "response": responses_body([call, second])},
    ]

    output = await collect(WatcherCallback(peer.client), "responses", events)

    assert [request["response_body"]["output"] for request in peer.requests] == [[call], [second]]
    assert [item[field] for item in official_responses(output)["output"]] == [call[field], second[field]]
    assert [event["type"] for event in decoded(output)] == [event["type"] for event in events]


@pytest.mark.parametrize("invalid", ["item_id", "name", "null", "object", "late-delta"])
async def test_done_rejects_changed_identity_malformed_arguments_and_late_deltas(
    call: dict[str, Any], invalid: str
) -> None:
    field = "arguments" if call["type"] == "function_call" else "input"
    peer = WatcherPeer()
    done = argument_event(call, "done", call[field])
    if invalid in {"item_id", "name"}:
        done[invalid] = "changed"
    elif invalid == "null":
        done[field] = None
    elif invalid == "object":
        done[field] = {"cmd": "cat notes.txt"}
    events = [responses_start(), response_added(0, {**call, field: ""}), done]
    if invalid == "late-delta":
        events.append(argument_event(call, "delta", "extra"))
        call = {**call, field: call[field] + "extra"}
    events.append(response_done(0, call))

    output = await rejected(WatcherCallback(peer.client), "responses", events)

    assert peer.requests == []
    assert [event["type"] for event in output] == ["response.created", "error"]


@pytest.mark.parametrize("boundary", ["item", "response"])
@pytest.mark.parametrize("changed_field", ["arguments", "name", "call_id"])
async def test_done_only_call_cannot_change_at_later_boundaries(boundary: str, changed_field: str) -> None:
    peer = WatcherPeer()
    peer.decide("call_0", "allow")
    call = response_item("call_0", '{"cmd":"cat notes.txt"}', "exec_command")
    changed = {**call, changed_field: "unevaluated_replacement"}
    events = [
        responses_start(),
        response_added(0, {**call, "arguments": ""}),
        argument_event(call, "done", call["arguments"]),
        response_done(0, changed if boundary == "item" else call),
        {"type": "response.completed", "response": responses_body([changed])},
    ]

    output = await rejected(WatcherCallback(peer.client), "responses", events)

    assert len(peer.requests) == (0 if boundary == "item" else 1)
    assert "unevaluated_replacement" not in json.dumps(output)
    assert not any(event["type"] == "response.completed" for event in output)


@pytest.mark.parametrize("has_item_done", [False, True])
async def test_done_only_truncation_fails_visibly_without_releasing_an_unapproved_call(has_item_done: bool) -> None:
    peer = WatcherPeer()
    peer.decide("call_0", "allow")
    call = response_item("call_0", '{"cmd":"cat notes.txt"}', "exec_command")
    events = [
        responses_start(),
        response_added(0, {**call, "arguments": ""}),
        argument_event(call, "done", call["arguments"]),
    ]
    if has_item_done:
        events.append(response_done(0, call))

    output = await rejected(WatcherCallback(peer.client), "responses", events)

    assert len(peer.requests) == int(has_item_done)
    assert any(event["type"] == "response.output_item.done" for event in output) == has_item_done
    assert output[-1]["type"] == "error"
    assert not any(event["type"] == "response.completed" for event in output)
