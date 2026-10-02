"""Pydantic AI context-aware tools that await monitoring before their body."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from watcher_pydantic_ai.adapter import messages_for_watcher
from watcher_pydantic_ai.monitoring import Monitor
from watcher_pydantic_ai.native import before_tool

from watcher_sdk import AsyncWatcherClient


async def run_conversation(monitor, effect=lambda value: str(value * 2), *, tool_values=(2, 3)):
    """Exercise Agent's native concurrent tool scheduler and full message export."""

    def respond(messages, info):
        if any(isinstance(part, ToolReturnPart) for message in messages for part in message.parts):
            return ModelResponse(parts=[TextPart("4 and 6")])
        return ModelResponse(
            parts=[
                ToolCallPart("double", {"value": value}, tool_call_id=f"double-{index}")
                for index, value in enumerate(tool_values, start=2)
            ]
        )

    agent = Agent(FunctionModel(respond))

    @agent.tool
    async def double(ctx: RunContext[None], value: int) -> str:
        """Double an integer after Watcher authorizes this specific native call."""
        await before_tool(monitor, ctx, "double")
        return effect(value)

    result = await agent.run("Double 2 and 3")
    await monitor.record(result.all_messages())
    return result.all_messages()


async def main():
    """Execute the local arithmetic tools under the configured Watcher policy."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        monitor = Monitor(client, str(uuid4()), timeout=float(os.environ.get("WATCHER_TIMEOUT", "420")))
        messages = await run_conversation(monitor)
        json.dump(messages_for_watcher(messages), sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
