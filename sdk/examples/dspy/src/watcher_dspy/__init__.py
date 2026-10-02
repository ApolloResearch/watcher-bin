"""Observe native conversations or gate the documented DSPy tool boundary.

Create an application-owned public AsyncWatcherClient and one Monitor per
conversation. Demos show registration, completed history and failure handling.
"""

from watcher_dspy.adapter import IncompleteObservationError, WatcherTrace, messages_for_watcher, observe
from watcher_dspy.monitoring import ApprovalRequired, Monitor, ToolBlocked
from watcher_dspy.native import PendingTrace

__all__ = [
    "IncompleteObservationError",
    "messages_for_watcher",
    "observe",
    "WatcherTrace",
    "Monitor",
    "ToolBlocked",
    "ApprovalRequired",
    "PendingTrace",
]
