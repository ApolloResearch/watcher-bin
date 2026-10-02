"""A credential-free native LangChain agent run with completed-history observation."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from watcher_langchain.adapter import observe

from watcher_sdk import AsyncWatcherClient


class FixtureModel(FakeMessagesListChatModel):
    """Replay fixed tool requests while retaining create_agent's native tool loop."""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self


def fixture_model():
    """Return two fixture completions, with actual tool execution between them."""
    return FixtureModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "double", "args": {"value": 2}, "id": "double-2"},
                    {"name": "double", "args": {"value": 3}, "id": "double-3"},
                ],
            ),
            AIMessage(content="4 and 6"),
        ]
    )


async def run_conversation():
    """Let the installed agent call real tools and return its final state."""

    @tool
    def double(value: int) -> str:
        """Double an integer."""
        return str(value * 2)

    agent = create_agent(fixture_model(), tools=[double])
    result = await agent.ainvoke({"messages": [HumanMessage(content="Double 2 and 3")]})
    return result["messages"]


async def main():
    """Observe the complete native history through the public Watcher SDK."""
    messages = await run_conversation()
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        outcomes = await observe(client, str(uuid4()), messages)
        json.dump([outcome.to_dict() for outcome in outcomes], sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
