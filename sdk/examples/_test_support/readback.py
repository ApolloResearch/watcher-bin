"""Verify stored conversations through the same public SDK that customers use.

Installed example drivers supply the exact native external ID and final text.
The hook's HTTP success is not a recording acknowledgement; this bounded poll
requires the matching session, final message and requested decision identities.
It retains responses on failure so missing storage cannot be mistaken for a
successful SDK submission. No SQL or private product import is used here.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from watcher_sdk import AsyncWatcherClient, TrajectoryView


def preserves_source_fields(stored: Any, supplied: Any) -> bool:
    """Require every submitted JSON field and list element, allowing API-added keys.

    Lists keep exact length and order. Scalars keep their JSON type and value,
    including explicit null, false and zero. This does not flatten content blocks
    or discard optional source fields to make a readback comparison pass.
    """
    if isinstance(supplied, dict):
        return isinstance(stored, dict) and all(
            key in stored and preserves_source_fields(stored[key], value) for key, value in supplied.items()
        )
    if isinstance(supplied, list):
        return (
            isinstance(stored, list)
            and len(stored) == len(supplied)
            and all(preserves_source_fields(saved, source) for saved, source in zip(stored, supplied, strict=True))
        )
    if isinstance(supplied, str):
        return isinstance(stored, str) and stored == supplied
    if isinstance(supplied, bool) or supplied is None:
        return type(stored) is type(supplied) and stored == supplied
    if isinstance(supplied, int):
        return isinstance(stored, int) and not isinstance(stored, bool) and stored == supplied
    if isinstance(supplied, float):
        return isinstance(stored, float) and stored == supplied
    return False


async def wait_for_conversation(
    client: AsyncWatcherClient,
    *,
    external_ids: dict[str, list[str]],
    final_text: str | None,
    decision_ids: set[str],
    evidence: Path,
    expected_messages: list[dict[str, Any]] | None = None,
    timeout: float = 15,
) -> dict[str, Any]:
    """Return one exact stored session's extended trajectory, or fail by deadline.

    External ID filters must identify one native conversation. Ambiguous matches
    fail immediately. An empty decision set supports paused/transcript-only runs;
    it does not claim they produced tool judgments. A null final_text omits the
    final-answer check, allowing aborted native histories. When expected_messages
    is supplied, wait for every source field in the complete ordered history,
    including the final transcript-only delivery. Callers separately compare
    tool judgments and actual native effects with the retained records.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        result = await client.search_sessions(external_ids=external_ids)
        sessions = result.to_dict()
        (evidence / "sessions.json").write_text(json.dumps(sessions, indent=2))
        if sessions["total"] > 1 or len(sessions["sessions"]) > 1:
            raise AssertionError("The native identity matched multiple Watcher sessions")
        # Count and visible rows can differ while the accepted ingest finishes.
        # The actual row, not its count, establishes readiness for readback.
        if sessions["sessions"]:
            item = sessions["sessions"][0]
            if item["latest_trajectory_id"] is not None:
                response = await client.get_trajectory(
                    item["session_id"], item["latest_trajectory_id"], view=TrajectoryView.EXTENDED
                )
                stored = response.to_dict()
                (evidence / "trajectory.json").write_text(json.dumps(stored, indent=2))
                has_final = any(
                    message.get("role") == "assistant" and message.get("content") == final_text
                    for message in stored["messages"]
                )
                has_messages = expected_messages is None or preserves_source_fields(
                    stored["messages"], expected_messages
                )
                if (
                    (has_final or final_text is None)
                    and has_messages
                    and decision_ids <= stored["tool_call_decisions"].keys()
                ):
                    return stored
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(
                "The exact final transcript and tool decisions did not become readable through the SDK"
            )
        await asyncio.sleep(0.05)
