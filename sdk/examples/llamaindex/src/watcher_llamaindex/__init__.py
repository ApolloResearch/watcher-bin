"""Observe native conversations or gate the documented LlamaIndex tool boundary.

Create an application-owned public AsyncWatcherClient and one Monitor per
conversation. Demos show registration, completed history and failure handling.
"""

from watcher_llamaindex.adapter import IncompleteObservationError, messages_for_watcher, observe
from watcher_llamaindex.monitoring import ApprovalRequired, Monitor, ToolBlocked
from watcher_llamaindex.native import MonitoredFunctionAgent

__all__ = [
    "IncompleteObservationError",
    "messages_for_watcher",
    "observe",
    "Monitor",
    "ToolBlocked",
    "ApprovalRequired",
    "MonitoredFunctionAgent",
]
