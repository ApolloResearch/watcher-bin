"""Gate smolagents' native pre-execution ToolCall stream before resuming it."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from smolagents import ToolCallingAgent, tool
from watcher_smolagents.adapter import messages_for_watcher
from watcher_smolagents.monitoring import Monitor
from watcher_smolagents.native import CapturedModel, consume

from demo.observe import DeterministicModel
from watcher_sdk import AsyncWatcherClient


async def run_conversation(monitor, effect=lambda value: str(value * 2)):
    """Run native ToolCallingAgent and its real parallel tool stream without prefetch."""

    @tool
    def double(value: int) -> str:
        """Double an integer.

        Args:
            value: Integer to double.
        """
        return effect(value)

    model = CapturedModel(DeterministicModel())
    agent = ToolCallingAgent(model=model, tools=[double], verbosity_level=0)
    return await consume(monitor, agent, model, "Double 2 and 3")


async def main():
    """Execute the local arithmetic tools under the configured Watcher policy."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        monitor = Monitor(client, str(uuid4()), timeout=float(os.environ.get("WATCHER_TIMEOUT", "420")))
        messages = await run_conversation(monitor)
        json.dump(messages_for_watcher(messages), sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
