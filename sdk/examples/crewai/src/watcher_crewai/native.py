"""Reusable CrewAI execution boundary for synchronous Watcher monitoring.

Use these adapters with one Monitor per conversation. The runnable clients in
demo/enforce.py show native registration and final transcript recording.
"""

import asyncio
from uuid import uuid4

from crewai.agents.parser import AgentFinish

from watcher_crewai.adapter import WatcherTrace


class MonitoredTrace(WatcherTrace):
    """Retain model context and assign each CrewAI ReAct tool an ID before execution.

    CrewAI 1.3.0's ReAct actions have no native tool IDs. This application-owned
    wrapper assigns one UUID per invocation and reuses it in the actual result.
    step_callback is observation only and cannot authorize side effects.
    """

    def __init__(self, monitor, loop, prompt):
        super().__init__(prompt)
        self.monitor = monitor
        self.loop = loop

    def invoke(self, name, arguments, execute):
        """Gate a registered synchronous callable running in CrewAI's worker thread."""
        call_id = str(uuid4())
        self.messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": call_id, "function": name, "arguments": dict(arguments)}],
            }
        )
        try:
            asyncio.run_coroutine_threadsafe(
                self.monitor.before(self.messages, call_id, name, arguments), self.loop
            ).result()
            result = execute(**arguments)
        except Exception:
            self.messages.append(
                {
                    "role": "tool",
                    "content": "Tool withheld or failed",
                    "tool_call_id": call_id,
                    "error": {"type": "unknown", "message": "Tool withheld or failed"},
                }
            )
            raise
        self.messages.append({"role": "tool", "content": result, "tool_call_id": call_id})
        return result

    def on_step(self, step):
        if isinstance(step, AgentFinish):
            self.finish(step.output)
