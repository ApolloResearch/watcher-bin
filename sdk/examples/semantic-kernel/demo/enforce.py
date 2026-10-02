"""Native ChatCompletionAgent function invocation monitored before execution."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from watcher_semantic_kernel.adapter import messages_for_watcher
from watcher_semantic_kernel.monitoring import Monitor

from demo.observe import run_native
from watcher_sdk import AsyncWatcherClient


async def run_conversation(monitor, effect=lambda value: str(value * 2)):
    """Use the registered automatic-invocation filter during the native agent loop."""
    return await run_native(monitor, effect)


async def main():
    """Execute tools under the server's configured policy and submit actual history."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        messages = await run_conversation(
            Monitor(client, str(uuid4()), timeout=float(os.environ.get("WATCHER_TIMEOUT", "420")))
        )
        json.dump(messages_for_watcher(messages), sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
