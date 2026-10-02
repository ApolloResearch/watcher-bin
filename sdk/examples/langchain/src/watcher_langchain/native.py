"""LangChain agent middleware that awaits Watcher before native tool invocation."""

from langchain.agents.middleware import AgentMiddleware


class WatcherMiddleware(AgentMiddleware):
    """Register in create_agent(..., middleware=[...]) for async agent execution.

    One instance owns one conversation's Monitor. LangChain supplies the pending
    call and full current message state; only an accepted Watcher result permits
    the native handler to run. Earlier tools are not rolled back on later refusal.
    This middleware covers ainvoke/astream, not synchronous invoke/stream.
    """

    def __init__(self, monitor):
        self.monitor = monitor

    async def awrap_tool_call(self, request, handler):
        """Hold the native tool handler while policy or human approval is pending."""
        call = request.tool_call
        await self.monitor.before(request.state["messages"], call["id"], call["name"], call["args"])
        return await handler(request)

    def wrap_tool_call(self, request, handler):
        """Reject sync runners rather than allowing an unmonitored tool invocation."""
        raise RuntimeError("WatcherMiddleware requires agent.ainvoke or agent.astream")
