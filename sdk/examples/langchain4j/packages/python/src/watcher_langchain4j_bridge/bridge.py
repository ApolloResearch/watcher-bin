"""Submit completed native-step snapshots through the public Python Watcher SDK.

Snapshots are ordinary Inspect chat-message dictionaries, not a new wire schema.
This post-run bridge observes tools after execution and cannot enforce a denial.
"""

import asyncio
import json
import os
from pathlib import Path

from watcher_langchain4j_bridge.observation import ObservationQueue
from watcher_sdk import AsyncWatcherClient


async def observe_snapshots(watcher: AsyncWatcherClient, paths: list[Path], session_id: str) -> ObservationQueue:
    """Submit snapshots in order and grade each native tool identity once.

    Files must be ordered by the caller. Each tool is judged with its historical
    prefix, in batches of at most 32, before the full snapshot is recorded.
    Submission failures are counted and do not prevent the final-tail attempt.
    """
    observation = ObservationQueue(watcher, session_id)
    seen = set()
    for path in paths:
        messages = json.loads(path.read_text())
        for index, message in enumerate(messages):
            inputs = []
            for call in message.get("tool_calls", []):
                if call["id"] not in seen:
                    inputs.append(
                        {"tool_use_id": call["id"], "tool_name": call["function"], "tool_input": call["arguments"]}
                    )
                    seen.add(call["id"])
            for start in range(0, len(inputs), 32):
                observation.enqueue(messages[: index + 1], inputs[start : start + 32])
                await observation.flush()
        observation.enqueue(messages, [])
        await observation.flush()
    return observation


async def main() -> None:
    paths = sorted(Path(os.environ["SNAPSHOT_DIR"]).glob("*.json"), key=lambda path: int(path.stem))
    if not paths:
        raise ValueError("No native snapshots found")
    async with AsyncWatcherClient(os.environ["WATCHER_BASE_URL"], api_key=os.environ["WATCHER_API_KEY"]) as watcher:
        observation = await observe_snapshots(watcher, paths, os.environ["WATCHER_SESSION_ID"])
        if observation.error_count:
            raise RuntimeError(", ".join(observation.errors))


if __name__ == "__main__":
    asyncio.run(main())
