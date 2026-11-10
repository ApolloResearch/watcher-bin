"""Reusable OpenAI Agents execution boundary for synchronous Watcher monitoring.

Use these adapters with one Monitor per conversation. The runnable clients in
demo/enforce.py show native registration and final transcript recording.
"""

import asyncio
import json
from copy import deepcopy

from agents import FunctionTool, RunHooks, default_tool_error_function
from agents.tool_context import ToolContext


async def execute_tool(monitor, history, tool, call):
    """Gate a Responses function call before invoking the public FunctionTool handler.

    A refusal raises from monitor.before(), which reports the call blocked. A
    tool exception is marked failed on the Monitor and propagates, so a result
    the application later supplies for that call is recorded with ``error``. A
    cancellation while the tool runs is reported as cancelled (see
    Monitor.report_status) before it propagates; a reporting failure becomes its
    cause. A tool built with Agents' default ``failure_error_function`` returns
    its error as output instead of raising; build it with
    `failure_error_function` below so the Monitor still learns of the failure.
    """
    if tool.name != call.name:
        raise ValueError("Selected function must match the model's tool name")
    arguments = json.loads(call.arguments)
    await monitor.before(history, call.call_id, call.name, arguments)
    context = ToolContext(context=None, tool_call_id=call.call_id, tool_name=call.name, tool_arguments=call.arguments)
    try:
        result = await tool.on_invoke_tool(context, call.arguments)
    except asyncio.CancelledError as cancelled:
        # CancelledError is not an Exception, so neither the clause below nor
        # Agents' failure handling sees it; the call may have partly run.
        try:
            await monitor.report_status(call.call_id, call.name, arguments, "cancelled")
        except Exception as failure:
            raise cancelled from failure
        raise
    except Exception as error:
        monitor.mark_failed(call.call_id, str(error) or type(error).__name__)
        raise
    return {"type": "function_call_output", "call_id": call.call_id, "output": result}


def failure_error_function(monitor):
    """Build a FunctionTool ``failure_error_function`` that marks the failed call on ``monitor``.

    Agents' default turns a tool exception into output text, which Responses
    history cannot tell apart from a successful result, so Watcher would record
    the call as completed. Pass
    ``function_tool(failure_error_function=failure_error_function(monitor))``:
    the model still receives Agents' default error text, and the Monitor sends
    that result with ``error`` in later before() and record() histories. Works
    with Runner and execute_tool, which both invoke tools with a ToolContext.
    """

    def failed(context, error):
        if not isinstance(context, ToolContext):
            raise ValueError("Marking a tool failure needs the native ToolContext that names the call")
        monitor.mark_failed(context.tool_call_id, str(error) or type(error).__name__)
        return default_tool_error_function(context, error)

    return failed


class WatcherHooks(RunHooks):
    """Gate native Runner function tools using public model and tool lifecycle hooks.

    Use one instance per run and agents whose tools are all local FunctionTools,
    with stable system instructions. ComputerTool actions run concurrently with
    on_tool_start, so an unsupported-tool error cannot prevent those actions.
    Provider-hosted tools, handoffs and changing instructions need other adapters.
    """

    def __init__(self, monitor):
        self.monitor = monitor
        self.history = []
        self.system_prompt = None
        self.has_prompt = False

    async def on_llm_start(self, context, agent, system_prompt, input_items):
        if self.has_prompt and system_prompt != self.system_prompt:
            raise ValueError("Changing system instructions require a separate adapter")
        self.system_prompt = system_prompt
        self.has_prompt = True
        self.history = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + deepcopy(input_items)

    async def on_llm_end(self, context, agent, response):
        self.history.extend(item.model_dump(exclude_none=True) for item in response.output)

    async def on_tool_start(self, context, agent, tool):
        """Runner awaits this hook before invoking a local FunctionTool."""
        if not isinstance(context, ToolContext) or not isinstance(tool, FunctionTool):
            raise ValueError("WatcherHooks requires an agent with only local FunctionTools")
        if context.tool_name != tool.name:
            raise ValueError("Native tool and ToolContext names must match")
        await self.monitor.before(self.history, context.tool_call_id, tool.name, json.loads(context.tool_arguments))
