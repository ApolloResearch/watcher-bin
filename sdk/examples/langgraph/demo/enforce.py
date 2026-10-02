"""Native LangGraph ToolNode middleware that waits before its execution handler."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from watcher_langgraph import Monitor, messages_for_watcher, monitored_tool_node

from watcher_sdk import AsyncWatcherClient


async def run_conversation(monitor, effect=lambda value: str(value * 2)):
    """Run a compiled graph with native parallel ToolNode dispatch and final answer."""

    @tool
    def double(value: int) -> str:
        """Double an integer."""
        return effect(value)

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
    builder.add_node("tools", monitored_tool_node([double], monitor))
    builder.add_edge(START, "assistant")
    builder.add_conditional_edges("assistant", route)
    builder.add_edge("tools", "assistant")
    state = await builder.compile().ainvoke({"messages": [HumanMessage(content="Double 2 and 3")]})  # ty: ignore[invalid-argument-type]
    await monitor.record(state["messages"])
    return state["messages"]


async def main():
    """Execute the local arithmetic tools under the configured Watcher policy."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        monitor = Monitor(client, str(uuid4()), timeout=float(os.environ.get("WATCHER_TIMEOUT", "420")))
        messages = await run_conversation(monitor)
        json.dump(messages_for_watcher(messages), sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
