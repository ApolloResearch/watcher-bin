"""Observe native conversations or gate the documented Semantic Kernel tool boundary.

Create an application-owned public AsyncWatcherClient and one Monitor per
conversation. Demos show registration, completed history and failure handling.
"""

from watcher_semantic_kernel.adapter import IncompleteObservationError, messages_for_watcher, observe
from watcher_semantic_kernel.monitoring import ApprovalRequired, Monitor, ToolBlocked
from watcher_semantic_kernel.native import WatcherFilter

__all__ = [
    "IncompleteObservationError",
    "messages_for_watcher",
    "observe",
    "Monitor",
    "ToolBlocked",
    "ApprovalRequired",
    "WatcherFilter",
]
