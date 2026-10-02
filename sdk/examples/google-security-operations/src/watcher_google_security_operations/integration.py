"""Export Watcher decisions and session snapshots through Chronicle v1 UDM import.

Summary exports contain public classifications and references. Explicit
transcript exports include extended trajectory data. HTTP acknowledgement
does not establish hosted UDM searchability or create Google detections.
"""

import asyncio
import hashlib
import json
import math
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from watcher_google_security_operations.snapshots import SessionSnapshot, fetch_session_snapshots
from watcher_sdk import AsyncWatcherClient


class ExportError(ValueError):
    """A source inconsistency or unacknowledged import prevents a complete receipt.

    Counts describe earlier fully acknowledged batches in this invocation. The
    failing batch may also have reached Google; these counts are not a replay cursor.
    Exceptions contain no response bodies, bearer tokens or source record values.
    """

    def __init__(self, message: str, *, acknowledged_records: int = 0, acknowledged_batches: int = 0) -> None:
        self.acknowledged_records = acknowledged_records
        self.acknowledged_batches = acknowledged_batches
        super().__init__(message)


class DecisionRecord(BaseModel):
    """Content-free source fields with closed vocabularies for exportable categories."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    tool_call_id: UUID
    session_id: UUID
    occurred_at: datetime
    severity_score: int | None = Field(default=None, strict=True)
    coverage_state: Literal["bypassed", "decided", "grading_error", "not_evaluated", "unknown"] = "unknown"
    decision_category: (
        Literal["auto_denied", "cleared", "human_allowed", "human_denied", "would_denied", "would_escalated"] | None
    ) = None
    content_state: Literal["available", "scrubbed", "unknown"] = "unknown"

    @field_validator("occurred_at")
    @classmethod
    def require_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value < datetime(1970, 1, 1, tzinfo=UTC):
            raise ValueError("occurred_at must be timezone-aware and at or after the Unix epoch")
        return value.astimezone(UTC)

    def fingerprint(self) -> str:
        """Hash exported field values for reconciliation, not destination deduplication."""
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


class ExportReceipt(BaseModel):
    """Counts acknowledged by HTTP, without claims about indexing or source completeness."""

    start: datetime
    end: datetime
    records: int
    batches: int
    exported_at: datetime


async def fetch_records(
    watcher: AsyncWatcherClient,
    *,
    start: datetime,
    end: datetime,
    page_size: int = 200,
    max_pages: int = 100,
) -> list[DecisionRecord]:
    """Read a finite inclusive occurrence-time window before making destination writes.

    Fail on inconsistent totals/offsets, duplicate IDs, records outside the window,
    or exhausted page bounds. Offset pagination cannot guarantee a stable snapshot
    and is not a decision-mutation cursor. Results cover Watcher's decision path.
    """
    if start.tzinfo is None or end.tzinfo is None or start >= end or start < datetime(1970, 1, 1, tzinfo=UTC):
        raise ValueError("Supply an ordered, timezone-aware window at or after the Unix epoch")
    if not 1 <= page_size <= 1000 or max_pages < 1:
        raise ValueError("page_size must be 1–1000 and max_pages must be positive")
    records: dict[UUID, DecisionRecord] = {}
    total: int | None = None
    offset = 0
    for _ in range(max_pages):
        page = await watcher.search_tool_calls(
            start_date=start, end_date=end, limit=page_size, offset=offset, sort_by="occurred_at", sort_order="asc"
        )
        if (
            type(page.offset) is not int
            or type(page.limit) is not int
            or type(page.total) is not int
            or page.offset != offset
            or page.limit != page_size
            or page.total < 0
            or len(page.tool_calls) > page_size
        ):
            raise ExportError("Watcher returned inconsistent pagination metadata")
        if total is not None and page.total != total:
            raise ExportError("Watcher total changed during pagination; reconcile the window")
        total = page.total
        if offset + len(page.tool_calls) > total:
            raise ExportError("Watcher returned more records than its total")
        for item in page.tool_calls:
            try:
                record = DecisionRecord.model_validate(item.to_dict())
            except ValueError:
                raise ExportError("Watcher returned invalid decision fields") from None
            if not start <= record.occurred_at <= end:
                raise ExportError("Watcher returned a record outside the requested window")
            if record.tool_call_id in records:
                raise ExportError("Watcher repeated a record across pages; reconcile the window")
            records[record.tool_call_id] = record
        offset += len(page.tool_calls)
        if offset == total:
            return list(records.values())
        if not page.tool_calls:
            raise ExportError("Watcher returned an empty page before the total was exhausted")
    raise ExportError("Source exceeds max_pages; narrow the window or increase the bound")


def encode_records(records: Sequence[DecisionRecord | SessionSnapshot]) -> bytes:
    """Serialize Chronicle v1 Event resources with UDM GENERIC_EVENT metadata.

    Watcher occurrence time is the event time. No Google event ID, principal,
    target, severity or action is invented. Vendor-specific values use the UDM
    additional Struct; severity remains Watcher's own score. productLogId is the
    Watcher tool-call UUID, while the fingerprint distinguishes exported versions.
    These fields do not make imports idempotent or turn a record into a detection.
    """
    events = []
    for record in records:
        if isinstance(record, SessionSnapshot):
            events.append(
                {
                    "udm": {
                        "metadata": {
                            "eventTimestamp": record.occurred_at.isoformat().replace("+00:00", "Z"),
                            "eventType": "GENERIC_EVENT",
                            "vendorName": "Apollo Research",
                            "productName": "Watcher",
                            "productEventType": record.record_type,
                            "productLogId": record.trajectory_id or str(record.session_id),
                            "description": "Watcher exported a stored " + record.record_type + ".",
                        },
                        "additional": {
                            "watcher_session_id": str(record.session_id),
                            "watcher_record_fingerprint": record.fingerprint(),
                            "watcher_snapshot": record.payload,
                        },
                    }
                }
            )
            continue
        additional: dict[str, str | int] = {
            "watcher_tool_call_id": str(record.tool_call_id),
            "watcher_session_id": str(record.session_id),
            "watcher_record_fingerprint": record.fingerprint(),
            "watcher_coverage_state": record.coverage_state,
            "watcher_content_state": record.content_state,
        }
        if record.severity_score is not None:
            additional["watcher_severity_score"] = record.severity_score
        if record.decision_category is not None:
            additional["watcher_decision_category"] = record.decision_category
        events.append(
            {
                "udm": {
                    "metadata": {
                        "eventTimestamp": record.occurred_at.isoformat().replace("+00:00", "Z"),
                        "eventType": "GENERIC_EVENT",
                        "vendorName": "Apollo Research",
                        "productName": "Watcher",
                        "productEventType": "tool_call_decision",
                        "productLogId": str(record.tool_call_id),
                        "description": "Watcher recorded a tool-call decision.",
                    },
                    "additional": additional,
                }
            }
        )
    return json.dumps({"inlineSource": {"events": events}}, separators=(",", ":"), allow_nan=False).encode()


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    value = response.headers.get("Retry-After")
    if value is None:
        return 0.25 * 2**attempt
    try:
        delay = float(value)
    except ValueError:
        try:
            delay = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            raise ExportError("Invalid Retry-After header") from None
    if not math.isfinite(delay) or delay > 30:
        raise ExportError("Receiver requests a longer delay; reconcile before retrying later")
    return max(0.0, delay)


class GoogleSecOpsSink:
    """Import UDM batches through a regional Chronicle v1 endpoint.

    Pass a caller-owned AsyncClient and an explicit short-lived OAuth access token.
    No ambient Google credentials are discovered and tokens are not refreshed.
    Endpoint must be a regional chronicle.googleapis.com HTTPS origin, or loopback
    HTTP for tests. The parent is projects/P/locations/L/instances/I. Only explicit
    429 responses are retried; timeouts and server errors can conceal acceptance.
    The one-MiB request cap is this example's bound, not a Google quota claim.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        endpoint: str,
        parent: str,
        access_token: str,
        attempts: int = 3,
        max_request_bytes: int = 1_048_576,
    ) -> None:
        url = urlsplit(endpoint)
        is_google = url.scheme == "https" and re.fullmatch(r"[a-z0-9-]+-chronicle\.googleapis\.com", url.hostname or "")
        is_fixture = url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost", "::1")
        if (
            not (is_google or is_fixture)
            or url.path not in ("", "/")
            or url.query
            or url.fragment
            or url.username is not None
            or url.password is not None
            or (is_google and url.port not in (None, 443))
        ):
            raise ValueError("Use a regional Chronicle HTTPS origin, or loopback HTTP, without path or credentials")
        if not re.fullmatch(r"projects/[a-zA-Z0-9-]+/locations/[a-z0-9-]+/instances/[a-zA-Z0-9-]+", parent):
            raise ValueError("parent must be projects/PROJECT/locations/LOCATION/instances/INSTANCE")
        if not access_token or re.search(r"\s", access_token):
            raise ValueError("Supply a nonempty OAuth access token without whitespace")
        if not 1 <= attempts <= 5 or not 1 <= max_request_bytes <= 1_048_576:
            raise ValueError("attempts must be 1–5; max_request_bytes must be 1–1048576")
        self.client = client
        self.url = f"{endpoint.rstrip('/')}/v1/{parent}/events:import"
        self.access_token = SecretStr(access_token)
        self.attempts = attempts
        self.max_request_bytes = max_request_bytes

    async def send(self, records: Sequence[DecisionRecord | SessionSnapshot]) -> None:
        """Require an empty HTTP 200 acknowledgment for one nonempty UDM batch.

        The API documents all-or-nothing validation. Unexpected partial-result or
        error JSON fails conservatively. No raw receiver body is included in errors.
        """
        if not records:
            return
        payload = encode_records(records)
        if len(payload) > self.max_request_bytes:
            raise ExportError("UDM request exceeds this example's byte bound")
        for attempt in range(self.attempts):
            try:
                response = await self.client.post(
                    self.url,
                    content=payload,
                    headers={
                        "Authorization": f"Bearer {self.access_token.get_secret_value()}",
                        "Content-Type": "application/json",
                    },
                    follow_redirects=False,
                )
            except httpx.TransportError:
                raise ExportError(
                    "Import transport failed; acceptance is unknown, so reconcile before replay"
                ) from None
            if response.status_code == 429 and attempt + 1 < self.attempts:
                await asyncio.sleep(_retry_delay(response, attempt))
                continue
            if response.status_code != 200:
                raise ExportError(f"Chronicle import returned HTTP {response.status_code}; batch not acknowledged")
            if not response.content.strip():
                return
            if len(response.content) > 4096:
                raise ExportError("Unexpected oversized Chronicle acknowledgment")
            if response.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
                raise ExportError("Expected an empty JSON Chronicle acknowledgment")
            try:
                acknowledgment = response.json()
            except ValueError:
                raise ExportError("Malformed Chronicle acknowledgment") from None
            if acknowledgment != {}:
                raise ExportError("Unexpected nonempty Chronicle acknowledgment; reconcile before replay")
            return
        raise AssertionError("Bounded send loop must return or raise")


async def export_window(
    watcher: AsyncWatcherClient,
    sink: GoogleSecOpsSink,
    *,
    start: datetime,
    end: datetime,
    page_size: int = 200,
    max_pages: int = 100,
    batch_size: int = 100,
) -> ExportReceipt:
    """Fetch a finite window, preflight request sizes, then import bounded UDM batches.

    Inclusive windows and replay may duplicate events. Earlier batches remain
    imported if a later batch fails; ExportError carries prior acknowledgment
    counts, not an exactly-once cursor. No watermark or credentials are persisted.
    """
    if not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be 1–1000")
    records = await fetch_records(watcher, start=start, end=end, page_size=page_size, max_pages=max_pages)
    batches = [records[index : index + batch_size] for index in range(0, len(records), batch_size)]
    if any(len(encode_records(batch)) > sink.max_request_bytes for batch in batches):
        raise ExportError("A UDM batch exceeds the byte bound; reduce batch_size")
    acknowledged_records = 0
    acknowledged_batches = 0
    for batch in batches:
        try:
            await sink.send(batch)
        except ExportError as error:
            error.acknowledged_records = acknowledged_records
            error.acknowledged_batches = acknowledged_batches
            raise
        acknowledged_records += len(batch)
        acknowledged_batches += 1
    return ExportReceipt(
        start=start, end=end, records=acknowledged_records, batches=acknowledged_batches, exported_at=datetime.now(UTC)
    )


async def export_sessions(
    watcher: AsyncWatcherClient,
    sink: GoogleSecOpsSink,
    *,
    start: datetime,
    end: datetime,
    page_size: int = 200,
    max_pages: int = 100,
    batch_size: int = 100,
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
    if not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be 1–1000")
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
    batches = [records[index : index + batch_size] for index in range(0, len(records), batch_size)]
    if any(len(encode_records(batch)) > sink.max_request_bytes for batch in batches):
        raise ExportError("A UDM batch exceeds the byte bound; reduce batch_size")
    acknowledged_records = 0
    acknowledged_batches = 0
    for batch in batches:
        try:
            await sink.send(batch)
        except ExportError as error:
            error.acknowledged_records = acknowledged_records
            error.acknowledged_batches = acknowledged_batches
            raise
        acknowledged_records += len(batch)
        acknowledged_batches += 1
    return ExportReceipt(
        start=start, end=end, records=acknowledged_records, batches=acknowledged_batches, exported_at=datetime.now(UTC)
    )
