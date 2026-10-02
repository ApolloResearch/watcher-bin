"""Reusable DSPy execution boundary for synchronous Watcher monitoring.

Use these adapters with one Monitor per conversation. The runnable clients in
demo/enforce.py show native registration and final transcript recording.
"""

from contextvars import ContextVar
from copy import deepcopy

from watcher_dspy.adapter import WatcherTrace


class PendingTrace(WatcherTrace):
    """Capture the native ID and raw arguments before DSPy's argument validation."""

    def __init__(self, prompt):
        super().__init__(prompt)
        self.pending_call: ContextVar[tuple[str, dict] | None] = ContextVar("watcher_pending_call", default=None)

    def on_tool_start(self, call_id, instance, inputs):
        super().on_tool_start(call_id, instance, inputs)
        self.pending_call.set((call_id, deepcopy(inputs["kwargs"])))
