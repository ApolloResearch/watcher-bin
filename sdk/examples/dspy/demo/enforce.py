"""DSPy registered tool wrapper; callbacks capture context but do not enforce."""

import asyncio
import json
import os
import sys
from uuid import uuid4

import dspy
from dspy.utils.dummies import DummyLM
from watcher_dspy.adapter import messages_for_watcher
from watcher_dspy.monitoring import Monitor, ToolBlocked, same_json_arguments
from watcher_dspy.native import PendingTrace

from watcher_sdk import AsyncWatcherClient


async def run_conversation(monitor, effect=lambda value: str(value * 2), *, tool_values=(2, 3)):
    """Run native ReAct; only the registered side-effecting tool is synchronously gated.

    DSPy catches callback exceptions, so enforcement lives in the tool callable.
    Its internal finish pseudo-tool is retained in history but has no side effect.
    """
    trace = PendingTrace("Double 2 and 3")

    async def double(value: int) -> str:
        """Double an integer after checking DSPy's current call ID and arguments."""
        pending = trace.pending_call.get()
        if pending is None:
            raise ToolBlocked("No native tool callback captured the pending call")
        call_id, arguments = pending
        if not same_json_arguments(arguments, {"value": value}):
            raise ToolBlocked("Validated tool arguments differ from the captured request")
        await monitor.before(trace.messages, call_id, "double", arguments)
        return effect(value)

    model = DummyLM(
        [
            *[
                {
                    "next_thought": "Double the value",
                    "next_tool_name": "double",
                    "next_tool_args": json.dumps({"value": value}),
                }
                for value in tool_values
            ],
            {"next_thought": "Done", "next_tool_name": "finish", "next_tool_args": "{}"},
            {"reasoning": "The results are four and six", "answer": "4 and 6"},
        ]
    )
    with dspy.context(lm=model, callbacks=[trace]):
        result = await dspy.ReAct(dspy.make_signature("question -> answer"), tools=[double]).acall(
            question="Double 2 and 3"
        )
    trace.finish(result.answer)
    await monitor.record(trace.messages)
    return trace.messages


async def main():
    """Execute the local arithmetic tools under the configured Watcher policy."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        monitor = Monitor(client, str(uuid4()), timeout=float(os.environ.get("WATCHER_TIMEOUT", "420")))
        messages = await run_conversation(monitor)
        json.dump(messages_for_watcher(messages), sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
