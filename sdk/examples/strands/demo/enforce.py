"""Synchronous Strands before-tool hook, bridged to an independent Watcher loop."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from strands import tool
from watcher_strands.adapter import messages_for_watcher
from watcher_strands.monitoring import Monitor
from watcher_strands.native import WatcherAgent, agent_history

from demo.observe import DeterministicModel
from watcher_sdk import AsyncWatcherClient


async def run_conversation(monitor, effect=lambda value: str(value * 2), *, system_prompt: str | None = None):
    """Run native tools on a worker and record their history with the configured system prompt."""

    @tool
    def double(value: int) -> str:
        """Double an integer."""
        return effect(value)

    agent = WatcherAgent(
        monitor,
        asyncio.get_running_loop(),
        model=DeterministicModel(),
        system_prompt=system_prompt,
        tools=[double],
        callback_handler=None,
    )
    await asyncio.to_thread(agent, "Double 2 and 3")
    history = agent_history(agent)
    await monitor.record(history)
    return history


async def main():
    """Execute the local arithmetic tools under the configured Watcher policy."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        monitor = Monitor(client, str(uuid4()), timeout=float(os.environ.get("WATCHER_TIMEOUT", "420")))
        messages = await run_conversation(monitor)
        json.dump(messages_for_watcher(messages), sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
