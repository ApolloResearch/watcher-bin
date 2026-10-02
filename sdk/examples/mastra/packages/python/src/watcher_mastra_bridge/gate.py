"""Read an Inspect transcript on stdin and authorize one native call via the public SDK.

Exit zero permits ordinary native dispatch under the applied Watcher policy.
Every refusal or invalid result exits nonzero. With no call ID, record the completed transcript without grading.
The native application must wait for this process before invoking its tool.
Native callers must insert -- before supplied IDs so option-shaped IDs stay data.
"""

import asyncio
import json
import os
import sys
from typing import Annotated

import typer

from watcher_mastra_bridge.monitoring import Monitor, Withheld
from watcher_sdk import AsyncWatcherClient

app = typer.Typer(invoke_without_command=True, add_completion=False, pretty_exceptions_enable=False)


async def request_approval(*, tool_use_id, tool_name, tool_input, outcome) -> bool:
    """Ask the parent Node application for one explicit human choice over local pipes.

    The parent must obtain the choice from an authorized person. EOF, malformed
    replies, another call's ID, and non-boolean answers fail before execution.
    The Monitor subsequently records and reads back the human choice in Watcher.
    """
    sys.stdout.write(
        json.dumps(
            {
                "type": "approval",
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "outcome": outcome.to_dict(),
            }
        )
        + "\n"
    )
    sys.stdout.flush()
    line = await asyncio.to_thread(sys.stdin.readline)
    reply = json.loads(line)
    if (
        not isinstance(reply, dict)
        or reply.get("tool_use_id") != tool_use_id
        or type(reply.get("approved")) is not bool
    ):
        raise Withheld("The parent did not return an explicit choice for this call")
    return reply["approved"]


async def main(tool_id: str | None = None, *, human_approval: bool = False) -> None:
    """Use explicit Watcher configuration and a caller-owned conversation identity."""
    messages = json.loads(sys.stdin.readline()) if human_approval else json.load(sys.stdin)
    async with AsyncWatcherClient(
        os.environ["WATCHER_BASE_URL"], api_key=os.environ["WATCHER_API_KEY"], max_retries=0
    ) as watcher:
        monitor = Monitor(
            watcher,
            os.environ["WATCHER_SESSION_ID"],
            timeout=float(os.environ.get("WATCHER_TIMEOUT", "420")),
            approval_callback=request_approval if human_approval else None,
        )
        if tool_id is None:
            await monitor.record(messages)
            return
        inputs = [
            {"tool_use_id": call["id"], "tool_name": call["function"], "tool_input": call["arguments"]}
            for message in messages
            for call in message.get("tool_calls", [])
            if call["id"] == tool_id
        ]
        if len(inputs) != 1:
            await monitor.record(messages)
            raise Withheld("Native tool ID must identify one transcript call")
        await monitor.authorize(messages, inputs)


@app.command()
def cli(
    tool_id: Annotated[str | None, typer.Argument(help="Native tool ID; omit to record the transcript.")] = None,
    human_approval: Annotated[
        bool,
        typer.Option("--human-approval", help="Request a human choice from the parent process when Watcher escalates."),
    ] = False,
) -> None:
    """Authorize one tool ID or record stdin; prefix supplied IDs with -- in native callers."""
    try:
        asyncio.run(main(tool_id, human_approval=human_approval))
    except Exception as error:
        sys.stderr.write(type(error).__name__ + "\n")
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
