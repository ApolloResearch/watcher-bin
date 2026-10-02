"""Native pre-tool command hook; unsuccessful decisions return a native denial."""

import asyncio
import json
import os
import sys
from pathlib import Path

from watcher_qwen_code.enforcement import apply_policy
from watcher_qwen_code.integration import convert
from watcher_sdk import AsyncWatcherClient


async def run_hook(payload: dict) -> None:
    """Grade the pending native call using the transcript available before execution.

    The native agent_id identifies a subagent and is refused before reading
    history. A supplied parent_session_id is also refused. Native child-agent
    dispatch has not been exercised; the verified scope is root sessions.
    """
    if payload["hook_event_name"] != "PreToolUse" or payload.get("agent_id") or payload.get("parent_session_id"):
        raise ValueError("Unsupported native event or subagent")
    records = [json.loads(line) for line in Path(payload["transcript_path"]).read_text().splitlines() if line.strip()]
    messages = convert(records)
    call = {"id": payload["tool_call_id"], "function": payload["tool_name"], "arguments": payload["tool_input"]}
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        await apply_policy(client, payload["session_id"], messages, call, cwd=payload.get("cwd"))


def main() -> None:
    """Emit neutral permission output on allow so ordinary native checks still run.

    All bridge/SDK errors emit the same denial as a policy refusal. Native
    dispatcher crash/timeout behavior remains upstream-owned; see README.
    """
    allowed = False
    try:
        asyncio.run(run_hook(json.load(sys.stdin)))
        allowed = True
    except Exception:
        sys.stderr.write("Watcher did not confirm approval; tool withheld.\n")
    output = (
        {}
        if allowed
        else {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Watcher did not confirm approval",
            }
        }
    )
    sys.stdout.write(json.dumps(output) + "\n")


if __name__ == "__main__":
    main()
