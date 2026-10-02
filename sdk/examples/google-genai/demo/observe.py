"""Run one native synthetic turn and require Watcher recording acknowledgement."""

import asyncio
import os
import sys
from uuid import uuid4

from google.genai import types
from watcher_google_genai.integration import Observation, complete, make_client

from watcher_sdk import AsyncWatcherClient


async def main():
    session_id = str(uuid4())
    async with AsyncWatcherClient(os.environ["WATCHER_BASE_URL"], api_key=os.environ["WATCHER_API_KEY"]) as watcher:
        observation = Observation(watcher, session_id)
        async with make_client(os.environ["PROVIDER_API_KEY"], os.environ["PROVIDER_BASE_URL"]) as provider:
            await complete(
                provider,
                observation,
                model=os.environ["PROVIDER_MODEL"],
                contents=[types.Content(role="user", parts=[types.Part(text="Reply exactly: integration example")])],
            )
        await observation.flush()
        if observation.error_count:
            raise RuntimeError(", ".join(observation.errors))
    sys.stdout.write(f"Submitted conversation {session_id}; verify its final message in Analyzer.\n")


if __name__ == "__main__":
    asyncio.run(main())
