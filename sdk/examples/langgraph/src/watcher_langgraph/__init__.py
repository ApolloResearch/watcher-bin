"""Observe completed LangGraph histories or gate native ToolNode execution.

Use ``observe`` after a completed turn, or register
``monitored_tool_node(tools, Monitor(...))`` before running an async graph.
The monitored node refuses synchronous dispatch. Both paths require an
application-owned public ``AsyncWatcherClient`` and conversation ID.
"""

from watcher_langgraph.adapter import (
    IncompleteObservationError,
    messages_for_watcher,
    observe,
)
from watcher_langgraph.monitoring import ApprovalRequired, Monitor, ToolBlocked
from watcher_langgraph.native import monitored_tool_node

__all__ = [
    "IncompleteObservationError",
    "Monitor",
    "ToolBlocked",
    "ApprovalRequired",
    "messages_for_watcher",
    "observe",
    "monitored_tool_node",
]
