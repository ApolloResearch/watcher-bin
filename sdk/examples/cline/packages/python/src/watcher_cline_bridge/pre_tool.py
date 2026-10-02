"""Native pre-tool hook using the public session history/export API."""

import asyncio
import json
import os
import sys
from contextlib import suppress

from watcher_cline_bridge.enforcement import apply_policy
from watcher_cline_bridge.integration import convert
from watcher_sdk import AsyncWatcherClient


async def run_hook(payload: dict) -> None:
    """Read current public native history and wait for approval of this pending ID."""
    if payload["hookName"] != "tool_call" or payload.get("parent_agent_id"):
        raise ValueError("Only root-session tool callbacks are supported")
    session_id = payload["sessionContext"]["rootSessionId"]
    native = payload["tool_call"]
    call = {"id": native["id"], "function": native["name"], "arguments": native["input"]}
    command = [os.environ.get("WATCHER_HISTORY_READER", "watcher-cline-history"), session_id]
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        async with asyncio.timeout(25):
            output, _ = await process.communicate()
    except (TimeoutError, asyncio.CancelledError):
        with suppress(ProcessLookupError):
            process.kill()
        await process.communicate()
        raise
    if process.returncode:
        raise ValueError("Native public history reader failed")
    records = json.loads(output)
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        await apply_policy(client, session_id, convert(records), call)


def main() -> None:
    """Return the native denial shape for every non-allow and bridge failure."""
    allowed = False
    try:
        asyncio.run(run_hook(json.load(sys.stdin)))
        allowed = True
    except Exception:
        sys.stderr.write("Watcher did not confirm approval; tool withheld.\n")
    output = {} if allowed else {"cancel": True, "errorMessage": "Watcher did not confirm approval"}
    sys.stdout.write(json.dumps(output) + "\n")


if __name__ == "__main__":
    main()
