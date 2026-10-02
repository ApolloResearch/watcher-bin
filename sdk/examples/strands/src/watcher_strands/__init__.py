"""Observe native conversations or gate the documented Strands Agents tool boundary.

Create an application-owned public AsyncWatcherClient and one Monitor per
conversation. Demos show registration, completed history and failure handling.
"""

from watcher_strands.adapter import IncompleteObservationError, messages_for_watcher, observe
from watcher_strands.monitoring import ApprovalRequired, Monitor, ToolBlocked
from watcher_strands.native import WatcherAgent, WatcherHook, agent_history, require_separate_loop

__all__ = [
    "IncompleteObservationError",
    "messages_for_watcher",
    "agent_history",
    "observe",
    "Monitor",
    "ToolBlocked",
    "ApprovalRequired",
    "require_separate_loop",
    "WatcherHook",
    "WatcherAgent",
]
