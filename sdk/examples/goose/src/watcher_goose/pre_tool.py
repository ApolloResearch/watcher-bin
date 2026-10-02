"""Native pre-tool hook using the public session history/export API."""

import asyncio
import json
import os
import sys
from contextlib import suppress

from watcher_goose.enforcement import apply_policy
from watcher_goose.integration import convert
from watcher_sdk import AsyncWatcherClient


async def run_hook(payload: dict) -> None:
    """Read current public native history and wait for approval of this pending ID."""
    if payload["event"] != "PreToolUse":
        raise ValueError("Only pre-tool callbacks are supported")
    session_id = payload["session_id"]
    call = {"id": payload["tool_call_id"], "function": payload["tool_name"], "arguments": payload["tool_input"]}
    command = ["goose", "session", "export", "--session-id", session_id, "--format", "json"]
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
    records = json.loads(output)["conversation"]
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        await apply_policy(client, session_id, convert(records), call, cwd=payload.get("working_dir"))


def main() -> None:
    """Return the native denial shape for every non-allow and bridge failure."""
    allowed = False
    try:
        asyncio.run(run_hook(json.load(sys.stdin)))
        allowed = True
    except Exception:
        sys.stderr.write("Watcher did not confirm approval; tool withheld.\n")
    output = {"decision": "allow"} if allowed else {"decision": "block", "reason": "Watcher did not confirm approval"}
    sys.stdout.write(json.dumps(output) + "\n")


if __name__ == "__main__":
    main()
