"""Bridge the native plugin's pending call to the public Watcher SDK."""

import asyncio
import json
import os
import sys

from watcher_pi_bridge.enforcement import apply_policy
from watcher_pi_bridge.integration import convert
from watcher_sdk import AsyncWatcherClient


async def run_hook(payload: dict) -> None:
    """Await approval using a native snapshot and the exact pending callback identity."""
    messages = convert(payload["messages"])
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        await apply_policy(client, payload["session_id"], messages, payload["call"], cwd=payload.get("cwd"))


def main() -> int:
    """No output or a nonzero exit is a denial to approval.mjs, never an allow."""
    try:
        payload = json.load(sys.stdin)
        asyncio.run(run_hook(payload))
    except Exception:
        sys.stderr.write("Watcher did not confirm approval; tool withheld.\n")
        return 1
    sys.stdout.write(
        json.dumps({"allow": True, "session_id": payload["session_id"], "tool_use_id": payload["call"]["id"]}) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
