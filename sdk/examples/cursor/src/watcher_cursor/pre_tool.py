"""Cursor preToolUse enforcement using the existing partial-context event journal.

Native dispatch is unverified without an authenticated Cursor service. This
command is an opt-in replacement for the observation-only preToolUse entry;
retain every other observation hook from hooks.example.json.
"""

import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

from watcher_cursor.enforcement import apply_policy
from watcher_cursor.integration import CALL_EVENT, EVENT_FIELD, SESSION_FIELD, convert
from watcher_cursor.integration import run_hook as journal_event
from watcher_sdk import AsyncWatcherClient


async def run_hook(payload: dict) -> None:
    """Journal the native pending event, then grade its observed context before allowing."""
    if payload[EVENT_FIELD] != CALL_EVENT:
        raise ValueError("Only preToolUse is supported")
    await journal_event(payload)
    session_id = payload[SESSION_FIELD]
    with sqlite3.connect(Path(os.environ["WATCHER_STATE_DIR"]) / "native-events.sqlite3", timeout=5) as database:
        records = [
            json.loads(row[0])
            for row in database.execute("SELECT payload FROM events WHERE session=? ORDER BY seq", (session_id,))
        ]
    call = {"id": payload["tool_use_id"], "function": payload["tool_name"], "arguments": payload["tool_input"]}
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        await apply_policy(client, session_id, convert(records), call)


def main() -> int:
    """Deny on malformed input, transport failure or any incomplete/non-allow judgment."""
    try:
        asyncio.run(run_hook(json.load(sys.stdin)))
    except Exception:
        sys.stdout.write('{"permission":"deny","user_message":"Watcher did not confirm approval"}\n')
        return 2
    sys.stdout.write('{"permission":"allow"}\n')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
