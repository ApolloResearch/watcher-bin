"""Public Python SDK sidecar for awaited native Vercel AI tool execution."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from watcher_sdk import AsyncWatcherClient
from watcher_vercel_ai_bridge.adapter import messages_for_watcher
from watcher_vercel_ai_bridge.monitoring import Monitor, same_json_arguments


async def run_conversation(monitor, effect=lambda value: str(value * 2)):
    """Run native generateText; authorize pending calls and dispatch Python tools.

    The Node tool.execute awaits the sidecar decision before requesting its
    application-owned Python tool body. Process death, invalid JSON, or a denied
    decision cannot request that body. Pending calls are graded serially, so N
    calls can consume N grading timeouts. Stderr is inherited to avoid an unread
    subprocess pipe blocking Node. No direct Watcher HTTP occurs in Node.
    """
    process = await asyncio.create_subprocess_exec(
        os.environ.get("WATCHER_VERCEL_SYNC", "watcher-vercel-ai-sync"),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=None,
    )
    allowed = {}
    history = None
    try:
        if process.stdout is None or process.stdin is None:
            raise RuntimeError("The native sidecar requires stdin and stdout pipes")
        while line := await process.stdout.readline():
            event = json.loads(line)
            reply = {"id": event["id"], "ok": False}
            if event["type"] == "authorize":
                try:
                    await monitor.before(event["messages"], event["toolCallId"], event["toolName"], event["input"])
                except Exception as error:
                    reply["error"] = type(error).__name__
                else:
                    allowed[event["toolCallId"]] = event["input"]
                    reply["ok"] = True
            elif event["type"] == "execute":
                expected = allowed.pop(event["toolCallId"], None)
                if expected is not None and same_json_arguments(expected, event["input"]):
                    reply.update(ok=True, result=effect(**expected))
            elif event["type"] == "complete":
                history = event["messages"]
                break
            else:
                raise ValueError("Unexpected sidecar request")
            process.stdin.write((json.dumps(reply) + "\n").encode())
            await process.stdin.drain()
        process.stdin.close()
        await process.wait()
        if process.returncode or history is None:
            raise RuntimeError("Vercel tool sidecar did not complete")
        await monitor.record(history)
        return history
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def main():
    """Execute the local arithmetic tools under the configured Watcher policy."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        monitor = Monitor(client, str(uuid4()), timeout=float(os.environ.get("WATCHER_TIMEOUT", "420")))
        messages = await run_conversation(monitor)
        json.dump(messages_for_watcher(messages), sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
