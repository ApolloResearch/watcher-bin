"""Reusable Pydantic AI execution boundary for synchronous Watcher monitoring.

Use these adapters with one Monitor per conversation. The runnable clients in
demo/enforce.py show native registration and final transcript recording.
"""

from pydantic_ai.messages import ToolCallPart

from watcher_pydantic_ai.monitoring import ToolBlocked


async def before_tool(monitor, ctx, name):
    """Grade the raw pending model call before a registered tool's body.

    Pydantic validates and may coerce arguments before invoking this wrapper.
    Read the original arguments by native ID so Watcher sees the model's call;
    the tool body still receives Pydantic's normally validated values.
    """
    calls = [
        part
        for message in ctx.messages
        for part in message.parts
        if isinstance(part, ToolCallPart) and part.tool_call_id == ctx.tool_call_id
    ]
    if len(calls) != 1:
        raise ToolBlocked("Expected exactly one pending native tool call")
    await monitor.before(ctx.messages, ctx.tool_call_id, name, calls[0].args_as_dict())
