"""Reusable Strands Agents execution boundary for synchronous Watcher monitoring.

Use these adapters with one Monitor per conversation. The runnable clients in
demo/enforce.py show native registration and final transcript recording.
"""

import asyncio
from copy import deepcopy

from strands import Agent
from strands.hooks import BeforeToolCallEvent, HookProvider


def agent_history(agent):
    """Copy native history with the text system prompt Strands stores separately.

    Pass this snapshot to Monitor.record or observe to preserve the configured
    instructions alongside the conversation. Keep it out of Agent.messages:
    Strands passes the system prompt to the model separately from that list.
    Keep the prompt fixed for this conversation: each snapshot prefixes its
    current value to the entire history.
    """
    history = deepcopy(agent.messages)
    if agent.system_prompt:
        history.insert(0, {"role": "system", "content": [{"text": agent.system_prompt}]})
    return history


def require_separate_loop(loop):
    """Reject calls that would synchronously wait on their own Watcher event loop."""
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    if current_loop is loop:
        raise RuntimeError("Run the Strands Agent in a worker thread, separate from the Watcher loop")


class WatcherHook(HookProvider):
    """Register on Agent(hooks=[...]); execute that Agent in a worker thread.

    Strands 1.13 invokes callbacks synchronously, so passing async def would not
    wait. This hook blocks that worker on the separately running SDK event loop.
    Never invoke the Agent on the SDK loop's thread: that would deadlock.
    """

    def __init__(self, monitor, loop):
        self.monitor = monitor
        self.loop = loop

    def register_hooks(self, registry, **kwargs):
        """Register the native callback, accepting the framework's extra hook context."""
        registry.add_callback(BeforeToolCallEvent, self.before)

    def before(self, event):
        """Wait before native execution; failures become cancelled tool results.

        A callback on the Watcher loop cannot wait for its own SDK request.
        Cancel it directly because Strands may swallow an exception here.
        """
        try:
            require_separate_loop(self.loop)
        except RuntimeError as error:
            event.cancel_tool = str(error)
            return
        call = event.tool_use
        if event.selected_tool is None or event.selected_tool.tool_name != call["name"]:
            event.cancel_tool = "Selected tool does not match the pending call"
            return
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.monitor.before(agent_history(event.agent), call["toolUseId"], call["name"], call["input"]),
                self.loop,
            )
            future.result()
        except Exception as error:
            event.cancel_tool = f"Watcher withheld this tool call ({type(error).__name__})"


class WatcherAgent(Agent):
    """Reject synchronous, async and stream invocations on the Watcher loop.

    The synchronous guard runs before Strands creates a worker and blocks
    its caller. The stream guard also protects invoke_async, which consumes
    that stream. Other Agent options are forwarded unchanged. Run synchronous
    calls with asyncio.to_thread; async calls need a separate event loop.
    """

    def __init__(self, monitor, loop, **kwargs):
        self.watcher_loop = loop
        super().__init__(hooks=[WatcherHook(monitor, loop)], **kwargs)

    def __call__(self, *args, **kwargs):
        require_separate_loop(self.watcher_loop)
        return super().__call__(*args, **kwargs)

    async def stream_async(self, *args, **kwargs):
        """Yield native events; reject the Watcher loop before the first event."""
        require_separate_loop(self.watcher_loop)
        async for event in super().stream_async(*args, **kwargs):
            yield event
