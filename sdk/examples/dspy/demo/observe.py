"""Credential-free native model/tool fixture; main records it to a real Watcher."""

import asyncio
import json
import os
import sys
from uuid import uuid4

import dspy
from dspy.utils.dummies import DummyLM
from watcher_dspy.adapter import WatcherTrace, observe

from watcher_sdk import AsyncWatcherClient


async def run_conversation():
    """Execute native ReAct, DummyLM and Tool callbacks including finish."""
    model = DummyLM(
        [
            {"next_thought": "Double two", "next_tool_name": "double", "next_tool_args": json.dumps({"value": 2})},
            {"next_thought": "Double three", "next_tool_name": "double", "next_tool_args": json.dumps({"value": 3})},
            {"next_thought": "Done", "next_tool_name": "finish", "next_tool_args": "{}"},
            {"reasoning": "The results are four and six", "answer": "4 and 6"},
        ]
    )

    def double(value: int) -> str:
        """Return twice the supplied integer."""
        return str(value * 2)

    trace = WatcherTrace("Double 2 and 3")
    with dspy.context(lm=model, callbacks=[trace]):
        result = await dspy.ReAct(dspy.make_signature("question -> answer"), tools=[double]).acall(
            question="Double 2 and 3"
        )
    trace.finish(result.answer)
    return trace.messages


async def main():
    """Send the deterministic native run to the configured real Watcher server."""
    messages = await run_conversation()
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        outcomes = await observe(client, str(uuid4()), messages)
        json.dump([outcome.to_dict() for outcome in outcomes], sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
