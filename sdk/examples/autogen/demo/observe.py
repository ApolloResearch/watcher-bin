"""Credential-free native model/tool fixture; main records it to a real Watcher."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from autogen_agentchat.agents import AssistantAgent
from autogen_core import FunctionCall
from autogen_core.models import CreateResult, RequestUsage
from autogen_ext.models.replay import ReplayChatCompletionClient
from watcher_autogen.adapter import observe

from watcher_sdk import AsyncWatcherClient


def fixture_model():
    """Return the official replay client with pending calls and a final answer."""
    return ReplayChatCompletionClient(
        chat_completions=[
            CreateResult(
                finish_reason="function_calls",
                content=[
                    FunctionCall(id="double-2", name="double", arguments='{"value":2}'),
                    FunctionCall(id="double-3", name="double", arguments='{"value":3}'),
                ],
                usage=RequestUsage(prompt_tokens=0, completion_tokens=0),
                cached=False,
            ),
            "4 and 6",
        ],
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": False,
            "family": "unknown",
            "structured_output": False,
        },
    )


async def run_conversation():
    """Run AssistantAgent with the official replay model and real parallel tools."""
    model = fixture_model()

    def double(value: int) -> str:
        """Return twice the supplied integer."""
        return str(value * 2)

    agent = AssistantAgent("example", model_client=model, tools=[double], reflect_on_tool_use=True, system_message=None)
    result = await agent.run(task="Double 2 and 3")
    await model.close()
    return result.messages


async def main():
    """Send the deterministic native run to the configured real Watcher server."""
    messages = await run_conversation()
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        outcomes = await observe(client, str(uuid4()), messages)
        json.dump([outcome.to_dict() for outcome in outcomes], sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
