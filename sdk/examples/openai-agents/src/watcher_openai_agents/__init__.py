"""Observe native conversations or gate the documented OpenAI Agents tool boundary.

Create an application-owned public AsyncWatcherClient and one Monitor per
conversation. Demos show registration, completed history and failure handling.
"""

from watcher_openai_agents.adapter import IncompleteObservationError, messages_for_watcher, observe
from watcher_openai_agents.monitoring import ApprovalRequired, Monitor, ToolBlocked
from watcher_openai_agents.native import WatcherHooks, execute_tool

__all__ = [
    "IncompleteObservationError",
    "messages_for_watcher",
    "observe",
    "Monitor",
    "ToolBlocked",
    "ApprovalRequired",
    "execute_tool",
    "WatcherHooks",
]
