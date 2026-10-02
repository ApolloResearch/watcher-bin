"""The documented Agno constructor refuses unsupported calls before native effects."""

import pytest
from agno.tools.function import Function
from demo.enforce import MonitoredModel
from demo.observe import DeterministicModel
from watcher_agno import WatcherAgent


class RecordingMonitor:
    """Record native pending IDs and optionally refuse before a Function executes."""

    def __init__(self, refuse=False):
        self.calls = []
        self.refuse = refuse

    async def before(self, history, call_id, name, arguments):
        self.calls.append((list(history), call_id, name, arguments))
        if self.refuse:
            raise RuntimeError("Monitor refused the pending call")


def function_for(effects):
    """Use a sync Function that would execute under an ordinary Agent.run."""

    def double(value: int) -> str:
        """Double an integer and record its native execution."""
        effects.append(value)
        return str(value * 2)

    return Function.from_callable(double)


@pytest.mark.parametrize("method", ["run", "continue_run"])
@pytest.mark.parametrize("stream", [False, True])
def test_sync_agent_refuses_before_provider_monitor_or_tool(method, stream):
    monitor, effects, model_calls = RecordingMonitor(refuse=True), [], []

    class CountedModel(MonitoredModel):
        """Record any native provider call, without credentials or networking."""

        def invoke(self, messages, **kwargs):
            model_calls.append(messages)
            return super().invoke(messages, **kwargs)

    agent = WatcherAgent(
        monitor, model=CountedModel(id="deterministic"), tools=[function_for(effects)], telemetry=False
    )
    with pytest.raises(RuntimeError, match="WatcherAgent"):
        if method == "run":
            result = agent.run("Double 2 and 3", stream=stream)
        else:
            result = agent.continue_run(run_id="pending", session_id="fixture", stream=stream)
        if stream:
            list(result)

    assert model_calls == []
    assert monitor.calls == []
    assert effects == []


@pytest.mark.parametrize("setting", ["call_stream", "agent_stream", "resume"])
def test_unsupported_async_modes_refuse_before_native_dispatch(setting):
    monitor, effects = RecordingMonitor(refuse=True), []
    agent = WatcherAgent(
        monitor,
        model=MonitoredModel(id="deterministic"),
        tools=[function_for(effects)],
        telemetry=False,
        stream=setting == "agent_stream",
    )
    with pytest.raises(RuntimeError, match="WatcherAgent"):
        if setting == "resume":
            agent.acontinue_run(run_id="pending", session_id="fixture")
        else:
            agent.arun("Double 2 and 3", **({"stream": True} if setting == "call_stream" else {}))
    assert monitor.calls == []
    assert effects == []


@pytest.mark.asyncio
@pytest.mark.parametrize("refuse", [False, True])
async def test_buffered_arun_uses_registered_monitor_and_native_history(refuse):
    monitor, effects = RecordingMonitor(refuse=refuse), []
    function = function_for(effects)
    agent = WatcherAgent(monitor, model=MonitoredModel(id="deterministic"), tools=[function], telemetry=False)
    result = await agent.arun("Double 2 and 3")

    assert function.pre_hook is None, "Registration must not alter a caller-owned Function"
    assert monitor.calls
    assert {call[1] for call in monitor.calls} == {"double-2", "double-3"}
    for history, call_id, name, arguments in monitor.calls:
        assert any(message.role == "user" and message.content == "Double 2 and 3" for message in history)
        assert any(call["id"] == call_id for message in history for call in message.tool_calls or [])
        assert name == "double"
        assert arguments == {"value": int(call_id[-1])}
    if refuse:
        assert effects == []
    else:
        assert sorted(effects) == [2, 3]
        assert result.messages[-1].content == "4 and 6"


@pytest.mark.asyncio
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("refuse", [False, True])
async def test_existing_application_pre_hook_remains_before_monitor(asynchronous, refuse):
    monitor, effects, application_calls = RecordingMonitor(), [], []

    def permission(fc, agent, session_state):
        application_calls.append((fc.call_id, agent, session_state))
        assert not any(call[1] == fc.call_id for call in monitor.calls)
        if refuse:
            raise RuntimeError("Application refused the tool")

    async def async_permission(fc, agent, session_state):
        permission(fc, agent, session_state)

    function = function_for(effects)
    original_hook = async_permission if asynchronous else permission
    function.pre_hook = original_hook
    agent = WatcherAgent(monitor, model=MonitoredModel(id="deterministic"), tools=[function], telemetry=False)
    await agent.arun("Double 2 and 3", session_state={"customer": "fixture"})

    assert function.pre_hook is original_hook
    assert {call[0] for call in application_calls} == {"double-2", "double-3"}
    assert all(call[1] is agent and call[2]["customer"] == "fixture" for call in application_calls)
    if refuse:
        assert monitor.calls == []
        assert effects == []
    else:
        assert len(monitor.calls) == 2
        assert sorted(effects) == [2, 3]


def test_constructor_rejects_unmonitored_model_or_unregistered_tool():
    monitor, effects = RecordingMonitor(), []
    with pytest.raises(TypeError, match="CaptureModelCalls"):
        WatcherAgent(monitor, model=DeterministicModel(id="deterministic"), tools=[function_for(effects)])
    with pytest.raises(TypeError, match="Function objects"):
        WatcherAgent(monitor, model=MonitoredModel(id="deterministic"), tools=[lambda: effects.append(1)])
    assert effects == []


@pytest.mark.parametrize("asynchronous", [False, True])
def test_constructor_refuses_generator_tools_without_running_them(asynchronous):
    effects = []

    def stream():
        """Produce streamed tool output, which this buffered adapter does not support."""
        effects.append("ran")
        yield "value"

    async def async_stream():
        """Produce async streamed tool output without making a model request."""
        effects.append("ran")
        yield "value"

    function = Function.from_callable(async_stream if asynchronous else stream)
    with pytest.raises(TypeError, match="buffered callable entrypoint"):
        WatcherAgent(RecordingMonitor(), model=MonitoredModel(id="deterministic"), tools=[function], telemetry=False)
    assert effects == []
