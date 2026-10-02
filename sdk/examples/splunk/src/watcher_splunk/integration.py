"""Export Watcher decision and session records to Splunk HEC.

Decisions and summaries exclude transcript content. The separate session-export
entry point includes stored transcripts only when the caller explicitly opts in.
"""

import asyncio
import json
import math
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import httpx

from watcher_sdk import AsyncWatcherClient
from watcher_splunk.snapshots import SessionSnapshot, fetch_session_snapshots
from watcher_splunk.source import (
    DecisionRecord,
    ExportError,
    ExportReceipt,
    checked_origin,
    fetch_records,
    wait_for_retry,
)


class AcknowledgmentPending(ExportError):
    """Polling failed or remained pending; retain channel and ack_id without resending."""

    def __init__(self, channel: UUID, ack_id: int) -> None:
        self.channel = channel
        self.ack_id = ack_id
        super().__init__("HEC acknowledgment is unconfirmed; retain its identity and do not resend blindly")


def encode_event(record: DecisionRecord | SessionSnapshot, *, index: str | None = None) -> bytes:
    """Encode one HEC envelope, retaining a stable version fingerprint for deduplication."""
    event = record.model_dump(mode="json", exclude_none=True)
    event["event_type"] = (
        "watcher." + record.record_type if isinstance(record, SessionSnapshot) else "watcher.tool_call.decision"
    )
    event["record_fingerprint"] = record.fingerprint()
    envelope: dict[str, object] = {
        "time": record.occurred_at.timestamp(),
        "source": "watcher",
        "sourcetype": "watcher:" + record.record_type if isinstance(record, SessionSnapshot) else "watcher:decision",
        "event": event,
    }
    if index is not None:
        envelope["index"] = index
    return json.dumps(envelope, separators=(",", ":"), ensure_ascii=False).encode()


def _response_object(response: httpx.Response) -> dict[str, object]:
    try:
        body = response.json()
    except ValueError as error:
        raise ExportError(
            f"HEC returned malformed JSON (HTTP {response.status_code}); delivery may be ambiguous"
        ) from error
    if not isinstance(body, dict):
        raise ExportError(f"HEC returned a non-object acknowledgment (HTTP {response.status_code})")
    return body


def _acknowledgment_id(body: dict[str, object]) -> int:
    """Normalize documented HEC key/value variants without choosing a conflicting ID."""
    identifiers: list[int] = []
    for key in ("ackId", "ackID"):
        if key not in body:
            continue
        value = body[key]
        if type(value) is int and value >= 0:
            identifiers.append(value)
        elif isinstance(value, str) and value.isascii() and value.isdecimal():
            try:
                identifiers.append(int(value, 10))
            except ValueError as error:
                raise ExportError("HEC accepted the batch with an invalid acknowledgment ID") from error
        else:
            raise ExportError("HEC accepted the batch with an invalid acknowledgment ID; do not resend blindly")
    if not identifiers or len(set(identifiers)) != 1:
        raise ExportError("HEC accepted the batch without one unambiguous acknowledgment ID; do not resend blindly")
    return identifiers[0]


class HecSink:
    """Use HEC JSON events with optional Enterprise acknowledgment polling.

    endpoint is the origin, for example https://splunk.example:8088. The token
    and index must be authorized by the operator. Set acknowledgments=True only
    for a token whose Enterprise HEC acknowledgment feature is enabled. Reuse a
    channel only for the same sender. The caller owns and closes the HTTP client.
    Explicit busy or queue-at-capacity responses have bounded retries; transport failures and
    ambiguous body codes are never retried. Every retry can duplicate events.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        token: str,
        *,
        index: str | None = None,
        acknowledgments: bool = False,
        channel: UUID | None = None,
        attempts: int = 3,
        ack_polls: int = 30,
        ack_interval: float = 1.0,
    ) -> None:
        self.endpoint = checked_origin(endpoint)
        if not token or any(character.isspace() for character in token):
            raise ValueError("Supply a nonempty HEC token without whitespace")
        if index is not None and (not index or any(character in index for character in "\r\n")):
            raise ValueError("index must be nonempty and contain no newlines")
        if not 1 <= attempts <= 5 or not 1 <= ack_polls <= 300:
            raise ValueError("attempts must be 1–5 and ack_polls 1–300")
        if not math.isfinite(ack_interval) or not 0 <= ack_interval <= 30:
            raise ValueError("ack_interval must be finite and between 0 and 30 seconds")
        self.client = client
        self.index = index
        self.acknowledgments = acknowledgments
        self.channel = channel or uuid4()
        self.attempts = attempts
        self.ack_polls = ack_polls
        self.ack_interval = ack_interval
        self.headers = {"Authorization": f"Splunk {token}", "Content-Type": "application/json"}
        if acknowledgments:
            self.headers["X-Splunk-Request-Channel"] = str(self.channel)

    async def send(self, payload: bytes) -> None:
        """Send a prepared nonempty HEC batch; require body code zero and optional ack."""
        if not payload:
            return
        for attempt in range(self.attempts):
            response = await self.client.post(
                self.endpoint + "/services/collector/event",
                content=payload,
                headers=self.headers,
                follow_redirects=False,
            )
            body = _response_object(response)
            code = body.get("code")
            if type(code) is not int:
                raise ExportError(f"HEC acknowledgment lacks an integer code (HTTP {response.status_code})")
            is_busy = (response.status_code == 429 and code in (26, 27)) or (response.status_code == 503 and code == 9)
            if is_busy and attempt + 1 < self.attempts:
                await wait_for_retry(response, attempt)
                continue
            if response.status_code != 200 or code != 0:
                raise ExportError(
                    f"HEC rejected or ambiguously accepted the batch (HTTP {response.status_code}, code {code})"
                )
            if self.acknowledgments:
                ack_id = _acknowledgment_id(body)
                try:
                    await self.wait_for_ack(ack_id)
                except (ExportError, httpx.HTTPError) as error:
                    if isinstance(error, AcknowledgmentPending):
                        raise
                    raise AcknowledgmentPending(self.channel, ack_id) from error
            return
        raise AssertionError("Bounded send loop must return or raise")

    async def wait_for_ack(self, ack_id: int) -> None:
        """Resume polling this channel; true confirms replication, not searchability.

        A false value also means unknown/expired, and querying an already returned
        true acknowledgment may return false. Keep successful polling results.
        """
        if not self.acknowledgments or type(ack_id) is not int or ack_id < 0:
            raise ValueError("Acknowledgments must be enabled and ack_id a nonnegative integer")
        for poll in range(self.ack_polls):
            response = await self.client.post(
                self.endpoint + "/services/collector/ack",
                json={"acks": [ack_id]},
                headers=self.headers,
                follow_redirects=False,
            )
            if response.status_code != 200:
                raise ExportError(
                    f"HEC acknowledgment poll failed (HTTP {response.status_code}); delivery is ambiguous"
                )
            body = _response_object(response)
            acks = body.get("acks")
            acknowledged = cast(dict[str, object], acks).get(str(ack_id)) if isinstance(acks, dict) else None
            if type(acknowledged) is not bool:
                raise ExportError("HEC acknowledgment poll lacks the requested boolean status")
            if acknowledged:
                return
            if poll + 1 < self.ack_polls:
                await asyncio.sleep(self.ack_interval)
        raise AcknowledgmentPending(self.channel, ack_id)


async def export_window(
    watcher: AsyncWatcherClient,
    sink: HecSink,
    *,
    start: datetime,
    end: datetime,
    page_size: int = 200,
    max_pages: int = 100,
    batch_size: int = 100,
    max_batch_bytes: int = 900_000,
) -> ExportReceipt:
    """Fetch and validate all records, then send bounded newline-separated HEC batches.

    The byte cap is a conservative example default, not a universal Splunk limit.
    Earlier batches may be accepted if a later batch fails. No checkpoint or
    exactly-once guarantee is provided; inclusive/replayed windows can duplicate.
    """
    if batch_size < 1 or not 1 <= max_batch_bytes <= 1_000_000:
        raise ValueError("batch_size must be positive and max_batch_bytes 1–1000000")
    records = await fetch_records(watcher, start=start, end=end, page_size=page_size, max_pages=max_pages)
    events = [encode_event(record, index=sink.index) for record in records]
    if any(len(event) > max_batch_bytes for event in events):
        raise ExportError("A single HEC event exceeds max_batch_bytes")
    batches: list[bytes] = []
    current: list[bytes] = []
    size = 0
    for event in events:
        if current and (len(current) == batch_size or size + 1 + len(event) > max_batch_bytes):
            batches.append(b"\n".join(current))
            current, size = [], 0
        size += len(event) + bool(current)
        current.append(event)
    if current:
        batches.append(b"\n".join(current))
    for payload in batches:
        await sink.send(payload)
    return ExportReceipt(
        start=start, end=end, records=len(records), batches=len(batches), exported_at=datetime.now(UTC)
    )


async def export_sessions(
    watcher: AsyncWatcherClient,
    sink: HecSink,
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
    if batch_size < 1 or not 1 <= max_batch_bytes <= 1000000:
        raise ValueError("batch_size must be positive and max_batch_bytes 1–1000000")
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
    events = [encode_event(record, index=sink.index) for record in records]
    if any(len(event) > max_batch_bytes for event in events):
        raise ExportError("A single HEC event exceeds max_batch_bytes")
    batches: list[bytes] = []
    current: list[bytes] = []
    size = 0
    for event in events:
        if current and (len(current) == batch_size or size + 1 + len(event) > max_batch_bytes):
            batches.append(b"\n".join(current))
            current, size = ([], 0)
        size += len(event) + bool(current)
        current.append(event)
    if current:
        batches.append(b"\n".join(current))
    for payload in batches:
        await sink.send(payload)
    return ExportReceipt(
        start=start, end=end, records=len(records), batches=len(batches), exported_at=datetime.now(UTC)
    )
