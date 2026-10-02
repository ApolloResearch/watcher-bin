"""Reusable Agno execution boundary for synchronous Watcher monitoring.

Use WatcherAgent with one Monitor and one captured model per conversation.
It installs awaited tool hooks and rejects synchronous Agent entry points, which
cannot await them. demo/enforce.py shows registration and final recording.
"""

import asyncio
from functools import wraps
from inspect import isasyncgenfunction, isawaitable, iscoroutinefunction, isgeneratorfunction, signature, unwrap

from agno.agent import Agent
from agno.exceptions import AgentRunException, StopAgentRun
from agno.models.message import Message
from agno.tools.function import Function


async def execute_tool(monitor, history, call):
    """Authorize the public FunctionCall immediately before aexecute invokes it."""
    await monitor.before(history, call.call_id, call.function.name, call.arguments)
    result = await call.aexecute()
    if result.status != "success":
        raise RuntimeError("Native tool execution failed")
    return Message(role="tool", content=str(call.result), tool_call_id=call.call_id)


class CaptureModelCalls:
    """Mixin before an Agno model provider to retain its public ainvoke message list.

    Use one model per conversation and buffered Agent.arun. Agno appends the parsed
    assistant response to this same list before Function.pre_hook, so the hook sees
    native pending IDs and the complete actual input history without parsing raw
    provider responses. Streaming and concurrently shared models are not supported.
    """

    async def ainvoke(self, messages, **kwargs):
        self.watcher_messages = messages
        return await super().ainvoke(messages, **kwargs)  # ty: ignore[unresolved-attribute]


def _before_tool(monitor, model, previous_hook):
    """Compose an awaited Function pre-hook for WatcherAgent's async-only dispatch.

    Agno 2.2.3 logs and swallows ordinary pre_hook exceptions. StopAgentRun is the
    public exception it propagates before execution. Existing application hooks
    run first, with Agno's documented context arguments. Their AgentRunException
    subclasses retain native retry/stop behavior and messages; other failures stop
    the call. Watcher checks the resulting arguments before execution.
    This callback alone is unsafe
    on an ordinary Agent: synchronous runs do not await it.
    """

    async def before(fc, agent=None, team=None, session_state=None):
        try:
            if previous_hook is not None:
                context = {"fc": fc, "agent": agent, "team": team, "session_state": session_state}
                parameters = signature(previous_hook).parameters
                result = previous_hook(**{key: value for key, value in context.items() if key in parameters})
                if isawaitable(result):
                    await result
            await monitor.before(model.watcher_messages, fc.call_id, fc.function.name, fc.arguments)
        except AgentRunException:
            raise
        except Exception as error:
            raise StopAgentRun("Watcher withheld this tool call") from error

    return before


def _async_entrypoint(entrypoint):
    """Keep Agno on its awaited hook path for synchronous and async tool bodies.

    Agno selects Function.execute for synchronous entrypoints even inside arun;
    that path cannot await an async pre-hook. A coroutine entrypoint selects
    aexecute instead. Synchronous bodies retain native worker-thread execution
    after the awaited gate. Generator tools are outside this buffered adapter.
    """
    if entrypoint is None or isgeneratorfunction(unwrap(entrypoint)) or isasyncgenfunction(unwrap(entrypoint)):
        raise TypeError("WatcherAgent tools require a buffered callable entrypoint")
    if iscoroutinefunction(entrypoint):
        return entrypoint

    @wraps(entrypoint)
    async def invoke(*args, **kwargs):
        return await asyncio.to_thread(entrypoint, *args, **kwargs)

    return invoke


def _refuse_generated_tools(options):
    """Reject Agno options that generate tools outside the caller's Function list.

    Agno's get_tools/aget_tools append these built-ins during a run, after this
    adapter installs pre-hooks. Knowledge search is enabled by default when a
    knowledge source or retriever is supplied; disabling both knowledge tool
    options leaves that source usable without adding an unmonitored tool.
    """
    unsupported = [
        name
        for name in (
            "read_chat_history",
            "read_tool_call_history",
            "search_session_history",
            "enable_agentic_memory",
            "enable_agentic_culture",
            "enable_agentic_state",
        )
        if options.get(name)
    ]
    if options.get("knowledge") is not None or options.get("knowledge_retriever") is not None:
        if options.get("search_knowledge", True):
            unsupported.append("search_knowledge")
        if options.get("update_knowledge", False):
            unsupported.append("update_knowledge")
    if unsupported:
        raise TypeError("WatcherAgent cannot monitor Agno-generated tools; disable: " + ", ".join(unsupported))


class WatcherAgent(Agent):
    """Register awaited Watcher hooks and permit buffered ``arun`` only.

    Supply a model with CaptureModelCalls first in its inheritance list and public
    Function tools. Each tool is copied before registration, preserving its existing
    pre-hook without modifying the caller's Function. Synchronous tool bodies run
    in a worker thread only after the awaited gate; generator tools are refused.
    Options that generate Agno-owned tools outside the supplied Function list
    are refused. Other Agent options pass through unchanged. Keep the model and
    agent private to this conversation; changing tools, hooks or tool-generating
    options after construction bypasses this registration.

    ``run`` and native continuation methods refuse before model or tool dispatch.
    Streaming is unsupported because the history capture uses buffered ``ainvoke``.
    """

    def __init__(self, monitor, *, model, tools, **kwargs):
        _refuse_generated_tools(kwargs)
        if not isinstance(model, CaptureModelCalls):
            raise TypeError("WatcherAgent requires a model with the CaptureModelCalls mixin")
        monitored_tools = []
        for function in tools:
            if not isinstance(function, Function):
                raise TypeError("WatcherAgent tools must be Agno Function objects")
            monitored = function.model_copy(deep=True)
            monitored.entrypoint = _async_entrypoint(function.entrypoint)
            monitored.pre_hook = _before_tool(monitor, model, function.pre_hook)
            monitored_tools.append(monitored)
        super().__init__(model=model, tools=monitored_tools, **kwargs)

    def run(self, *args, **kwargs):
        """Refuse sync dispatch before Agno can drop an awaited tool pre-hook."""
        raise RuntimeError("WatcherAgent requires await agent.arun(); synchronous run() is unsupported")

    def arun(self, *args, **kwargs):
        """Return Agno's buffered run coroutine; refuse streaming before dispatch."""
        stream = kwargs.get("stream")
        effective_stream = self.stream if stream is None else stream
        if effective_stream:
            raise RuntimeError("WatcherAgent supports buffered arun() only; streaming is unsupported")
        return super().arun(*args, **kwargs)

    def continue_run(self, *args, **kwargs):
        """Refuse native continuation; application approvals stay inside arun."""
        raise RuntimeError("WatcherAgent does not support continue_run(); use the awaited approval callback")

    def acontinue_run(self, *args, **kwargs):
        """Refuse continuation without a freshly captured pending-call history."""
        raise RuntimeError("WatcherAgent does not support acontinue_run(); use the awaited approval callback")
