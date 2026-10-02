"""Export Watcher decisions and session snapshots as standard OTLP logs.

Decision and summary exports omit transcript content. Explicit transcript
exports retain public extended trajectory fields. The caller chooses the
receiver and owns downstream alerting; these snapshots are not a change feed.
"""

import asyncio
import hashlib
import json
import math
from collections.abc import Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest, ExportLogsServiceResponse
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, InstrumentationScope, KeyValue
from opentelemetry.proto.logs.v1.logs_pb2 import LogRecord, ResourceLogs, ScopeLogs
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from pydantic import BaseModel, ConfigDict, Field, field_validator

from watcher_opentelemetry.snapshots import SessionSnapshot, fetch_session_snapshots
from watcher_sdk import AsyncWatcherClient


class ExportError(ValueError):
    """Source consistency or sink acknowledgment prevents a complete export claim."""


class PartialExportError(ExportError):
    """The receiver reported partial acceptance or a warning; the batch is not retried."""

    def __init__(self, rejected_records: int) -> None:
        self.rejected_records = rejected_records
        super().__init__(
            f"OTLP receiver reported partial success ({rejected_records} rejected records); do not retry blindly"
        )


class DecisionRecord(BaseModel):
    """An allowlist of public decision fields; user and transcript content are excluded."""

    model_config = ConfigDict(extra="ignore")

    tool_call_id: UUID
    session_id: UUID
    occurred_at: datetime
    severity_score: int | None = Field(default=None, strict=True)
    coverage_state: str = "unknown"
    decision_category: str | None = None
    content_state: str = "unknown"

    @field_validator("occurred_at")
    @classmethod
    def require_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value < datetime(1970, 1, 1, tzinfo=UTC):
            raise ValueError("occurred_at must include a UTC offset and be at or after the Unix epoch")
        return value.astimezone(UTC)

    def fingerprint(self) -> str:
        """Identify the exported field version, not an immutable Watcher change event."""
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


class ExportReceipt(BaseModel):
    """Counts of HTTP-acknowledged logs; not proof of indexing or source completeness."""

    start: datetime
    end: datetime
    records: int
    batches: int
    exported_at: datetime


def _window(start: datetime, end: datetime) -> None:
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("Supply timezone-aware start and end with start before end")
    if start < datetime(1970, 1, 1, tzinfo=UTC):
        raise ValueError("The export window must start at or after the Unix epoch")


async def fetch_records(
    watcher: AsyncWatcherClient,
    *,
    start: datetime,
    end: datetime,
    page_size: int = 200,
    max_pages: int = 100,
) -> list[DecisionRecord]:
    """Fetch a finite inclusive occurrence-time window before exporting any logs.

    Pagination uses the SDK's stable occurrence-time ordering and offset pages.
    Changed totals, conflicting duplicate records, invalid windows and excessive
    pages fail before sending. These checks cannot provide snapshot isolation:
    late-arriving records and later decisions still require reconciliation.
    Only calls that entered Watcher's decision path appear in these results.
    """
    _window(start, end)
    if not 1 <= page_size <= 1000 or max_pages < 1:
        raise ValueError("page_size must be 1–1000 and max_pages must be positive")
    records: dict[UUID, DecisionRecord] = {}
    total: int | None = None
    offset = 0
    for _ in range(max_pages):
        page = await watcher.search_tool_calls(
            start_date=start,
            end_date=end,
            limit=page_size,
            offset=offset,
            sort_by="occurred_at",
            sort_order="asc",
        )
        if any(type(value) is not int for value in (page.offset, page.limit, page.total)):
            raise ExportError("Watcher pagination counts must be integers")
        if page.offset != offset or page.limit != page_size or page.total < 0 or len(page.tool_calls) > page_size:
            raise ExportError("Watcher returned inconsistent pagination metadata")
        if total is not None and page.total != total:
            raise ExportError("Source total changed during pagination; reconcile the window")
        total = page.total
        if offset + len(page.tool_calls) > total:
            raise ExportError("Watcher returned more records than its total")
        for item in page.tool_calls:
            record = DecisionRecord.model_validate(item.to_dict())
            if not start <= record.occurred_at <= end:
                raise ExportError("Watcher returned a record outside the requested time window")
            if record.tool_call_id in records:
                raise ExportError("Source repeated a record across pages; reconcile the window")
            records[record.tool_call_id] = record
        offset += len(page.tool_calls)
        if offset == total:
            return list(records.values())
        if not page.tool_calls:
            raise ExportError("Empty page before the source total was exhausted")
    raise ExportError("Source exceeds max_pages; narrow the window or increase the bound")


def _nanoseconds(value: datetime) -> int:
    delta = value.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return ((delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds) * 1000


def _attribute(key: str, value: str | int) -> KeyValue:
    return KeyValue(
        key=key, value=AnyValue(int_value=value) if isinstance(value, int) else AnyValue(string_value=value)
    )


def encode_records(records: Sequence[DecisionRecord | SessionSnapshot], *, observed_at: datetime) -> bytes:
    """Encode official OTLP log messages with content-free bodies and stable references.

    Watcher severity remains a custom numeric attribute; it is not mapped to an
    unrelated log severity scale. No trace/span IDs are fabricated. Per-record
    IDs stay log attributes so Loki does not turn them into high-cardinality
    resource labels. The content fingerprint supports downstream deduplication
    but does not make OTLP delivery idempotent.
    """
    if observed_at.tzinfo is None or observed_at < datetime(1970, 1, 1, tzinfo=UTC):
        raise ValueError("observed_at must include a UTC offset and follow the Unix epoch")
    logs: list[LogRecord] = []
    for record in records:
        if isinstance(record, SessionSnapshot):
            attributes = [
                _attribute("watcher.session_id", str(record.session_id)),
                _attribute("watcher.record_type", record.record_type),
                _attribute("watcher.record_fingerprint", record.fingerprint()),
            ]
            if record.trajectory_id is not None:
                attributes.append(_attribute("watcher.trajectory_id", record.trajectory_id))
            logs.append(
                LogRecord(
                    time_unix_nano=_nanoseconds(record.occurred_at),
                    observed_time_unix_nano=_nanoseconds(observed_at),
                    event_name="watcher." + record.record_type,
                    body=AnyValue(string_value=json.dumps(record.payload, separators=(",", ":"), allow_nan=False)),
                    attributes=attributes,
                )
            )
            continue
        attributes = [
            _attribute("watcher.tool_call_id", str(record.tool_call_id)),
            _attribute("watcher.session_id", str(record.session_id)),
            _attribute("watcher.record_fingerprint", record.fingerprint()),
            _attribute("watcher.coverage_state", record.coverage_state),
            _attribute("watcher.content_state", record.content_state),
        ]
        if record.decision_category is not None:
            attributes.append(_attribute("watcher.decision_category", record.decision_category))
        if record.severity_score is not None:
            attributes.append(_attribute("watcher.severity_score", record.severity_score))
        logs.append(
            LogRecord(
                time_unix_nano=_nanoseconds(record.occurred_at),
                observed_time_unix_nano=_nanoseconds(observed_at),
                event_name="watcher.tool_call.decision",
                body=AnyValue(string_value="Watcher recorded a tool-call decision."),
                attributes=attributes,
            )
        )
    request = ExportLogsServiceRequest(
        resource_logs=[
            ResourceLogs(
                resource=Resource(attributes=[_attribute("service.name", "watcher-decisions")]),
                scope_logs=[
                    ScopeLogs(scope=InstrumentationScope(name="watcher-opentelemetry-example"), log_records=logs)
                ],
            )
        ]
    )
    return request.SerializeToString()


def _delay(response: httpx.Response, attempt: int) -> float:
    """Use the receiver's delay without violating this example's finite retry budget."""
    value = response.headers.get("Retry-After")
    if value is None:
        return 0.25 * 2**attempt
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError) as error:
            raise ExportError("Invalid Retry-After header") from error
    if not math.isfinite(seconds) or seconds > 30:
        raise ExportError("Receiver asks for a longer retry delay; retry the window later")
    return max(0.0, seconds)


class OtlpLogSink:
    """Send checked HTTP/protobuf batches to a caller-selected OTLP logs endpoint.

    Supply the full logs URL, such as http://127.0.0.1:4318/v1/logs. Remote
    endpoints require HTTPS. Configure vendor authentication on the caller-owned
    AsyncClient, which is never closed here. HTTP 429/502/503/504 are retried up
    to attempts; transport timeouts, redirects and partial success are not.
    A timeout can mean accepted-but-unacknowledged delivery: replay can duplicate.
    Requests exceeding max_request_bytes fail before transmission. The default
    leaves room below common 1 MB limits; a destination can impose tighter limits.
    """

    def __init__(
        self, client: httpx.AsyncClient, endpoint: str, *, attempts: int = 3, max_request_bytes: int = 900_000
    ) -> None:
        url = urlsplit(endpoint)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or (url.scheme == "http" and url.hostname not in ("127.0.0.1", "localhost", "::1"))
        ):
            raise ValueError("Use an HTTPS OTLP logs URL, or loopback HTTP, without user info, query or fragment")
        if not 1 <= attempts <= 5:
            raise ValueError("attempts must be between 1 and 5")
        if max_request_bytes < 1:
            raise ValueError("max_request_bytes must be positive")
        self.max_request_bytes = max_request_bytes
        self.client = client
        self.endpoint = endpoint
        self.attempts = attempts

    def check(self, records: Sequence[DecisionRecord | SessionSnapshot], *, observed_at: datetime) -> None:
        """Reject an oversized encoded batch without sending; useful before a multi-batch export."""
        if len(encode_records(records, observed_at=observed_at)) > self.max_request_bytes:
            raise ExportError("OTLP request exceeds max_request_bytes; reduce the batch size")

    async def send(self, records: Sequence[DecisionRecord | SessionSnapshot], *, observed_at: datetime) -> None:
        """Require a valid complete OTLP acknowledgment; never send empty batches."""
        if not records:
            return
        payload = encode_records(records, observed_at=observed_at)
        if len(payload) > self.max_request_bytes:
            raise ExportError("OTLP request exceeds max_request_bytes; reduce the batch size")
        for attempt in range(self.attempts):
            response = await self.client.post(
                self.endpoint,
                content=payload,
                headers={"Content-Type": "application/x-protobuf"},
                follow_redirects=False,
            )
            if response.status_code in (429, 502, 503, 504) and attempt + 1 < self.attempts:
                await asyncio.sleep(_delay(response, attempt))
                continue
            response.raise_for_status()
            if response.status_code != 200:
                raise ExportError("Expected HTTP 200 for the OTLP acknowledgment")
            if response.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/x-protobuf":
                raise ExportError("Expected an OTLP protobuf acknowledgment")
            result = ExportLogsServiceResponse()
            try:
                result.ParseFromString(response.content)
            except DecodeError as error:
                raise ExportError("Malformed OTLP acknowledgment") from error
            if result.HasField("partial_success"):
                partial = result.partial_success
                if partial.rejected_log_records < 0 or partial.rejected_log_records > len(records):
                    raise ExportError("Invalid OTLP rejected-record count")
                if partial.rejected_log_records or partial.error_message:
                    raise PartialExportError(partial.rejected_log_records)
            return
        raise AssertionError("Bounded export loop must return or raise")


async def export_window(
    watcher: AsyncWatcherClient,
    sink: OtlpLogSink,
    *,
    start: datetime,
    end: datetime,
    page_size: int = 200,
    max_pages: int = 100,
    batch_size: int = 100,
) -> ExportReceipt:
    """Fetch one finite source window, then acknowledge every OTLP batch.

    Boundaries are inclusive, matching the Watcher API. Adjacent/replayed windows
    can duplicate records; no watermark is persisted. All encoded batch sizes are
    checked before any transmission. Earlier batches can still be accepted if a
    later network request fails. Periodic re-export is needed for late arrivals
    or changed decisions, but cannot by itself prove a complete immutable audit
    feed. This function does not query vendor indexing or create alerts.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    records = await fetch_records(watcher, start=start, end=end, page_size=page_size, max_pages=max_pages)
    observed_at = datetime.now(UTC)
    # Validate every batch before the first request so local size errors cannot cause a partial export.
    for start_index in range(0, len(records), batch_size):
        sink.check(records[start_index : start_index + batch_size], observed_at=observed_at)
    batches = 0
    for start_index in range(0, len(records), batch_size):
        await sink.send(records[start_index : start_index + batch_size], observed_at=observed_at)
        batches += 1
    return ExportReceipt(start=start, end=end, records=len(records), batches=batches, exported_at=observed_at)


async def export_sessions(
    watcher: AsyncWatcherClient,
    sink: OtlpLogSink,
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
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
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
    observed_at = datetime.now(UTC)
    for start_index in range(0, len(records), batch_size):
        sink.check(records[start_index : start_index + batch_size], observed_at=observed_at)
    batches = 0
    for start_index in range(0, len(records), batch_size):
        await sink.send(records[start_index : start_index + batch_size], observed_at=observed_at)
        batches += 1
    return ExportReceipt(start=start, end=end, records=len(records), batches=batches, exported_at=observed_at)
