"""AssistantAgent runs native tools after Watcher releases its pending event stream."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from autogen_agentchat.agents import AssistantAgent
from watcher_autogen.adapter import messages_for_watcher
from watcher_autogen.monitoring import Monitor
from watcher_autogen.native import run_monitored

from demo.observe import fixture_model
from watcher_sdk import AsyncWatcherClient


async def run_conversation(monitor, effect=lambda value: str(value * 2)):
    """Run the actual AssistantAgent scheduler using a credential-free replay model."""

    def double(value: int) -> str:
        """Double an integer."""
        return effect(value)

    model = fixture_model()
    agent = AssistantAgent("example", model_client=model, tools=[double], reflect_on_tool_use=True, system_message=None)
    try:
        return await run_monitored(agent, monitor, task="Double 2 and 3")
    finally:
        await model.close()


async def main():
    """Submit native pending calls and actual results to the configured Watcher."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        messages = await run_conversation(
            Monitor(client, str(uuid4()), timeout=float(os.environ.get("WATCHER_TIMEOUT", "420")))
        )
        json.dump(messages_for_watcher(messages), sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
