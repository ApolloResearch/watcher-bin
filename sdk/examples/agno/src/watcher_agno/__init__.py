"""Observe native conversations or gate the documented Agno tool boundary.

Create an application-owned public AsyncWatcherClient and one Monitor per
conversation. Demos show registration, completed history and failure handling.
"""

from watcher_agno.adapter import IncompleteObservationError, messages_for_watcher, observe
from watcher_agno.monitoring import ApprovalRequired, Monitor, ToolBlocked
from watcher_agno.native import CaptureModelCalls, WatcherAgent, execute_tool

__all__ = [
    "IncompleteObservationError",
    "messages_for_watcher",
    "observe",
    "Monitor",
    "ToolBlocked",
    "ApprovalRequired",
    "execute_tool",
    "CaptureModelCalls",
    "WatcherAgent",
]
