"""Observe native conversations or gate the documented Pydantic AI tool boundary.

Create an application-owned public AsyncWatcherClient and one Monitor per
conversation. Demos show registration, completed history and failure handling.
"""

from watcher_pydantic_ai.adapter import IncompleteObservationError, messages_for_watcher, observe
from watcher_pydantic_ai.monitoring import ApprovalRequired, Monitor, ToolBlocked
from watcher_pydantic_ai.native import before_tool

__all__ = [
    "IncompleteObservationError",
    "messages_for_watcher",
    "observe",
    "Monitor",
    "ToolBlocked",
    "ApprovalRequired",
    "before_tool",
]
