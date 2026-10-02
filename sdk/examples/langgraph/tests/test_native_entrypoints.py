"""The documented ToolNode registration gates async dispatch and rejects sync use."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from watcher_langgraph import monitored_tool_node


class RecordingMonitor:
    """Track actual callback entry and optionally refuse before native execution."""

    def __init__(self, refuse=False):
        self.calls = []
        self.refuse = refuse

    async def before(self, history, call_id, name, arguments):
        self.calls.append((history, call_id, name, arguments))
        if self.refuse:
            raise RuntimeError("Monitor refused the pending call")


def graph_for(monitor, effects):
    """Compile a graph whose synchronous tool would leave a visible native effect."""

    @tool
    def double(value: int) -> str:
        """Double an integer and record execution in the test's effect list."""
        effects.append(value)
        return str(value * 2)

    builder = StateGraph(MessagesState)  # ty: ignore[invalid-argument-type]
    builder.add_node("tools", monitored_tool_node([double], monitor))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    return builder.compile()


def pending_input():
    """Provide the actual user prompt and one native assistant tool call."""
    return {
        "messages": [
            HumanMessage(content="Double 2"),
            AIMessage(content="", tool_calls=[{"id": "double-2", "name": "double", "args": {"value": 2}}]),
        ]
    }


@pytest.mark.parametrize("method", ["invoke", "stream"])
def test_sync_graph_refuses_before_monitor_or_tool(method):
    monitor, effects = RecordingMonitor(refuse=True), []
    graph = graph_for(monitor, effects)

    with pytest.raises(RuntimeError, match=r"require graph\.ainvoke"):
        result = getattr(graph, method)(pending_input())
        if method == "stream":
            list(result)

    assert monitor.calls == []
    assert effects == []


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["ainvoke", "astream"])
@pytest.mark.parametrize("refuse", [False, True])
async def test_async_graph_waits_for_monitor_before_native_effect(method, refuse):
    monitor, effects = RecordingMonitor(refuse=refuse), []
    graph = graph_for(monitor, effects)

    async def run():
        if method == "ainvoke":
            return await graph.ainvoke(pending_input())  # ty: ignore[invalid-argument-type]
        states = [state async for state in graph.astream(pending_input(), stream_mode="values")]  # ty: ignore[invalid-argument-type]
        return states[-1]

    if refuse:
        with pytest.raises(RuntimeError, match="Monitor refused the pending call"):
            await run()
        assert effects == []
    else:
        state = await run()
        assert effects == [2]
        result = state["messages"][-1]
        assert isinstance(result, ToolMessage)
        assert result.tool_call_id == "double-2"
        assert result.content == "4"

    assert len(monitor.calls) == 1
    history, call_id, name, arguments = monitor.calls[0]
    assert history[0].content == "Double 2"
    assert history[-1].tool_calls[0]["id"] == call_id == "double-2"
    assert (name, arguments) == ("double", {"value": 2})
