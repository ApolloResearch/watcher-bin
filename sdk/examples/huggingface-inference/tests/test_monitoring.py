"""Verify inherited policy gates actual callbacks and preserves native continuation."""

from copy import deepcopy

import pytest
from watcher_huggingface_inference.integration import fetch
from watcher_huggingface_inference.monitoring import Monitor, run_turn

from tests.support import CALLS, HISTORY, TOOLS, Transport, clients, reply


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,decision,allowed",
    [
        ("enforce", "allow", True),
        ("enforce", "deny", False),
        ("enforce", "escalate", False),
        ("observe", "deny", True),
        ("paused", "allow", True),
    ],
)
async def test_native_function_dispatch_applies_server_policy(mode, decision, allowed):
    transport, effects = Transport(mode=mode, decision=decision), []

    async def weather(**arguments):
        effects.append(arguments)
        return arguments

    async with clients(transport) as (provider, watcher):
        monitor = Monitor(watcher, "conversation")
        if allowed:
            history = await run_turn(
                provider, monitor, model="fixture-model", messages=HISTORY, tools=TOOLS, functions={"weather": weather}
            )
            assert [item["tool_call_id"] for item in history[-2:]] == ["call-a", "call-b"]
            assert effects == [{"city": "Paris"}, {"city": "Tokyo"}]
        else:
            with pytest.raises(PermissionError):
                await run_turn(
                    provider,
                    monitor,
                    model="fixture-model",
                    messages=HISTORY,
                    tools=TOOLS,
                    functions={"weather": weather},
                )
            assert effects == []
    assert len(transport.watcher_requests) == 1
    assert (
        "settings_overrides" not in transport.watcher_requests[0]
        or transport.watcher_requests[0]["settings_overrides"] is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["missing", "wrong-id", "missing-id", "duplicate", "deny-second"])
async def test_whole_batch_withheld_before_any_side_effect(mutation):
    transport, effects = Transport(mutation=mutation), []

    async def weather(**arguments):
        effects.append(arguments)

    async with clients(transport) as (provider, watcher):
        with pytest.raises((RuntimeError, PermissionError)):
            await run_turn(
                provider,
                Monitor(watcher, "conversation"),
                model="fixture-model",
                messages=HISTORY,
                tools=TOOLS,
                functions={"weather": weather},
            )
    assert effects == []


@pytest.mark.asyncio
async def test_full_native_history_retains_results_for_next_real_pair():
    transport, effects = Transport([reply(calls=CALLS), reply()]), []

    async def weather(**arguments):
        effects.append(arguments)
        return arguments

    async with clients(transport) as (provider, watcher):
        monitor = Monitor(watcher, "conversation")
        history = await run_turn(
            provider, monitor, model="fixture-model", messages=HISTORY, tools=TOOLS, functions={"weather": weather}
        )
        assert len(transport.watcher_requests) == 1
        await run_turn(provider, monitor, model="fixture-model", messages=history, functions={"weather": weather})
    assert transport.watcher_requests[-1]["request_body"]["messages"] == history
    assert len(effects) == 2


@pytest.mark.asyncio
async def test_attempted_identity_never_executes_twice():
    transport, effects = Transport(), []

    async def weather(**arguments):
        effects.append(arguments)
        return arguments

    async with clients(transport) as (provider, watcher):
        _, exchange = await fetch(provider, {"model": "fixture-model", "messages": HISTORY, "tools": TOOLS})
        monitor = Monitor(watcher, "conversation")
        await monitor.dispatch(exchange, {"weather": weather})
        with pytest.raises(PermissionError, match="Repeated"):
            await monitor.dispatch(exchange, {"weather": weather})
    assert len(effects) == 2 and len(transport.watcher_requests) == 1


@pytest.mark.asyncio
async def test_unknown_function_blocks_batch_without_callbacks():
    transport = Transport()
    async with clients(transport) as (provider, watcher):
        with pytest.raises(PermissionError, match="Unregistered"):
            await run_turn(
                provider, Monitor(watcher, "conversation"), model="fixture-model", messages=HISTORY, functions={}
            )
    assert transport.watcher_requests == []


@pytest.mark.asyncio
async def test_callback_failure_retains_native_linked_result():
    transport = Transport()

    async def weather(**arguments):
        raise ValueError("private detail")

    async with clients(transport) as (provider, watcher):
        history = await run_turn(
            provider,
            Monitor(watcher, "conversation"),
            model="fixture-model",
            messages=HISTORY,
            functions={"weather": weather},
        )
    assert history[-1] == {"role": "tool", "tool_call_id": "call-b", "content": '{"error": "ValueError"}'}


@pytest.mark.asyncio
async def test_more_than_32_raw_calls_are_not_split_or_dropped():
    calls = [{**deepcopy(CALLS[0]), "id": f"call-{i}"} for i in range(33)]
    transport, effects = Transport([reply(calls=calls)]), []

    async def weather(**arguments):
        effects.append(arguments)

    async with clients(transport) as (provider, watcher):
        await run_turn(
            provider,
            Monitor(watcher, "conversation"),
            model="fixture-model",
            messages=HISTORY,
            functions={"weather": weather},
        )
    assert len(effects) == 33 and len(transport.watcher_requests) == 1


@pytest.mark.asyncio
async def test_configured_grading_failure_allow_is_honored():
    transport, effects = Transport(mutation="failure-allow"), []

    async def weather(**arguments):
        effects.append(arguments)

    async with clients(transport) as (provider, watcher):
        await run_turn(
            provider,
            Monitor(watcher, "conversation"),
            model="fixture-model",
            messages=HISTORY,
            functions={"weather": weather},
        )
    assert len(effects) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["length", "content_filter"])
async def test_native_text_truncation_is_preserved_without_tool_dispatch(reason):
    response = reply(text="Partial text")
    response["choices"][0]["finish_reason"] = reason
    transport = Transport([response])
    async with clients(transport) as (provider, watcher):
        history = await run_turn(
            provider, Monitor(watcher, "partial-text"), model="fixture-model", messages=HISTORY, functions={}
        )
    assert history[-1]["content"] == "Partial text"
    assert transport.watcher_requests[0]["response_body"]["choices"][0]["finish_reason"] == reason


@pytest.mark.asyncio
async def test_id_only_decisions_may_arrive_in_another_order():
    transport, effects = Transport(mutation="reverse"), []

    async def weather(**arguments):
        effects.append(arguments)
        return arguments

    async with clients(transport) as (provider, watcher):
        await run_turn(
            provider,
            Monitor(watcher, "conversation"),
            model="fixture-model",
            messages=HISTORY,
            tools=TOOLS,
            functions={"weather": weather},
        )
    assert effects == [{"city": "Paris"}, {"city": "Tokyo"}]


@pytest.mark.asyncio
async def test_reused_response_identity_prevents_every_callback():
    calls = deepcopy(CALLS)
    calls[1]["id"] = calls[0]["id"]
    transport, effects = Transport([reply(calls=calls)]), []

    async def weather(**arguments):
        effects.append(arguments)

    async with clients(transport) as (provider, watcher):
        with pytest.raises(ValueError, match="duplicate native tool identity"):
            await run_turn(
                provider,
                Monitor(watcher, "conversation"),
                model="fixture-model",
                messages=HISTORY,
                tools=TOOLS,
                functions={"weather": weather},
            )
    assert effects == [] and transport.watcher_requests == []
