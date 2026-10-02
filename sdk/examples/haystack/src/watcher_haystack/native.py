"""Haystack chat-generator component that gates output before Agent dispatch."""

import asyncio
from copy import deepcopy

from haystack import component
from haystack.dataclasses import ChatMessage

from watcher_haystack.monitoring import ToolBlocked


@component
class MonitoredGenerator:
    """Wrap a non-streaming generator and pass it to Agent(chat_generator=...).

    Use Agent.run_async. This component awaits every pending decision before
    returning replies to the native Agent and ToolInvoker. A refused sibling
    withholds the entire response. The underlying generator must return exactly
    one complete ChatMessage per turn and accept messages and tools. Supply the
    same Monitor for final transcript submission after each Agent run.
    """

    def __init__(self, generator, monitor):
        self.generator = generator
        self.monitor = monitor

    def warm_up(self):
        if hasattr(self.generator, "warm_up"):
            self.generator.warm_up()

    @component.output_types(replies=list[ChatMessage])
    def run(self, messages: list[ChatMessage], tools=None):
        raise RuntimeError("MonitoredGenerator requires Agent.run_async")

    @component.output_types(replies=list[ChatMessage])
    async def run_async(self, messages: list[ChatMessage], tools=None):
        """Preserve model input and original IDs while awaiting applied decisions."""
        history = deepcopy(messages)
        if hasattr(self.generator, "run_async"):
            result = await self.generator.run_async(messages=messages, tools=tools)
        else:
            result = await asyncio.to_thread(self.generator.run, messages=messages, tools=tools)
        replies = result.get("replies")
        if not isinstance(replies, list) or len(replies) != 1 or not isinstance(replies[0], ChatMessage):
            raise ToolBlocked("Exactly one complete native model reply is required")
        pending = replies[0]
        history.append(pending)
        for call in pending.tool_calls:
            await self.monitor.before(history, call.id, call.tool_name, call.arguments)
        return {"replies": replies}
