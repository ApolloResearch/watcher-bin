"""Run the native observer in the current disposable workspace with explicit credentials.

Set PROMPT and the variables in .env.example; model-backed examples also need
their provider credentials. This demo intentionally uses the configured services.
"""

import asyncio
import os

from watcher_openhands.integration import run_openhands

from watcher_sdk import AsyncWatcherClient


async def main() -> None:
    """Observe the completed native run using the installed adapter."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        await run_openhands(os.environ["PROMPT"], os.getcwd(), os.environ["MODEL_NAME"], client)


if __name__ == "__main__":
    asyncio.run(main())
