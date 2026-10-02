"""Observe native conversations or gate the documented CrewAI tool boundary.

Create an application-owned public AsyncWatcherClient and one Monitor per
conversation. Demos show registration, completed history and failure handling.
"""

from watcher_crewai.adapter import IncompleteObservationError, ObservedLLM, WatcherTrace, messages_for_watcher, observe
from watcher_crewai.monitoring import ApprovalRequired, Monitor, ToolBlocked
from watcher_crewai.native import MonitoredTrace

__all__ = [
    "IncompleteObservationError",
    "messages_for_watcher",
    "observe",
    "WatcherTrace",
    "ObservedLLM",
    "Monitor",
    "ToolBlocked",
    "ApprovalRequired",
    "MonitoredTrace",
]
