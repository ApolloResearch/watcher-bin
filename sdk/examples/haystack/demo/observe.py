"""Credential-free native model/tool fixture; main records it to a real Watcher."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from haystack import component
from haystack.components.agents import Agent
from haystack.dataclasses import ChatMessage, ToolCall
from haystack.tools import Tool
from watcher_haystack.adapter import observe

from watcher_sdk import AsyncWatcherClient


@component
class DeterministicGenerator:
    """Native pipeline component standing in for a chat provider without network."""

    @component.output_types(replies=list[ChatMessage])
    def run(self, messages: list[ChatMessage], tools=None):
        if any(message.is_from("tool") for message in messages):
            return {"replies": [ChatMessage.from_assistant("4 and 6")]}
        return {
            "replies": [
                ChatMessage.from_assistant(
                    tool_calls=[
                        ToolCall(tool_name="double", arguments={"value": 2}, id="double-2"),
                        ToolCall(tool_name="double", arguments={"value": 3}, id="double-3"),
                    ]
                )
            ]
        }


async def run_conversation():
    """Run the installed Agent through actual tool results and its model answer."""

    def double(value: int) -> str:
        return str(value * 2)

    native_tool = Tool(
        name="double",
        description="Double an integer",
        function=double,
        parameters={"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"]},
    )
    agent = Agent(
        chat_generator=DeterministicGenerator(),
        tools=[native_tool],
        max_agent_steps=3,
        tool_invoker_kwargs={"convert_result_to_json_string": False},
    )
    agent.warm_up()
    result = await agent.run_async(messages=[ChatMessage.from_user("Double 2 and 3")])
    return result["messages"]


async def main():
    """Send the deterministic native run to the configured real Watcher server."""
    messages = await run_conversation()
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        outcomes = await observe(client, str(uuid4()), messages)
        json.dump([outcome.to_dict() for outcome in outcomes], sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
