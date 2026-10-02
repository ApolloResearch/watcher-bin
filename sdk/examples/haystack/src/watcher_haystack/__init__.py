"""Observe native conversations or gate the documented Haystack tool boundary.

Create an application-owned public AsyncWatcherClient and one Monitor per
conversation. Demos show registration, completed history and failure handling.
"""

from watcher_haystack.adapter import IncompleteObservationError, messages_for_watcher, observe
from watcher_haystack.monitoring import ApprovalRequired, Monitor, ToolBlocked
from watcher_haystack.native import MonitoredGenerator

__all__ = [
    "IncompleteObservationError",
    "messages_for_watcher",
    "observe",
    "Monitor",
    "ToolBlocked",
    "ApprovalRequired",
    "MonitoredGenerator",
]
