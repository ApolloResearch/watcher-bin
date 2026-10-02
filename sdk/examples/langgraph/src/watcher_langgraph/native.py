"""Gate LangGraph ToolNode callbacks through the public Watcher monitor.

Use ``monitored_tool_node(tools, monitor)`` in a graph run with ``ainvoke`` or
``astream``. It installs both native callbacks: async dispatch waits for Watcher,
and synchronous dispatch raises before executing a tool. Only calls handled by
that ToolNode are gated; unrelated side effects remain outside this integration.
"""

from langgraph.prebuilt import ToolNode


def monitored_tool_node(tools, monitor):
    """Build a ToolNode that gates async calls and refuses synchronous execution.

    Register the returned node in place of ToolNode. The async handler runs only
    after the monitor permits the call; ``invoke`` and ``stream`` raise without
    calling the monitor or tool. Errors propagate out of the graph. Do not replace
    either callback: LangGraph dispatches sync and async calls independently.
    """

    def before_sync(request, execute):
        raise RuntimeError("Watcher-monitored tools require graph.ainvoke() or graph.astream()")

    async def before_async(request, execute):
        call = request.tool_call
        await monitor.before(request.state["messages"], call["id"], call["name"], call["args"])
        return await execute(request)

    return ToolNode(tools, wrap_tool_call=before_sync, awrap_tool_call=before_async, handle_tool_errors=False)
