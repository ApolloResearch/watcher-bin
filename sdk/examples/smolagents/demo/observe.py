"""Credential-free native model/tool fixture; main records it to a real Watcher."""

import asyncio
import json
import os
import sys
from collections.abc import Iterator
from uuid import uuid4

from smolagents import Model, ToolCallingAgent, tool
from smolagents.memory import TaskStep
from smolagents.models import ChatMessage, ChatMessageToolCall, ChatMessageToolCallFunction, MessageRole
from watcher_smolagents.adapter import observe

from watcher_sdk import AsyncWatcherClient


class DeterministicModel(Model):
    """Native model implementation; real ToolCallingAgent dispatches the tools."""

    def __init__(self):
        super().__init__()
        self.turn = 0

    def generate(self, messages, **kwargs):
        self.turn += 1
        if self.turn == 1:
            calls = [
                ChatMessageToolCall(
                    id="double-2",
                    type="function",
                    function=ChatMessageToolCallFunction(name="double", arguments={"value": 2}),
                ),
                ChatMessageToolCall(
                    id="double-3",
                    type="function",
                    function=ChatMessageToolCallFunction(name="double", arguments={"value": 3}),
                ),
            ]
        else:
            calls = [
                ChatMessageToolCall(
                    id="final",
                    type="function",
                    function=ChatMessageToolCallFunction(name="final_answer", arguments={"answer": "4 and 6"}),
                )
            ]
        content = "I will double both numbers." if self.turn == 1 else "I have both results."
        return ChatMessage(role=MessageRole.ASSISTANT, content=content, tool_calls=calls)


async def run_conversation():
    """Retain native stream events, which preserve IDs for parallel tool results."""

    @tool
    def double(value: int) -> str:
        """Return twice an integer.

        Args:
            value: Integer to double.
        """
        return str(value * 2)

    agent = ToolCallingAgent(tools=[double], model=DeterministicModel(), verbosity_level=0)
    events = agent.run("Double 2 and 3", stream=True)
    if not isinstance(events, Iterator):
        raise TypeError("Expected the native event iterator for stream=True")
    return [TaskStep(task="Double 2 and 3"), *events]


async def main():
    """Send the deterministic native run to the configured real Watcher server."""
    messages = await run_conversation()
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        outcomes = await observe(client, str(uuid4()), messages)
        json.dump([outcome.to_dict() for outcome in outcomes], sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
