"""Run a native Haystack Agent with Watcher before its ToolInvoker."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from haystack.components.agents import Agent
from haystack.dataclasses import ChatMessage
from haystack.tools import Tool
from watcher_haystack.adapter import messages_for_watcher
from watcher_haystack.monitoring import Monitor
from watcher_haystack.native import MonitoredGenerator

from demo.observe import DeterministicGenerator
from watcher_sdk import AsyncWatcherClient


async def run_conversation(monitor, effect=lambda value: str(value * 2)):
    """Use Agent.run_async for model iteration, native execution and final history."""

    def double(value: int) -> str:
        return effect(value)

    tool = Tool(
        name="double",
        description="Double an integer",
        function=double,
        parameters={"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"]},
    )
    agent = Agent(
        chat_generator=MonitoredGenerator(DeterministicGenerator(), monitor),
        tools=[tool],
        max_agent_steps=3,
        raise_on_tool_invocation_failure=False,
        tool_invoker_kwargs={"convert_result_to_json_string": False},
    )
    agent.warm_up()
    result = await agent.run_async(messages=[ChatMessage.from_user("Double 2 and 3")])
    await monitor.record(result["messages"])
    return result["messages"]


async def main():
    """Execute local arithmetic under the configured Watcher policy."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        messages = await run_conversation(Monitor(client, str(uuid4())))
        json.dump(messages_for_watcher(messages), sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
