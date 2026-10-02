"""A LangChain create_agent tool loop with Watcher middleware and a local model."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from watcher_langchain.adapter import messages_for_watcher
from watcher_langchain.monitoring import Monitor
from watcher_langchain.native import WatcherMiddleware

from demo.observe import fixture_model
from watcher_sdk import AsyncWatcherClient


async def run_conversation(monitor, effect=lambda value: str(value * 2)):
    """Drive native agent scheduling and retain the runner's actual full history."""

    @tool
    def double(value: int) -> str:
        """Double an integer."""
        return effect(value)

    agent = create_agent(fixture_model(), tools=[double], middleware=[WatcherMiddleware(monitor)])
    result = await agent.ainvoke({"messages": [HumanMessage(content="Double 2 and 3")]})
    await monitor.record(result["messages"])
    return result["messages"]


async def main():
    """Execute native tools using the configured Watcher policy."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        messages = await run_conversation(
            Monitor(client, str(uuid4()), timeout=float(os.environ.get("WATCHER_TIMEOUT", "420")))
        )
        json.dump(messages_for_watcher(messages), sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
