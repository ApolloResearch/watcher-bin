"""Credential-free native model/tool fixture; main records it to a real Watcher."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from agno.agent import Agent
from agno.models.base import Model
from agno.models.response import ModelResponse
from watcher_agno.adapter import observe

from watcher_sdk import AsyncWatcherClient


class DeterministicModel(Model):
    """A native model provider with deterministic buffered function responses."""

    def invoke(self, messages, **kwargs):
        if any(message.role == "tool" for message in messages):
            return ModelResponse(role="assistant", content="4 and 6")
        return ModelResponse(
            role="assistant",
            content="",
            tool_calls=[
                {"id": "double-2", "type": "function", "function": {"name": "double", "arguments": '{"value":2}'}},
                {"id": "double-3", "type": "function", "function": {"name": "double", "arguments": '{"value":3}'}},
            ],
        )

    async def ainvoke(self, messages, **kwargs):
        return self.invoke(messages, **kwargs)

    def invoke_stream(self, *args, **kwargs):
        raise NotImplementedError("Buffered fixture")

    async def ainvoke_stream(self, *args, **kwargs):
        raise NotImplementedError("Buffered fixture")
        yield

    def _parse_provider_response(self, response, **kwargs):
        return response

    def _parse_provider_response_delta(self, response):
        return response


async def run_conversation():
    """Execute Agent.arun's native parallel tool dispatch and retrieve real messages."""

    def double(value: int) -> str:
        """Return twice the supplied integer."""
        return str(value * 2)

    agent = Agent(model=DeterministicModel(id="deterministic"), tools=[double], telemetry=False)
    result = await agent.arun("Double 2 and 3")
    return result.messages


async def main():
    """Send the deterministic native run to the configured real Watcher server."""
    messages = await run_conversation()
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        outcomes = await observe(client, str(uuid4()), messages)
        json.dump([outcome.to_dict() for outcome in outcomes], sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
