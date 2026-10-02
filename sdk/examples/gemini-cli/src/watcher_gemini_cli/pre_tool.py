"""Native pre-tool hook for the explicitly enabled ephemeral Watcher veto."""

import asyncio
import json
import os
import sys
from pathlib import Path

from watcher_gemini_cli.enforcement import apply_policy, require_opt_in
from watcher_gemini_cli.integration import convert
from watcher_sdk import AsyncWatcherClient


async def run_hook(payload: dict) -> None:
    """Grade only context available at this native callback, without recording it.

    A supplied parent_session_id is refused, but the pinned callbacks do not
    establish that marker for every child agent. Missing it is not proof of a
    root session; subagent execution remains outside the verified scope.
    """
    require_opt_in()
    if payload["hook_event_name"] != "BeforeTool" or payload.get("parent_session_id"):
        raise ValueError("Unsupported native event or subagent")
    # BeforeTool has prior native history, but no pending call ID.
    path = payload["transcript_path"]
    if not isinstance(path, str) or not path:
        raise ValueError("The native hook did not supply prior context")
    records = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    messages = convert(records)
    if not messages:
        raise ValueError("Prior native context is unavailable")
    call = {"function": payload["tool_name"], "arguments": payload["tool_input"]}
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
