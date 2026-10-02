"""Native completion hook to public Watcher SDK; see README for supported transcript shapes."""

import asyncio
import json
import os
import sys
from pathlib import Path

from watcher_openclaw_bridge.checkpoint import state_path
from watcher_openclaw_bridge.conversion import normalize_messages
from watcher_openclaw_bridge.monitoring import observe
from watcher_sdk import AsyncWatcherClient

PREFIX = "openclaw:"


def convert(records: list[dict]) -> list[dict]:
    """Translate OpenClaw AgentMessage values, retaining parallel IDs and result errors.

    The extension supplies the current branch's message entries; custom messages
    and images are deliberately rejected until an explicit converter exists.
    Tool names stay exactly as supplied by native dispatch and its pre-tool hook.
    """
    history = []
    for row in records:
        role = row["role"]
        if role == "toolResult":
            history.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": row["toolCallId"],
                            "content": row["content"],
                            "is_error": row["isError"],
                        }
                    ],
                }
            )
            continue
        if role not in {"assistant", "user"}:
            raise ValueError("Unsupported OpenClaw message role")
        content = row["content"]
        if isinstance(content, str):
            history.append({"role": role, "content": content})
            continue
        blocks = []
        for block in content:
            if block["type"] == "toolCall":
                name = block["name"]
                blocks.append({"type": "tool_use", "id": block["id"], "name": name, "input": block["arguments"]})
            elif block["type"] == "text":
                blocks.append({"type": "text", "text": block["text"]})
            elif block["type"] == "thinking":
                blocks.append({"type": "thinking", "thinking": block["thinking"]})
            else:
                raise ValueError("Unsupported OpenClaw content")
        history.append({"role": role, "content": blocks})
    return normalize_messages(history)


async def send(
    client: AsyncWatcherClient,
    session_id: str,
    messages: list[dict],
    *,
    checkpoint_path: Path | None = None,
    record_only: bool = False,
) -> None:
    """Record the snapshot first, then check tools against their historical context.

    Set record_only after synchronous monitoring to submit the final transcript
    without retrospective grades overwriting earlier applied decisions. An upload
    response alone does not establish durable storage.

    Native execution has already occurred. No Watcher result changes tool output or
    permissions. Failures propagate to the observation-only native boundary.
    Pass a checkpoint path to resume grading across callbacks. Without one, each
    invocation is stateless and attempts all calls within its work budget.
    """
    if not session_id:
        raise ValueError("A native session ID is required")
    if record_only:
        outcomes = await client.pre_tool_use_hook(
            input=[], messages=messages, external_ids={"other": PREFIX + session_id}, timeout=10
        )
        if outcomes != []:
            raise ValueError("Transcript-only submission returned unexpected outcomes")
        return
    await observe(client, PREFIX + session_id, messages, checkpoint_path=checkpoint_path)


async def run_hook(payload: dict) -> None:
    """Consume the native plugin's snapshot; stdout remains the hook control channel."""
    messages = convert(payload["messages"])
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        identity = PREFIX + payload["session_id"]
        if not payload["session_id"]:
            raise ValueError("A native session ID is required")
        await send(
            client,
            payload["session_id"],
            messages,
            record_only=payload.get("record_only") is True,
            checkpoint_path=state_path(identity, os.environ["WATCHER_URL"], os.environ["WATCHER_API_KEY"]),
        )


def main() -> int:
    """Consume native hook stdin. Report observation failure to the plugin, which logs it without blocking.

    Emit only a neutral hook response and a static diagnostic: transcript content,
    paths, credentials and server error bodies are never copied to stderr.
    """
    try:
        asyncio.run(run_hook(json.load(sys.stdin)))
    except Exception:
        sys.stderr.write("Watcher did not finish observing this turn.\n")
        return 1
    sys.stdout.write("{}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
