"""Credential-free native model/tool fixture; main records it to a real Watcher."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from camel.agents import ChatAgent
from camel.models.stub_model import StubModel
from camel.types import ModelType
from openai.types.chat import ChatCompletion
from watcher_camel.adapter import observe

from watcher_sdk import AsyncWatcherClient


class DeterministicModel(StubModel):
    """Extend CAMEL's official StubModel through its native provider interface."""

    def _run(self, messages, response_format=None, tools=None):
        if any(message["role"] == "tool" for message in messages):
            message = {"role": "assistant", "content": "4 and 6"}
        else:
            message = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "double-2", "type": "function", "function": {"name": "double", "arguments": '{"value":2}'}},
                    {"id": "double-3", "type": "function", "function": {"name": "double", "arguments": '{"value":3}'}},
                ],
            }
        return ChatCompletion.model_validate(
            {
                "id": "fixture",
                "model": "stub",
                "object": "chat.completion",
                "created": 0,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls" if "tool_calls" in message else "stop",
                        "message": message,
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        )

    async def _arun(self, messages, response_format=None, tools=None):
        return self._run(messages, response_format, tools)


async def run_conversation():
    """Run CAMEL's tool loop and read its native retained memory after completion."""

    def double(value: int) -> str:
        """Return twice the supplied integer.

        Args:
            value: Integer to double.
        """
        return str(value * 2)

    agent = ChatAgent(
        model=DeterministicModel(ModelType.STUB), tools=[double], max_iteration=3, prune_tool_calls_from_memory=False
    )
    await agent.astep("Double 2 and 3")
    messages, token_count = agent.memory.get_context()
    return messages


async def main():
    """Send the deterministic native run to the configured real Watcher server."""
    messages = await run_conversation()
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        outcomes = await observe(client, str(uuid4()), messages)
        json.dump([outcome.to_dict() for outcome in outcomes], sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
