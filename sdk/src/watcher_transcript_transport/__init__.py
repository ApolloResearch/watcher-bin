"""Dependency-free transcript transport shared by Watcher ingestion clients.

The package stays compatible with Python 3.10 and avoids importing the heavier
``watcher_sdk`` package on hook startup. It exposes deterministic planning and
Claude transcript semantics while each runtime owns persistence, HTTP,
deadlines, and logging. Codex and Copilot boundaries live in ``codex`` and
``copilot``, imported directly rather than from here, so the remote collector's
copy of this package can omit those modules.
"""

from watcher_transcript_transport import claude, upload

__all__ = ["claude", "upload"]
