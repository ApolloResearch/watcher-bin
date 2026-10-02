"""Native pre-tool hook for the explicitly enabled ephemeral Watcher veto."""

import asyncio
import json
import os
import sys

from watcher_mistral_vibe.enforcement import apply_policy, require_opt_in
from watcher_sdk import AsyncWatcherClient


async def run_hook(payload: dict) -> None:
    """Grade only context available at this native callback, without recording it.

    The pinned pre-tool contract supplies parent_session_id for a child
    agent; a nonempty value is refused. Native child-agent dispatch has not
    been exercised; the verified scope is root sessions.
    """
    require_opt_in()
    if payload["hook_event_name"] != "pre_tool" or payload.get("parent_session_id"):
        raise ValueError("Unsupported native event or subagent")
    # The first pre_tool callback precedes transcript persistence. This explicitly
    # selected variant grades the current tool only, even if an older log exists.
    messages = []
    call_id = payload["tool_call_id"]
    if not isinstance(call_id, str) or not call_id:
        raise ValueError("The native callback did not supply a tool ID")
    call = {"id": call_id, "function": payload["tool_name"], "arguments": payload["tool_input"]}
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        await apply_policy(client, payload["session_id"], messages, call)


def main() -> None:
    """Return neutral permission output only after allow; errors explicitly deny.

    Ordinary native permission checks still run. Native hook-process crash/timeout
    handling is owned by the CLI; this adapter cannot strengthen a fail-open host.
    """
    allowed = False
    try:
        asyncio.run(run_hook(json.load(sys.stdin)))
        allowed = True
    except Exception:
        sys.stderr.write("Watcher did not confirm approval; tool withheld.\n")
    sys.stdout.write(
        json.dumps({} if allowed else {"decision": "deny", "reason": "Watcher did not confirm approval"}) + "\n"
    )


if __name__ == "__main__":
    main()
