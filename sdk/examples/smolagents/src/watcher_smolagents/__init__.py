"""Observe native conversations or gate the documented smolagents tool boundary.

Create an application-owned public AsyncWatcherClient and one Monitor per
conversation. Demos show registration, completed history and failure handling.
"""

from watcher_smolagents.adapter import IncompleteObservationError, messages_for_watcher, observe
from watcher_smolagents.monitoring import ApprovalRequired, Monitor, ToolBlocked
from watcher_smolagents.native import CapturedModel, consume

__all__ = [
    "IncompleteObservationError",
    "messages_for_watcher",
    "observe",
    "Monitor",
    "ToolBlocked",
    "ApprovalRequired",
    "CapturedModel",
    "consume",
]
