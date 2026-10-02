"""Observe a session produced by Continue's public version-one JSON export."""

import asyncio
import json
import os
import sys

from watcher_continue.conversion import normalize_messages
from watcher_continue.monitoring import observe
from watcher_sdk import AsyncWatcherClient

PREFIX = "continue:"


def convert(records: list[dict]) -> list[dict]:
    """Preserve exported messages and native tool states without inventing results.

    Continue stores completed tool outputs in toolCallStates on the calling
    assistant message. Their IDs and array order define the exported linkage.
    Text context items use Continue's documented source rendering. Incomplete
    tool states, compacted histories and non-text content fail explicitly.
    """
    history = []
    calls = set()
    results = set()
    for item in records:
        if item.get("conversationSummary"):
            raise ValueError("Compacted exports require branch-aware replay")
        message = item["message"]
        role = message["role"]
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("Unsupported exported message role")
        content = message["content"]
        if isinstance(content, list):
            if any(part["type"] != "text" for part in content):
                raise ValueError("Only text exports are supported")
            content = "".join(part["text"] for part in content)
        if not isinstance(content, str):
            raise ValueError("Expected exported text content")
        context_items = item["contextItems"]
        if context_items:
            if role != "user" or not isinstance(message["content"], str):
                raise ValueError("Unsupported exported context placement")
            content = (
                "".join(
                    f'<context name="{context["name"]}">\n{context["content"]}\n</context>\n\n'
                    for context in context_items
                )
                + content
            )
        if role == "tool":
            identity = message["toolCallId"]
            if identity not in calls or identity in results:
                raise ValueError("Missing or duplicate exported tool identity")
            results.add(identity)
            history.append(
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": identity, "content": content}]}
            )
            continue
        blocks = [{"type": "text", "text": content}] if content else []
        for call in message.get("toolCalls", []):
            identity = call["id"]
            if identity in calls:
                raise ValueError("Conflicting exported tool ID")
            calls.add(identity)
            blocks.append(
                {
                    "type": "tool_use",
                    "id": identity,
                    "name": call["function"]["name"],
                    "input": json.loads(call["function"]["arguments"]),
                }
            )
        if blocks:
            history.append({"role": role, "content": blocks})
        outputs = []
        for state in item.get("toolCallStates", []):
            identity = state["toolCallId"]
            if identity not in calls or identity in results:
                raise ValueError("Missing or duplicate exported tool identity")
            if state["status"] not in {"done", "errored"} or not state.get("output"):
                raise ValueError("Exported tool result is incomplete")
            results.add(identity)
            outputs.append(
                {
                    "type": "tool_result",
                    "tool_use_id": identity,
                    "content": "\n".join(output["content"] for output in state["output"]),
                    "is_error": state["status"] == "errored",
                }
            )
        if outputs:
            history.append({"role": "user", "content": outputs})
    if calls != results:
        raise ValueError("Export is missing a completed native tool result")
    return normalize_messages(history)


async def send(client: AsyncWatcherClient, session_id: str, messages: list[dict]) -> None:
    """Observe completed exported tools with historical prefixes and flush the final tail."""
    if not session_id:
        raise ValueError("A native session ID is required")
    await observe(client, PREFIX + session_id, messages)


async def run_export(exported: dict) -> None:
    """Submit one public export envelope after the native session has completed."""
    if exported["version"] != 1:
        raise ValueError("Unsupported Continue export version")
    session = exported["session"]
    session_id = session["sessionId"]
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("A native session ID is required")
    messages = convert(session["history"])
    if not messages or messages[-1]["role"] != "assistant" or messages[-1].get("tool_calls"):
        raise ValueError("Export does not end with a final assistant response")
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        await send(client, session_id, messages)


def main() -> int:
    """Read an explicit export on stdin and report delivery failure without leaking content."""
    try:
        asyncio.run(run_export(json.load(sys.stdin)))
    except Exception:
        sys.stderr.write("Watcher export observation failed; transcript was not confirmed recorded.\n")
        return 1
    sys.stdout.write("{}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
