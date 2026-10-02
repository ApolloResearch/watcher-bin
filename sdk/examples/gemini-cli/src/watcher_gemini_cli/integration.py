"""Native completion hook to public Watcher SDK; see README for supported transcript shapes."""

import asyncio
import json
import os
import sys
from pathlib import Path

from watcher_gemini_cli.conversion import normalize_messages
from watcher_gemini_cli.monitoring import observe
from watcher_sdk import AsyncWatcherClient

PREFIX = "gemini-cli:"


def convert(records: list[dict]) -> list[dict]:
    """Rebuild Gemini's JSONL message updates by ID and preserve recorded tools.

    A repeated ID replaces an earlier record without moving its position.
    A $set.messages snapshot replaces all prior messages, including the initial
    session context, following the native recording loader.
    Standalone user functionResponse parts preserve actual delivery order and
    take precedence over the duplicate results stored on toolCalls. Older records
    with only inline results retain their tool-array ordering.
    """
    latest = {}
    for row in records:
        if "$rewindTo" in row:
            raise ValueError("Rewound sessions require branch-aware replay")
        if "id" in row:
            latest[row["id"]] = row
        elif "$set" in row and "messages" in row["$set"]:
            messages = row["$set"]["messages"]
            if not isinstance(messages, list):
                raise ValueError("Unsupported Gemini message snapshot")
            latest = {message["id"]: message for message in messages}
        elif "messages" in row:
            raise ValueError("Unsupported Gemini metadata record with messages")
    delivered_ids = {
        part["functionResponse"]["id"]
        for row in latest.values()
        if row["type"] == "user" and isinstance(row["content"], list)
        for part in row["content"]
        if isinstance(part, dict) and "functionResponse" in part
    }
    history = []
    for row in latest.values():
        if row["type"] not in {"user", "gemini"}:
            continue
        role = "assistant" if row["type"] == "gemini" else "user"
        content = row["content"]
        blocks: list[dict] = [{"type": "text", "text": content}] if isinstance(content, str) else []
        if not isinstance(content, str):
            for part in content:
                if not isinstance(part, dict):
                    raise ValueError("Unsupported Gemini content")
                if "text" in part:
                    blocks.append({"type": "text", "text": part["text"]})
                elif role == "user" and "functionResponse" in part:
                    result = part["functionResponse"]
                    blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": result["id"],
                            "content": json.dumps(result["response"], ensure_ascii=False),
                            "is_error": "error" in result["response"],
                        }
                    )
                else:
                    raise ValueError("Unsupported Gemini content")
        results = []
        for call in row.get("toolCalls", []):
            blocks.append({"type": "tool_use", "id": call["id"], "name": call["name"], "input": call["args"]})
            if call.get("result") is not None and call["id"] not in delivered_ids:
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call["id"],
                        "content": json.dumps(call["result"], ensure_ascii=False),
                        "is_error": call["status"] == "error",
                    }
                )
        if blocks:
            history.append({"role": role, "content": blocks})
        if results:
            history.append({"role": "user", "content": results})
    return normalize_messages(history)


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
