"""Native completion hook to public Watcher SDK; see README for supported transcript shapes."""

import asyncio
import json
import os
import sys

from watcher_sdk import AsyncWatcherClient

PREFIX = "roo-code:"


def convert(records: list[dict]) -> list[dict]:
    """Archive finalized Roo UI text only; public UI events lack model tool IDs."""
    latest = {}
    for row in records:
        message = row["message"]
        latest[message["ts"]] = message
    messages = []
    for message in latest.values():
        if message.get("partial") or message.get("say") not in {"text", "user_feedback", "completion_result"}:
            continue
        messages.append(
            {"role": "user" if message["say"] == "user_feedback" else "assistant", "content": message["text"]}
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
