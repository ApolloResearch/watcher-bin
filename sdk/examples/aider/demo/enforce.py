"""Gate real Aider write_text calls; run only in an intended disposable workspace.

Set PROMPT, MODEL_NAME, TARGET_FILE and Watcher/provider credentials explicitly.
The Watcher organization must enforce decisions. Normal Aider permissions remain.
"""

import asyncio
import os

from aider.coders import Coder
from watcher_aider.observation import Capture, ObservedModel, run_prompt, send_capture
from watcher_aider.synchronous import EnforcedIO

from watcher_sdk import AsyncWatcherClient


def client() -> AsyncWatcherClient:
    return AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"])


async def main() -> None:
    """Preserve captured operation IDs through enforcement and final observation."""
    capture = Capture()
    session_id = os.environ["WATCHER_SESSION_ID"]
    coder = Coder.create(
        main_model=ObservedModel(os.environ["MODEL_NAME"], capture),
        io=EnforcedIO(capture, session_id, client, yes=False, pretty=False),
        fnames=[os.environ["TARGET_FILE"]],
        edit_format="whole",
        stream=False,
        use_git=False,
    )
    try:
        await asyncio.to_thread(run_prompt, coder, capture, os.environ["PROMPT"])
    finally:
        async with client() as watcher:
            await send_capture(watcher, session_id, capture, record_only=True)


if __name__ == "__main__":
    asyncio.run(main())
