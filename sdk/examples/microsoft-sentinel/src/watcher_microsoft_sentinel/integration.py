"""Export Watcher records to an Azure Monitor custom table for Sentinel.

The caller supplies a bearer token and DCR configuration. Session exports may
include full transcripts only when explicitly enabled. This module performs no
credential discovery, provisioning or Sentinel rule creation.
"""

import json
import re
from datetime import UTC, datetime
from uuid import uuid4

import httpx

from watcher_microsoft_sentinel.snapshots import SessionSnapshot, fetch_session_snapshots
from watcher_microsoft_sentinel.source import (
    DecisionRecord,
    ExportError,
    ExportReceipt,
    checked_origin,
    fetch_records,
    wait_for_retry,
)
from watcher_sdk import AsyncWatcherClient


def encode_record(record: DecisionRecord | SessionSnapshot) -> bytes:
    """Match the table/stream schema and retain occurrence time if Azure rewrites TimeGenerated."""
    if isinstance(record, SessionSnapshot):
        event = {
            "TimeGenerated": record.occurred_at.isoformat(),
            "OccurredAt": record.occurred_at.isoformat(),
            "ToolCallId": None,
            "SessionId": str(record.session_id),
            "RecordFingerprint": record.fingerprint(),
            "SeverityScore": None,
            "CoverageState": None,
            "DecisionCategory": None,
            "ContentState": None,
            "RecordType": record.record_type,
            "TrajectoryId": record.trajectory_id,
            "Snapshot": record.payload,
        }
        return json.dumps(event, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    event = {
        "TimeGenerated": record.occurred_at.isoformat(),
        "OccurredAt": record.occurred_at.isoformat(),
        "ToolCallId": str(record.tool_call_id),
        "SessionId": str(record.session_id),
        "RecordFingerprint": record.fingerprint(),
        "SeverityScore": record.severity_score,
        "CoverageState": record.coverage_state,
        "DecisionCategory": record.decision_category,
        "ContentState": record.content_state,
        "RecordType": "tool_call_decision",
        "TrajectoryId": None,
        "Snapshot": None,
    }
    return json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode()


class LogsIngestionSink:
    """Send UTF-8 arrays through Azure Monitor Logs Ingestion API 2023-01-01.

    Use the DCR logsIngestion endpoint (or associated DCE origin), immutable
    dcr-* ID and input stream, not a workspace ID or ARM resource ID. bearer_token
    must target this Azure cloud's Monitor audience and outlive the export.
    No token acquisition occurs here. The caller owns the HTTP client.
    HTTP 429/500/502/503/504 receive bounded retries, which can duplicate rows.
    Timeouts and redirects are not retried; HTTP 204 confirms request acceptance.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        bearer_token: str,
        *,
        rule_id: str,
        stream: str = "Custom-WatcherDecisions",
        attempts: int = 3,
    ) -> None:
        origin = checked_origin(endpoint)
        if not re.fullmatch(r"dcr-[A-Za-z0-9]+", rule_id):
            raise ValueError("rule_id must be an immutable dcr-* identifier")
        if not re.fullmatch(r"Custom-[A-Za-z0-9_-]+", stream):
            raise ValueError("stream must be a Custom-* input stream name")
        if not bearer_token or any(character.isspace() for character in bearer_token):
            raise ValueError("Supply a nonempty bearer token without whitespace")
        if not 1 <= attempts <= 5:
            raise ValueError("attempts must be 1–5")
        self.client = client
        self.endpoint = f"{origin}/dataCollectionRules/{rule_id}/streams/{stream}?api-version=2023-01-01"
        self.headers = {"Authorization": f"Bearer {bearer_token}", "Content-Type": "application/json"}
        self.attempts = attempts

    async def send(self, payload: bytes) -> None:
        """Send a prepared bounded JSON-array batch and require a bodyless HTTP 204."""
        if not payload or payload == b"[]":
            return
        if len(payload) > 1_000_000:
            raise ValueError("Logs Ingestion requests must not exceed 1 MB")
        headers = {**self.headers, "x-ms-client-request-id": str(uuid4())}
        for attempt in range(self.attempts):
            response = await self.client.post(
                self.endpoint,
                content=payload,
                headers=headers,
                follow_redirects=False,
            )
            if response.status_code in (429, 500, 502, 503, 504) and attempt + 1 < self.attempts:
                await wait_for_retry(response, attempt)
                continue
            if response.status_code != 204 or response.content:
                raise ExportError(f"Logs Ingestion did not acknowledge the batch (HTTP {response.status_code})")
            return
        raise AssertionError("Bounded send loop must return or raise")


async def export_window(
    watcher: AsyncWatcherClient,
    sink: LogsIngestionSink,
    *,
    start: datetime,
    end: datetime,
    page_size: int = 200,
    max_pages: int = 100,
    batch_size: int = 100,
    max_batch_bytes: int = 900_000,
) -> ExportReceipt:
    """Validate a finite Watcher window, then send byte- and count-bounded arrays.

    Earlier batches may be accepted when a later one fails. This function creates
    neither a delivery checkpoint nor a Sentinel alert. Inclusive boundaries and
    retries can duplicate rows; reconcile source changes independently.
    """
    if batch_size < 1 or not 2 <= max_batch_bytes <= 1_000_000:
        raise ValueError("batch_size must be positive and max_batch_bytes 2–1000000")
    records = await fetch_records(watcher, start=start, end=end, page_size=page_size, max_pages=max_pages)
    rows = [encode_record(record) for record in records]
    if any(len(row) + 2 > max_batch_bytes for row in rows):
        raise ExportError("A single Azure row exceeds max_batch_bytes")
    batches: list[bytes] = []
    current: list[bytes] = []
    size = 2
    for row in rows:
        if current and (len(current) == batch_size or size + 1 + len(row) > max_batch_bytes):
            batches.append(b"[" + b",".join(current) + b"]")
            current, size = [], 2
        size += len(row) + bool(current)
        current.append(row)
    if current:
        batches.append(b"[" + b",".join(current) + b"]")
    for payload in batches:
        await sink.send(payload)
    return ExportReceipt(
        start=start, end=end, records=len(records), batches=len(batches), exported_at=datetime.now(UTC)
    )


async def export_sessions(
    watcher: AsyncWatcherClient,
    sink: LogsIngestionSink,
    *,
    start: datetime,
    end: datetime,
    page_size: int = 200,
    max_pages: int = 100,
    batch_size: int = 100,
    max_batch_bytes: int = 900000,
    severities: list[str] | None = None,
    include_transcripts: bool = False,
    max_trajectories: int = 100,
    max_total_bytes: int = 32 * 1024 * 1024,
) -> ExportReceipt:
    """Export selected session summaries and optionally their stored transcripts.

    None includes high/critical scores and recorded denials or observe-mode
    denial/escalation judgments. Explicit severity lists filter only scores;
    pass [] for all sessions. Content is read only with include_transcripts=True.
    All source identities and encoded batch
    limits are checked before transmission. This is an activity-window snapshot,
    not a notification feed; retries and concurrent changes require reconciliation.
    """
    if batch_size < 1 or not 2 <= max_batch_bytes <= 1000000:
        raise ValueError("batch_size must be positive and max_batch_bytes 2–1000000")
    records = await fetch_session_snapshots(
        watcher,
        start=start,
        end=end,
        page_size=page_size,
        max_pages=max_pages,
        severities=severities,
        include_transcripts=include_transcripts,
        max_trajectories=max_trajectories,
        max_total_bytes=max_total_bytes,
    )
    rows = [encode_record(record) for record in records]
    if any(len(row) + 2 > max_batch_bytes for row in rows):
        raise ExportError("A single Azure row exceeds max_batch_bytes")
    batches: list[bytes] = []
    current: list[bytes] = []
    size = 2
    for row in rows:
        if current and (len(current) == batch_size or size + 1 + len(row) > max_batch_bytes):
            batches.append(b"[" + b",".join(current) + b"]")
            current, size = ([], 2)
        size += len(row) + bool(current)
        current.append(row)
    if current:
        batches.append(b"[" + b",".join(current) + b"]")
    for payload in batches:
        await sink.send(payload)
    return ExportReceipt(
        start=start, end=end, records=len(records), batches=len(batches), exported_at=datetime.now(UTC)
    )
