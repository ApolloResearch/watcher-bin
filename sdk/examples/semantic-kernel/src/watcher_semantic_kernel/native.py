"""Gate Semantic Kernel's native automatic function invocation with Watcher."""

import json
from collections.abc import Awaitable, Callable

from semantic_kernel.filters import AutoFunctionInvocationContext

from watcher_semantic_kernel.monitoring import ToolBlocked


class WatcherFilter:
    """Register with kernel.add_filter(FilterTypes.AUTO_FUNCTION_INVOCATION, filter).

    One filter uses one conversation's Monitor. The native context retains exact
    model call identity and full history; the continuation executes only after
    Watcher permits it. Direct application calls to kernel.invoke bypass this
    automatic-invocation filter and need their own boundary. Other filters must
    not rewrite authorized tool arguments after this one runs.
    """

    def __init__(self, monitor):
        self.monitor = monitor

    async def __call__(
        self,
        context: AutoFunctionInvocationContext,
        next: Callable[[AutoFunctionInvocationContext], Awaitable[None]],
    ):
        """Await policy before the native invocation continuation is reached."""
        call = context.function_call_content
        if call is None or context.chat_history is None:
            raise ToolBlocked("Automatic invocation requires pending call identity and history")
        arguments = json.loads(call.arguments) if isinstance(call.arguments, str) else call.arguments
        if not isinstance(arguments, dict):
            raise ToolBlocked("Pending function arguments must be a JSON object")
        await self.monitor.before(context.chat_history.messages, call.call_id or call.id, call.name, arguments)
        await next(context)
