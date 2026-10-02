"""Synchronous Watcher enforcement at Aider's injected InputOutput write boundary.

Use EnforcedIO with ObservedModel/Capture from observation.py and a sequential,
nonstreaming whole-file Coder. Other write paths and shell commands are outside
this boundary; it is application-owned IO, not a native universal tool hook.
"""

import asyncio
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from aider.io import InputOutput

from watcher_aider.enforcement import apply_policy
from watcher_aider.observation import Capture, archive_messages
from watcher_sdk import AsyncWatcherClient


class EnforcedIO(InputOutput):
    """Withhold write_text until Watcher records a full-grade allow for that operation.

    client_factory must return a fresh AsyncWatcherClient for each synchronous
    invocation; configure its organization for enforce mode. All exceptions stop
    the write. Call from a synchronous Coder thread, never a running event loop.
    Capture remains compatible with send_capture for independent final observation.
    """

    def __init__(self, capture: Capture, session_id: str, client_factory: Callable[[], AsyncWatcherClient], **kwargs):
        super().__init__(**kwargs)
        self.capture = capture
        self.session_id = session_id
        self.client_factory = client_factory

    def write_text(self, filename, content, max_retries=5, initial_delay=0.1):
        """Judge one actual IO invocation; rejected and failed writes retain a receipt."""
        if self.dry_run:
            self.capture.skipped_dry_runs += 1
            return super().write_text(filename, content, max_retries, initial_delay)
        exchange = self.capture.active
        if exchange is None:
            raise PermissionError("No captured model context for this write")
        messages = archive_messages(self.capture)
        operation = {
            "id": str(uuid4()),
            "arguments": {"path": str(Path(filename).resolve()), "content": content},
            "status": "running",
        }
        call = {"id": operation["id"], "function": "aider_write_file", "arguments": operation["arguments"]}
        exchange["writes"].append(operation)

        async def approve():
            async with self.client_factory() as client:
                await apply_policy(client, self.session_id, messages, call)

        try:
            asyncio.run(approve())
        except Exception:
            operation.update(status="withheld", error="Watcher did not confirm approval; write was withheld")
            raise
        try:
            result = super().write_text(filename, content, max_retries, initial_delay)
        except (OSError, UnicodeError) as error:
            operation.update(status="error", error=type(error).__name__)
            raise
        operation["status"] = "completed"
        return result
