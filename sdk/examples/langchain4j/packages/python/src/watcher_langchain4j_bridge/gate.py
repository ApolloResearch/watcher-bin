"""Read an Inspect transcript on stdin and authorize one native call via the public SDK.

Exit zero means an applied allow or valid deferred decision for the requested ID.
Exit three means human approval is required; other nonzero exits are failures. With no call ID, record the completed transcript without grading.
The native application must wait for this process before invoking its tool.
Native callers must insert -- before supplied IDs so option-shaped IDs stay data.
"""

import asyncio
import json
import os
import sys
from typing import Annotated

import typer

from watcher_langchain4j_bridge.monitoring import ApprovalRequired, Monitor, Withheld
from watcher_sdk import AsyncWatcherClient

app = typer.Typer(invoke_without_command=True, add_completion=False, pretty_exceptions_enable=False)


async def main(tool_id: str | None = None, human_decision: str | None = None) -> None:
    """Use explicit Watcher configuration and a caller-owned conversation identity."""
    if human_decision not in (None, "allow", "deny") or human_decision is not None and tool_id is None:
        raise ValueError("A human choice needs one native tool ID")
    messages = json.load(sys.stdin)
    async with AsyncWatcherClient(
        os.environ["WATCHER_BASE_URL"], api_key=os.environ["WATCHER_API_KEY"], max_retries=0
    ) as watcher:
        monitor = Monitor(
            watcher, os.environ["WATCHER_SESSION_ID"], timeout=float(os.environ.get("WATCHER_TIMEOUT", "420"))
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
        if human_decision is None:
            await monitor.authorize(messages, inputs)
        else:
            pending = inputs[0]
            await monitor.report_human_decision(
                tool_id, pending["tool_name"], pending["tool_input"], approved=human_decision == "allow"
            )


@app.command()
def cli(
    tool_id: Annotated[str | None, typer.Argument(help="Native tool ID; omit to record the transcript.")] = None,
    human_decision: Annotated[
        str | None, typer.Option(help="Report an explicit human choice for a pending escalation.")
    ] = None,
) -> None:
    """Authorize one tool ID or record stdin; prefix supplied IDs with -- in native callers."""
    try:
        asyncio.run(main(tool_id, human_decision))
    except ApprovalRequired:
        raise typer.Exit(3) from None
    except Exception as error:
        sys.stderr.write(type(error).__name__ + "\n")
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
