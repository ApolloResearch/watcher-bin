"""Run LlamaIndex's native FunctionAgent workflow under Watcher policy."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from llama_index.core.memory import ChatMemoryBuffer
from watcher_llamaindex.adapter import messages_for_watcher
from watcher_llamaindex.monitoring import Monitor
from watcher_llamaindex.native import MonitoredFunctionAgent

from demo.observe import DeterministicModel
from watcher_sdk import AsyncWatcherClient


async def run_conversation(monitor, effect=lambda value: str(value * 2)):
    """Let the workflow dispatch tools, handle results and finalize its memory."""

    def double(value: int) -> str:
        """Double an integer."""
        return effect(value)

    memory = ChatMemoryBuffer.from_defaults(token_limit=10000)
    agent = MonitoredFunctionAgent(monitor=monitor, llm=DeterministicModel(max_tokens=None), tools=[double])
    await agent.run(user_msg="Double 2 and 3", memory=memory)
    messages = memory.get_all()
    await monitor.record(messages)
    return messages


async def main():
    """Execute local arithmetic under the configured Watcher policy."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        messages = await run_conversation(Monitor(client, str(uuid4())))
        json.dump(messages_for_watcher(messages), sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
