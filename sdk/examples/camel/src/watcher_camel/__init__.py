"""Observe native conversations or gate the documented CAMEL tool boundary.

Create an application-owned public AsyncWatcherClient and one Monitor per
conversation. Demos show registration, completed history and failure handling.
"""

from watcher_camel.adapter import IncompleteObservationError, messages_for_watcher, observe
from watcher_camel.monitoring import ApprovalRequired, Monitor, ToolBlocked
from watcher_camel.native import MonitoredModel

__all__ = [
    "IncompleteObservationError",
    "messages_for_watcher",
    "observe",
    "Monitor",
    "ToolBlocked",
    "ApprovalRequired",
    "MonitoredModel",
]
