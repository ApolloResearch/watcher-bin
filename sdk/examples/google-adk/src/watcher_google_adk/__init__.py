"""Observe native conversations or gate the documented Google ADK tool boundary.

Create an application-owned public AsyncWatcherClient and one Monitor per
conversation. Demos show registration, completed history and failure handling.
"""

from watcher_google_adk.adapter import IncompleteObservationError, messages_for_watcher, observe
from watcher_google_adk.monitoring import ApprovalRequired, Monitor, ToolBlocked
from watcher_google_adk.native import ConversationHistory, before_tool_callback

__all__ = [
    "IncompleteObservationError",
    "messages_for_watcher",
    "observe",
    "Monitor",
    "ToolBlocked",
    "ApprovalRequired",
    "ConversationHistory",
    "before_tool_callback",
]
