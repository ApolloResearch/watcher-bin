"""Credential-free native model/tool fixture; main records it to a real Watcher."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.base.llms.types import ChatMessage, ChatResponse, LLMMetadata
from llama_index.core.llms.function_calling import FunctionCallingLLM
from llama_index.core.llms.llm import ToolSelection
from llama_index.core.llms.mock import MockLLM
from llama_index.core.memory import ChatMemoryBuffer
from watcher_llamaindex.adapter import observe

from watcher_sdk import AsyncWatcherClient


class DeterministicModel(MockLLM, FunctionCallingLLM):
    """Native function-calling model backed by deterministic ChatResponse objects."""

    @property
    def metadata(self):
        return LLMMetadata(is_function_calling_model=True, is_chat_model=True)

    def _prepare_chat_with_tools(
        self,
        tools,
        user_msg=None,
        chat_history=None,
        verbose=False,
        allow_parallel_tool_calls=False,
        tool_required=False,
        **kwargs,
    ):
        return {"messages": chat_history}

    def chat(self, messages, **kwargs):
        if any(message.role == "tool" for message in messages):
            return ChatResponse(message=ChatMessage(role="assistant", content="4 and 6"))
        return ChatResponse(
            message=ChatMessage(
                role="assistant",
                content="",
                additional_kwargs={
                    "tool_calls": [
                        {
                            "id": "double-2",
                            "type": "function",
                            "function": {"name": "double", "arguments": '{"value":2}'},
                        },
                        {
                            "id": "double-3",
                            "type": "function",
                            "function": {"name": "double", "arguments": '{"value":3}'},
                        },
                    ]
                },
            )
        )

    async def achat(self, messages, **kwargs):
        return self.chat(messages, **kwargs)

    def get_tool_calls_from_response(self, response, error_on_no_tool_call=True, **kwargs):
        return [
            ToolSelection(
                tool_id=call["id"],
                tool_name=call["function"]["name"],
                tool_kwargs=json.loads(call["function"]["arguments"]),
            )
            for call in response.message.additional_kwargs.get("tool_calls", [])
        ]


async def run_conversation():
    """Run FunctionAgent, including real tool execution and its memory finalization."""

    def double(value: int) -> str:
        """Return twice the supplied integer."""
        return str(value * 2)

    memory = ChatMemoryBuffer.from_defaults(token_limit=10000)
    agent = FunctionAgent(llm=DeterministicModel(max_tokens=None), tools=[double], streaming=False)
    await agent.run(user_msg="Double 2 and 3", memory=memory)
    return memory.get_all()


async def main():
    """Send the deterministic native run to the configured real Watcher server."""
    messages = await run_conversation()
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        outcomes = await observe(client, str(uuid4()), messages)
        json.dump([outcome.to_dict() for outcome in outcomes], sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
