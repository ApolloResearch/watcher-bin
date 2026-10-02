"""Native completion hook to public Watcher SDK; see README for supported transcript shapes."""

import asyncio
import json
import os
import sys
from pathlib import Path

from watcher_mistral_vibe.conversion import normalize_chat
from watcher_mistral_vibe.monitoring import observe
from watcher_sdk import AsyncWatcherClient

PREFIX = "mistral-vibe:"


def convert(records: list[dict]) -> list[dict]:
    """Convert the harness's Chat Completions message snapshot without adding a turn.

    Multimodal resource attachments and compaction require harness-specific replay;
    reject them instead of silently losing their context.
    """
    if any(row.get("images") or row.get("resources") or row.get("context_boundary") for row in records):
        raise ValueError("Attachments and compaction are not supported")
    return normalize_chat(records)


async def send(client: AsyncWatcherClient, session_id: str, messages: list[dict]) -> None:
    """Observe captured tools against their historical context, then record the final tail.

    Native execution has already occurred. No Watcher result changes tool output or
    permissions. Failures propagate to the observation-only native boundary.
    """
    if not session_id:
        raise ValueError("A native session ID is required")
    await observe(client, PREFIX + session_id, messages)


async def run_hook(payload: dict) -> None:
    """Read the native full transcript on each completion hook, without local cursors."""
    path = payload["transcript_path"]
    if not isinstance(path, str) or not path:
        raise ValueError("The native hook did not supply a transcript path")
    records = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    messages = convert(records)
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        await send(client, payload["session_id"], messages)


def main() -> None:
    """Consume native hook stdin. Observation failures never block the coding agent.

    Emit only a neutral hook response and a static diagnostic: transcript content,
    paths, credentials and server error bodies are never copied to stderr.
    """
    try:
        asyncio.run(run_hook(json.load(sys.stdin)))
    except Exception:
        sys.stderr.write("Watcher observation failed; transcript was not confirmed recorded.\n")
    sys.stdout.write("{}\n")


if __name__ == "__main__":
    main()
