"""Fetch session summaries and optional full transcripts through the public SDK.

Session selection uses activity overlap, not a creation-time or change-feed
cursor. The default selects high/critical scores and recorded denials or observe-mode
denial/escalation judgments. Content leaves Watcher only with explicit transcript opt-in.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from watcher_sdk import AsyncWatcherClient, TrajectoryView

_SUMMARY_FIELDS = {
    "agent_platform",
    "trajectory_count",
    "message_count",
    "started_at",
    "ended_at",
    "is_content_scrubbed",
    "max_score",
    "max_gateway_score",
    "deep_review_severity",
    "deep_review_status",
    "deep_review_reviewed_at",
    "permission_decisions",
}


class SessionSnapshot(BaseModel):
    """A typed export envelope around public Watcher summary or trajectory fields.

    Summary payloads omit user identity, previews and transcript text. Transcript
    payloads carry the public extended trajectory response and can contain all
    of those things; callers must opt in before this object is constructed.
    """

    model_config = ConfigDict(frozen=True)
    session_id: UUID
    occurred_at: datetime
    record_type: Literal["session_summary", "transcript"]
    payload: dict[str, Any]
    trajectory_id: str | None = None

    @field_validator("occurred_at")
    @classmethod
    def require_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value < datetime(1970, 1, 1, tzinfo=UTC):
            raise ValueError("Snapshot time must have a UTC offset and follow the Unix epoch")
        return value.astimezone(UTC)

    def fingerprint(self) -> str:
        """Identify this field version for reconciliation; not a destination deduplication guarantee."""
        value = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(value.encode()).hexdigest()


def matches_severity(source: dict[str, Any], selected: list[str] | None) -> bool:
    """Match explicit score bands or the default selection of notable sessions.

    None includes high/critical scores and recorded human/automatic denials or
    observe-mode denial/escalation judgments, even when no score exists. An
    explicit list filters only numeric scores; an empty list includes every
    session. Decision counts never imply a numeric severity. Live-tool scores
    are considered alongside deep review because the server's filter omits them.
    """
    if selected == []:
        return True
    scores = [source[key] for key in ("max_gateway_score", "deep_review_severity") if source.get(key) is not None]
    if any(type(score) is not int or not 0 <= score <= 10 for score in scores):
        raise ValueError("Session summary contains an invalid severity score")
    if selected is None:
        counts = source.get("permission_decisions") or {}
        if any(counts.get(name, 0) > 0 for name in ("human_denied", "auto_denied", "would_denied", "would_escalated")):
            return True
        selected = ["high", "critical"]
    if not scores:
        return False
    score = max(scores)
    band = "critical" if score >= 9 else "high" if score >= 7 else "medium" if score >= 4 else "low"
    return band in selected


async def fetch_session_snapshots(
    watcher: AsyncWatcherClient,
    *,
    start: datetime,
    end: datetime,
    severities: list[str] | None = None,
    include_transcripts: bool = False,
    page_size: int = 200,
    max_pages: int = 100,
    max_trajectories: int = 100,
    max_total_bytes: int = 32 * 1024 * 1024,
) -> list[SessionSnapshot]:
    """Read a bounded activity window before any destination receives data.

    None selects high/critical scores and recorded denials or observe-mode
    denial/escalation judgments. Explicit severity lists filter scores only;
    an empty list selects all sessions. Scores use the highest live-tool or
    latest deep-review value: low < 4, medium 4–6, high 7–8, critical 9–10.
    The bounded scan includes
    all sessions in the activity window because the server severity filter omits
    live-only scores. Session activity may extend beyond the window. Summaries contain
    only an allowlist of source fields. With include_transcripts=True, every
    returned trajectory is fetched with TrajectoryView.EXTENDED, preserving the
    SDK's native fields instead of rebuilding messages or inventing notifications.
    Source totals, IDs and memory bounds are checked, but concurrent same-size
    edits and late arrivals still require reconciliation. No watermark is saved.
    """
    if start.tzinfo is None or end.tzinfo is None or start >= end or start < datetime(1970, 1, 1, tzinfo=UTC):
        raise ValueError("Supply a timezone-aware ordered window after the Unix epoch")
    if not 1 <= page_size <= 1000 or min(max_pages, max_trajectories, max_total_bytes) < 1:
        raise ValueError("Pagination, trajectory and byte limits must be positive")
    selected = severities
    if selected is not None and not set(selected) <= {"low", "medium", "high", "critical"}:
        raise ValueError("Unsupported Watcher severity bucket")
    records = []
    seen = set()
    total, offset, total_bytes = None, 0, 0
    previous = datetime(1970, 1, 1, tzinfo=UTC)

    def retain(record: SessionSnapshot) -> None:
        """Apply the memory budget as records arrive, before fetching another trajectory."""
        nonlocal total_bytes
        total_bytes += len(record.model_dump_json().encode())
        if total_bytes > max_total_bytes:
            raise ValueError("Source content exceeds the byte budget; narrow the export window")
        records.append(record)

    for _ in range(max_pages):
        page = await watcher.search_sessions(
            start_date=start,
            end_date=end,
            severities=None,
            limit=page_size,
            offset=offset,
            sort_by="started_at",
            sort_order="asc",
        )
        if (
            any(type(value) is not int for value in (page.offset, page.limit, page.total))
            or page.offset != offset
            or page.limit != page_size
            or page.total < 0
            or len(page.sessions) > page_size
            or offset + len(page.sessions) > page.total
        ):
            raise ValueError("Inconsistent session pagination")
        if total is not None and total != page.total:
            raise ValueError("Session total changed during export; reconcile the window")
        total = page.total
        for session in page.sessions:
            identifier = str(UUID(session.session_id))
            if identifier in seen:
                raise ValueError("Repeated session during pagination")
            seen.add(identifier)
            if (
                session.started_at.tzinfo is None
                or session.ended_at.tzinfo is None
                or session.started_at > end
                or session.ended_at < start
                or session.started_at < previous
                or session.started_at > session.ended_at
            ):
                raise ValueError("Session activity window or ordering is inconsistent")
            previous = session.started_at
            source = session.to_dict()
            if not matches_severity(source, selected):
                continue
            summary = {key: source[key] for key in _SUMMARY_FIELDS if key in source}
            counts = summary.get("permission_decisions")
            if counts is not None:
                summary["permission_decisions"] = {
                    name: counts[name]
                    for name in ("human_denied", "auto_denied", "human_allowed", "would_denied", "would_escalated")
                    if name in counts
                }
            retain(
                SessionSnapshot(
                    session_id=UUID(identifier),
                    occurred_at=session.ended_at,
                    record_type="session_summary",
                    payload=summary,
                )
            )
            if include_transcripts:
                listing = await watcher.list_trajectories(identifier)
                if (
                    type(listing.total) is not int
                    or listing.total != len(listing.trajectories)
                    or listing.total > max_trajectories
                ):
                    raise ValueError("Trajectory list is incomplete or exceeds the configured bound")
                trajectory_ids = set()
                for trajectory in listing.trajectories:
                    if trajectory.session_id != identifier or trajectory.trajectory_id in trajectory_ids:
                        raise ValueError("Unexpected or repeated trajectory identity")
                    trajectory_ids.add(trajectory.trajectory_id)
                    detail = await watcher.get_trajectory(
                        identifier, trajectory.trajectory_id, view=TrajectoryView.EXTENDED
                    )
                    if detail.session_id != identifier or detail.trajectory_id != trajectory.trajectory_id:
                        raise ValueError("Trajectory detail identity does not match the selected source")
                    retain(
                        SessionSnapshot(
                            session_id=UUID(identifier),
                            occurred_at=trajectory.last_timestamp,
                            record_type="transcript",
                            trajectory_id=trajectory.trajectory_id,
                            payload=detail.to_dict(),
                        )
                    )
        offset += len(page.sessions)
        if offset == total:
            return records
        if not page.sessions:
            raise ValueError("Empty session page before its total was exhausted")
    raise ValueError("Session source exceeds max_pages; narrow the export window")
