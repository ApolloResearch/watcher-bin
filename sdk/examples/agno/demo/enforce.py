"""Application-owned Agno FunctionCall execution with exact native call identity."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from agno.models.message import Message
from agno.tools.function import Function, FunctionCall
from watcher_agno.adapter import messages_for_watcher
from watcher_agno.monitoring import Monitor
from watcher_agno.native import CaptureModelCalls, WatcherAgent, execute_tool

from demo.observe import DeterministicModel
from watcher_sdk import AsyncWatcherClient


async def run_dispatch_conversation(monitor, effect=lambda value: str(value * 2)):
    """Run native provider messages and FunctionCall dispatch before final recording."""

    async def double(value: int) -> str:
        """Double an integer."""
        return effect(value)

    function = Function.from_callable(double)
    model = DeterministicModel(id="deterministic")
    history = [Message(role="user", content="Double 2 and 3")]
    response = await model.ainvoke(history)
    history.append(Message(role="assistant", content=response.content, tool_calls=response.tool_calls))
    calls = [
        FunctionCall(function=function, arguments=json.loads(call["function"]["arguments"]), call_id=call["id"])
        for call in response.tool_calls
    ]
    history.extend(await asyncio.gather(*(execute_tool(monitor, history, call) for call in calls)))
    history.append(Message(role="assistant", content=(await model.ainvoke(history)).content))
    await monitor.record(history)
    return history


class MonitoredModel(CaptureModelCalls, DeterministicModel):
    """The local provider fixture with native input-history capture enabled."""


async def run_conversation(monitor, effect=lambda value: str(value * 2)):
    """Run native Agent.arun and its parallel Function pre-hooks before tool bodies."""

    async def double(value: int) -> str:
        """Double an integer."""
        return effect(value)

    model = MonitoredModel(id="deterministic")
    function = Function.from_callable(double)
    result = await WatcherAgent(monitor, model=model, tools=[function], telemetry=False).arun("Double 2 and 3")
    await monitor.record(result.messages)
    return result.messages


async def main():
    """Execute the local arithmetic tools under the configured Watcher policy."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        monitor = Monitor(client, str(uuid4()), timeout=float(os.environ.get("WATCHER_TIMEOUT", "420")))
        messages = await run_conversation(monitor)
        json.dump(messages_for_watcher(messages), sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
