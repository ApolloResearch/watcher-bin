"""Credential-free native model/tool fixture; main records it to a real Watcher."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from watcher_sdk import AsyncWatcherClient
from watcher_vercel_ai_bridge.adapter import observe


async def run_conversation():
    """Execute the actual Node SDK and read its unmodified native JSON export."""
    process = await asyncio.create_subprocess_exec(
        os.environ.get("WATCHER_VERCEL_NODE", "watcher-vercel-ai-native"),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
    if process.returncode:
        raise RuntimeError(stderr.decode())
    return json.loads(stdout)


async def main():
    """Send the deterministic native run to the configured real Watcher server."""
    messages = await run_conversation()
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        outcomes = await observe(client, str(uuid4()), messages)
        json.dump([outcome.to_dict() for outcome in outcomes], sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
