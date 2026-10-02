"""Send one synthetic native provider turn, then flush its Watcher observation."""

import asyncio
import os
import sys
from uuid import uuid4

from watcher_mistralai.integration import Observation, complete, make_client

from watcher_sdk import AsyncWatcherClient


async def main() -> None:
    session_id = str(uuid4())
    async with (
        make_client(os.environ["PROVIDER_API_KEY"], os.environ["PROVIDER_BASE_URL"]) as provider,
        AsyncWatcherClient(os.environ["WATCHER_BASE_URL"], api_key=os.environ["WATCHER_API_KEY"]) as watcher,
    ):
        observation = Observation(watcher, session_id)
        await complete(
            provider,
            observation,
            model=os.environ["PROVIDER_MODEL"],
            messages=[{"role": "user", "content": "Reply with exactly: integration example"}],
        )
        await observation.flush()
        if observation.errors:
            raise RuntimeError(", ".join(observation.errors))
    sys.stdout.write(f"Submitted conversation {session_id}; verify it in Analyzer.\n")


if __name__ == "__main__":
    asyncio.run(main())
