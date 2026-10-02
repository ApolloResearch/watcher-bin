"""Run a compiled LangGraph with parallel native tools and record its final state."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from watcher_langgraph import observe

from watcher_sdk import AsyncWatcherClient


@tool
def double(value: int) -> str:
    """Return twice the supplied integer."""
    return str(value * 2)


async def run_conversation():
    """Execute graph scheduling, message reduction, parallel tools and final answer."""
    model = FakeMessagesListChatModel(
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

    async def assistant(state: MessagesState):
        return {"messages": [await model.ainvoke(state["messages"])]}

    def route(state: MessagesState):
        latest = state["messages"][-1]
        assert isinstance(latest, AIMessage)
        return "tools" if latest.tool_calls else END

    # The pinned library accepts this TypedDict; its StateLike bound is not recognized by ty.
    builder = StateGraph(MessagesState)  # ty: ignore[invalid-argument-type]
    builder.add_node("assistant", assistant)
    builder.add_node("tools", ToolNode([double]))
    builder.add_edge(START, "assistant")
    builder.add_conditional_edges("assistant", route)
    builder.add_edge("tools", "assistant")
    state = await builder.compile().ainvoke({"messages": [HumanMessage(content="Double 2 and 3")]})  # ty: ignore[invalid-argument-type]
    return state["messages"]


async def main():
    messages = await run_conversation()
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        outcomes = await observe(client, str(uuid4()), messages)
        json.dump([outcome.to_dict() for outcome in outcomes], sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
