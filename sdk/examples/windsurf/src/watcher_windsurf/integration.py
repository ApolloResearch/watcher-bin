"""Native completion hook to public Watcher SDK; see README for supported transcript shapes."""

import asyncio
import json
import os
import sys
from pathlib import Path

from watcher_sdk import AsyncWatcherClient

PREFIX = "windsurf:"


def convert(records: list[dict]) -> list[dict]:
    """Keep documented native text/actions without fabricating tool-call IDs.

    The published step schema has no stable tool identity. Actions remain opaque
    metadata with their native step type, not falsely linked Inspect tool calls.
    """
    messages = []
    for row in records:
        if row["type"] == "user_input":
            messages.append({"role": "user", "content": row["user_input"]["user_response"]})
        elif row["type"] == "planner_response":
            messages.append({"role": "assistant", "content": row["planner_response"]["response"]})
        else:
            messages.append(
                {
                    "role": "assistant",
                    "content": "Native action: " + row["type"],
                    "metadata": {"native_step": json.loads(json.dumps(row))},
                }
            )
    return messages


async def send(client: AsyncWatcherClient, session_id: str, messages: list[dict]) -> None:
    """Record a full snapshot, including final text; wait for recording acknowledgement.

    This is transcript-only observation: no pending calls are graded or blocked.
    The caller owns retry policy. A timeout may follow successful server storage.
    """
    if not session_id:
        raise ValueError("A native session ID is required")
    await client.pre_tool_use_hook(
        input=[],
        messages=messages,
        external_ids={"other": PREFIX + session_id},
        timeout=10,
    )


async def run_hook(payload: dict) -> None:
    """Read the full transcript supplied by post_cascade_response_with_transcript."""
    path = Path(payload["tool_info"]["transcript_path"])
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        await send(client, path.stem, convert(records))


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
