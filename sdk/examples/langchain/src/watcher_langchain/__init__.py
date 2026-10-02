"""Observe native conversations or gate the documented LangChain tool boundary.

Create an application-owned public AsyncWatcherClient and one Monitor per
conversation. Demos show registration, completed history and failure handling.
"""

from watcher_langchain.adapter import IncompleteObservationError, messages_for_watcher, observe
from watcher_langchain.monitoring import ApprovalRequired, Monitor, ToolBlocked
from watcher_langchain.native import WatcherMiddleware

__all__ = [
    "IncompleteObservationError",
    "messages_for_watcher",
    "observe",
    "Monitor",
    "ToolBlocked",
    "ApprovalRequired",
    "WatcherMiddleware",
]
