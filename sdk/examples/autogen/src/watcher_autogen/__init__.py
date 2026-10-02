"""Observe native conversations or gate the documented AutoGen tool boundary.

Create an application-owned public AsyncWatcherClient and one Monitor per
conversation. Demos show registration, completed history and failure handling.
"""

from watcher_autogen.adapter import IncompleteObservationError, messages_for_watcher, observe
from watcher_autogen.monitoring import ApprovalRequired, Monitor, ToolBlocked
from watcher_autogen.native import run_monitored

__all__ = [
    "IncompleteObservationError",
    "messages_for_watcher",
    "observe",
    "Monitor",
    "ToolBlocked",
    "ApprovalRequired",
    "run_monitored",
]
