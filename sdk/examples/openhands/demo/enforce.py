"""Connect a configured OpenHands Agent to recorded synchronous tool approval.

Call run_monitored(agent, prompt, cwd) with your existing native Agent and tools.
Only conversation.run() is covered; native confirmation policy remains in force.
"""

import asyncio
import os
from pathlib import Path

from openhands.sdk import Agent
from openhands.sdk.conversation import LocalConversation
from watcher_openhands.integration import convert, send
from watcher_openhands.synchronous import EnforcementRecorder

from watcher_sdk import AsyncWatcherClient


def client() -> AsyncWatcherClient:
    return AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"])


async def run_monitored(agent: Agent, prompt: str, cwd: str) -> None:
    """Bind before execution and retain final observation even when execution fails."""
    recorder = EnforcementRecorder(client)
    conversation = LocalConversation(
        agent=agent, workspace=cwd, callbacks=[recorder], profile_store_dir=Path(cwd) / ".openhands-profiles"
    )
    recorder.bind(conversation)
    try:
        conversation.send_message(prompt)
        await asyncio.to_thread(conversation.run)
    finally:
        async with client() as watcher:
            await send(watcher, str(conversation.id), convert(recorder.messages), record_only=True)
