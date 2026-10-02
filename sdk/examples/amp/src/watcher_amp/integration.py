"""Native completion hook to public Watcher SDK; see README for supported transcript shapes."""

import asyncio
import json
import os
import sys

from amp_sdk import AmpOptions, execute

from watcher_amp.conversion import normalize_messages
from watcher_amp.monitoring import observe
from watcher_sdk import AsyncWatcherClient

PREFIX = "amp:"


def convert(records: list[dict]) -> list[dict]:
    """Normalize native user/assistant message records, preserving tool IDs and results.

    UI/progress records do not enter model context. Reject compacted histories;
    this example covers a single linear, uncompacted conversation only.
    Unsupported provider blocks fail visibly rather than being converted to text.
    """
    if any(record.get("subtype") == "compact_boundary" for record in records):
        raise ValueError("Compacted histories require branch-aware replay")
    history = [record["message"] for record in records if record.get("type") in {"user", "assistant"}]
    return normalize_messages(history)


async def run_amp(prompt: str, cwd: str, client: AsyncWatcherClient) -> None:
    """Consume Amp's native execute stream, then observe it after the run settles.

    Amp owns its normal tools and permissions. The callback does not cancel or
    alter tool execution. A failed stream still flushes the captured prefix.
    """
    records = []
    session_id = None
    try:
        async for event in execute(prompt, AmpOptions(cwd=cwd)):
            row = event.model_dump(mode="json", exclude_none=True)
            session_id = row["session_id"]
            if row.get("parent_tool_use_id"):
                raise ValueError("Subagent streams need separate conversations")
            if row["type"] in {"user", "assistant"}:
                records.append(row)
    finally:
        if session_id and records:
            await send(client, session_id, convert(records))


async def send(client: AsyncWatcherClient, session_id: str, messages: list[dict]) -> None:
    """Observe captured tools against their historical context, then record the final tail.

    Native execution has already occurred. No Watcher result changes tool output or
    permissions. Failures propagate to the observation-only native boundary.
    """
    if not session_id:
        raise ValueError("A native session ID is required")
    await observe(client, PREFIX + session_id, messages)


async def run_hook(payload: dict) -> None:
    """Consume the native plugin's snapshot; stdout remains the hook control channel."""
    messages = convert(payload["messages"])
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
