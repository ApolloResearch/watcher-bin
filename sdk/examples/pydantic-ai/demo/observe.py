"""Credential-free native model/tool fixture; main records it to a real Watcher."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from watcher_pydantic_ai.adapter import observe

from watcher_sdk import AsyncWatcherClient


async def run_conversation():
    """Run the native Agent scheduler with two tools and a deterministic FunctionModel."""

    def respond(messages, info):
        if any(isinstance(part, ToolReturnPart) for message in messages for part in message.parts):
            return ModelResponse(parts=[TextPart("4 and 6")])
        return ModelResponse(
            parts=[
                ToolCallPart("double", {"value": 2}, tool_call_id="double-2"),
                ToolCallPart("double", {"value": 3}, tool_call_id="double-3"),
            ]
        )

    agent = Agent(FunctionModel(respond))

    @agent.tool_plain
    def double(value: int) -> str:
        """Return twice the supplied integer."""
        return str(value * 2)

    result = await agent.run("Double 2 and 3")
    return result.all_messages()


async def main():
    """Send the deterministic native run to the configured real Watcher server."""
    messages = await run_conversation()
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        outcomes = await observe(client, str(uuid4()), messages)
        json.dump([outcome.to_dict() for outcome in outcomes], sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
