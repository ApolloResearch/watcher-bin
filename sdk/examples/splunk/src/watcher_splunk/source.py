"""Fetch bounded decision windows using only the public Watcher SDK.

Records exclude transcript content and personal identity. Offset pagination is
not a change feed: reconcile late arrivals and changed decisions separately.
"""

import asyncio
import hashlib
import json
import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from watcher_sdk import AsyncWatcherClient


class ExportError(ValueError):
    """The window or destination response cannot support a successful export claim."""


class DecisionRecord(BaseModel):
    """Only identifiers, time and bounded classification fields leave Watcher."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    tool_call_id: UUID
    session_id: UUID
    occurred_at: datetime
    severity_score: int | None = Field(default=None, strict=True)
    coverage_state: Literal["decided", "bypassed", "grading_error", "not_evaluated"]
    decision_category: (
        Literal["auto_denied", "cleared", "human_allowed", "human_denied", "would_denied", "would_escalated"] | None
    ) = None
    content_state: Literal["available", "scrubbed"]

    @field_validator("occurred_at")
    @classmethod
    def require_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value < datetime(1970, 1, 1, tzinfo=UTC):
            raise ValueError("occurred_at needs a UTC offset and must follow the Unix epoch")
        return value.astimezone(UTC)

    def fingerprint(self) -> str:
        """Stable identifier of this exported field version; not an idempotency key."""
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


class ExportReceipt(BaseModel):
    """Counts acknowledged by the ingestion protocol, not proof of searchable rows."""

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
    """Read an inclusive finite time window before any destination writes.

    Refuse changed totals, repeated IDs, invalid rows and time-order regressions.
    Same-size concurrent edits can escape these checks: this is not a snapshot.
    Only calls present in Watcher's decision search appear here.
    """
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("Use timezone-aware start < end")
    if start < datetime(1970, 1, 1, tzinfo=UTC):
        raise ValueError("The window must follow the Unix epoch")
    if not 1 <= page_size <= 1000 or max_pages < 1:
        raise ValueError("page_size must be 1–1000 and max_pages positive")
    records: dict[UUID, DecisionRecord] = {}
    total: int | None = None
    offset = 0
    previous = start
    for _ in range(max_pages):
        page = await watcher.search_tool_calls(
            start_date=start,
            end_date=end,
            limit=page_size,
            offset=offset,
            sort_by="occurred_at",
            sort_order="asc",
        )
        if (
            any(type(value) is not int for value in (page.offset, page.limit, page.total))
            or page.offset != offset
            or page.limit != page_size
            or page.total < 0
            or len(page.tool_calls) > page_size
        ):
            raise ExportError("Watcher returned inconsistent pagination metadata")
        if total is not None and total != page.total:
            raise ExportError("Source total changed; reconcile the window")
        total = page.total
        if offset + len(page.tool_calls) > total:
            raise ExportError("Source page exceeds its advertised total")
        for item in page.tool_calls:
            record = DecisionRecord.model_validate(item.to_dict())
            if not start <= record.occurred_at <= end or record.occurred_at < previous:
                raise ExportError("Source time ordering or window is inconsistent")
            if record.tool_call_id in records:
                raise ExportError("Source repeated a record; reconcile the window")
            records[record.tool_call_id] = record
            previous = record.occurred_at
        offset += len(page.tool_calls)
        if offset == total:
            return list(records.values())
        if not page.tool_calls:
            raise ExportError("Source ended before its total was exhausted")
    raise ExportError("Source exceeds max_pages; narrow the window or raise the bound")


def checked_origin(endpoint: str) -> str:
    """Accept HTTPS origins or explicit loopback HTTP; credentials never enter URLs."""
    url = urlsplit(endpoint)
    if (
        url.scheme not in ("http", "https")
        or not url.hostname
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or url.path not in ("", "/")
        or (url.scheme == "http" and url.hostname not in ("127.0.0.1", "localhost", "::1"))
    ):
        raise ValueError("Use an HTTPS origin or loopback HTTP without paths, user info, query or fragment")
    return endpoint.rstrip("/")


async def wait_for_retry(response: httpx.Response, attempt: int) -> None:
    """Honor Retry-After within a finite 30-second per-retry budget."""
    value = response.headers.get("Retry-After")
    seconds = 0.25 * 2**attempt
    if value is not None:
        try:
            seconds = float(value)
        except ValueError:
            try:
                seconds = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
            except (TypeError, ValueError) as error:
                raise ExportError("Invalid Retry-After header") from error
    if not math.isfinite(seconds) or seconds > 30:
        raise ExportError("Receiver asks for a longer retry; reconcile and retry later")
    await asyncio.sleep(max(0.0, seconds))
