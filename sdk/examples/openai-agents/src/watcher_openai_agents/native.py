"""Reusable OpenAI Agents execution boundary for synchronous Watcher monitoring.

Use these adapters with one Monitor per conversation. The runnable clients in
demo/enforce.py show native registration and final transcript recording.
"""

import json
from copy import deepcopy

from agents import FunctionTool, RunHooks
from agents.tool_context import ToolContext


async def execute_tool(monitor, history, tool, call):
    """Gate a Responses function call before invoking the public FunctionTool handler."""
    if tool.name != call.name:
        raise ValueError("Selected function must match the model's tool name")
    await monitor.before(history, call.call_id, call.name, json.loads(call.arguments))
    context = ToolContext(context=None, tool_call_id=call.call_id, tool_name=call.name, tool_arguments=call.arguments)
    result = await tool.on_invoke_tool(context, call.arguments)
    return {"type": "function_call_output", "call_id": call.call_id, "output": result}


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
