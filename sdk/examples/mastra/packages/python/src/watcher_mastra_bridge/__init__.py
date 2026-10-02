"""Public Python bridge for recording and authorizing Mastra tool calls.

Use ``observe_snapshots`` for ordered post-run files. The Node monitoring adapter
invokes the installed ``watcher_mastra_bridge.gate`` module before native tools run.
"""

from watcher_mastra_bridge.bridge import observe_snapshots
from watcher_mastra_bridge.monitoring import Monitor, Withheld
from watcher_mastra_bridge.observation import ObservationQueue

__all__ = ["Monitor", "ObservationQueue", "Withheld", "observe_snapshots"]
