"""Run CAMEL's native tool loop with Watcher before every dispatch."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from camel.agents import ChatAgent
from camel.types import ModelType
from watcher_camel.adapter import messages_for_watcher
from watcher_camel.monitoring import Monitor
from watcher_camel.native import MonitoredModel

from demo.observe import DeterministicModel
from watcher_sdk import AsyncWatcherClient


async def run_conversation(monitor, effect=lambda value: str(value * 2)):
    """Drive actual ChatAgent.astep, then submit its retained tool results and answer."""

    def double(value: int) -> str:
        """Double an integer.

        Args:
            value: Integer to double.
        """
        return effect(value)

    model = MonitoredModel(DeterministicModel(ModelType.STUB), monitor)
    agent = ChatAgent(model=model, tools=[double], max_iteration=3, prune_tool_calls_from_memory=False)
    await agent.astep("Double 2 and 3")
    messages, _ = agent.memory.get_context()
    await monitor.record(messages)
    return messages


async def main():
    """Execute local arithmetic under the configured Watcher policy."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        messages = await run_conversation(Monitor(client, str(uuid4())))
        json.dump(messages_for_watcher(messages), sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
