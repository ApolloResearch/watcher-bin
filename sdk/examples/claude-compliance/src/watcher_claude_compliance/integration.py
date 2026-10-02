"""Import retained Claude Enterprise conversations through the public Watcher SDK.

Compliance transcript retrieval is retrospective. These functions record text and
tool history; they do not request tool judgments or prevent actions. The caller
owns both HTTP clients and the destination's retention/access policy.
"""

import asyncio
import hashlib
import json
import math
import os
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from watcher_sdk import AsyncWatcherClient

Family = Literal["chats", "local", "remote"]
JsonObject = dict[str, JsonValue]
_PATHS = {"chats": "apps/chats", "local": "apps/sessions/local", "remote": "apps/sessions/remote"}


class ComplianceError(ValueError):
    """The source response cannot be imported faithfully within this example's scope."""


class Conversation(BaseModel):
    """A complete page walk, preserving source order and capture limitations."""

    family: Family
    organization_id: str
    conversation_id: str
    messages: list[JsonObject]
    limitations: list[str]

    @property
    def external_id(self) -> str:
        """A collision-resistant namespace independent of native Claude Code IDs."""
        components = [self.family, self.organization_id, self.conversation_id]
        return "claude-compliance:" + ":".join(quote(value, safe="") for value in components)


class ImportReceipt(BaseModel):
    """A submitted transcript request; inspect Watcher to confirm stored content.

    The hook schedules persistence after its response. This receipt records the
    source digest and submission time, without asserting durable storage or
    exactly-once delivery. A receipt never suppresses a later import attempt.
    """

    schema_version: Literal[2] = 2
    status: Literal["submitted"] = "submitted"
    external_id: str
    source_digest: str
    submitted_at: datetime
    message_count: int
    limitations: list[str]


class _Message(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    role: Literal["user", "assistant"]
    content: list[JsonObject]
    created_at: datetime


def _object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        raise ComplianceError("Expected a JSON object in the Compliance response")
    return value


def _identifier(value: JsonValue) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ComplianceError("Missing source identity; no identity is fabricated")
    return value


def _no_duplicate_keys(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
    """Reject ambiguous JSON before it becomes tool arguments or source identity."""
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise ComplianceError("Duplicate JSON keys are not supported")
        result[key] = value
    return result


def _reject_constant(value: str) -> JsonValue:
    raise ComplianceError("Nonfinite JSON numbers are not supported")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ComplianceError("Nonfinite JSON numbers are not supported")
    return number


def _json(text: str) -> JsonValue:
    try:
        return json.loads(
            text, object_pairs_hook=_no_duplicate_keys, parse_constant=_reject_constant, parse_float=_finite_float
        )
    except (json.JSONDecodeError, RecursionError) as error:
        raise ComplianceError("Malformed JSON in the Compliance response") from error


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    """Honor bounded Retry-After values; never retry earlier than a long server delay."""
    value = response.headers.get("Retry-After")
    if value is None:
        return 1.0 * 2**attempt
    try:
        delay = float(value)
    except ValueError:
        try:
            delay = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError) as error:
            raise ComplianceError("Invalid Retry-After response") from error
    if not math.isfinite(delay) or delay > 30:
        raise ComplianceError("Retry-After exceeds this run's budget; retry the import later")
    return max(0.0, delay)


class ComplianceClient:
    """Read documented transcript endpoints with finite pagination and retries.

    Supply an authenticated AsyncClient whose base URL is the Anthropic origin
    and whose headers contain x-api-key and anthropic-version. The client is
    never closed here. GET retries are bounded; redirects are never followed.
    Source response errors leave the caller's import receipt unchanged.
    """

    def __init__(self, client: httpx.AsyncClient, *, max_pages: int = 1000, attempts: int = 3) -> None:
        if max_pages < 1 or not 1 <= attempts <= 5:
            raise ValueError("max_pages must be positive and attempts must be between 1 and 5")
        self.client = client
        self.max_pages = max_pages
        self.attempts = attempts

    async def _get(self, path: str, params: Mapping[str, str | int]) -> JsonObject:
        """Fetch one page without logging source content or following credential redirects."""
        for attempt in range(self.attempts):
            try:
                response = await self.client.get(path, params=params, follow_redirects=False)
            except httpx.TransportError:
                if attempt + 1 == self.attempts:
                    raise
                await asyncio.sleep(1.0 * 2**attempt)
                continue
            is_retryable = (
                response.status_code in (429, 500, 502, 503, 504, 529)
                and response.headers.get("x-should-retry") != "false"
            )
            if is_retryable and attempt + 1 < self.attempts:
                await asyncio.sleep(_retry_delay(response, attempt))
                continue
            response.raise_for_status()
            return _object(_json(response.text))
        raise AssertionError("Bounded request loop must return or raise")

    async def fetch(self, family: Family, conversation_id: str) -> Conversation:
        """Read every transcript page before constructing an ingestible conversation.

        Use a chat ID for chats, or a session ID for local/remote. Deleted chats
        are refused before recording. Unknown fields are tolerated.
        Conflicting duplicate messages, changed organization
        identity, repeated cursors and excessive pages fail before Watcher is
        called. An expired cursor also fails; restart the whole fetch, since a
        resumed partial transcript could cross the source's retention boundary.
        """
        if family not in _PATHS:
            raise ValueError("family must be chats, local or remote")
        _identifier(conversation_id)
        path = f"/v1/compliance/{_PATHS[family]}/{quote(conversation_id, safe='')}/messages"
        suffix = "chars" if family == "chats" else "bytes"
        params: dict[str, str | int] = {
            "order": "asc",
            "limit": 1000,
            f"tool_use_input_max_{suffix}": -1,
            f"tool_result_max_{suffix}": -1,
        }
        seen_cursors: set[str] = set()
        seen_messages: dict[str, JsonObject] = {}
        source_messages: list[JsonObject] = []
        organization_id: str | None = None
        limitations: set[str] = set()
        for _ in range(self.max_pages):
            page = await self._get(path, params)
            envelope = page if family == "chats" else _object(page["session"])
            if family == "chats" and envelope.get("deleted_at") is not None:
                raise ComplianceError("The source chat was deleted; its unavailable content is not imported")
            if envelope["id"] != conversation_id:
                raise ComplianceError("Response conversation identity changed")
            current_org = _identifier(envelope["organization_uuid"])
            if organization_id is not None and organization_id != current_org:
                raise ComplianceError("Response organization identity changed")
            organization_id = current_org
            if envelope.get("truncated") is True:
                limitations.add("The source reports a truncated session; later messages are unavailable.")
            raw_messages = page["chat_messages" if family == "chats" else "data"]
            if not isinstance(raw_messages, list):
                raise ComplianceError("Expected a transcript message array")
            for value in raw_messages:
                raw = _object(value)
                identity = _identifier(raw["id"])
                if identity in seen_messages:
                    if _canonical(raw) != _canonical(seen_messages[identity]):
                        raise ComplianceError("A source message changed during pagination; restart the fetch")
                    continue
                seen_messages[identity] = raw
                source_messages.append(raw)
            if family == "chats":
                has_more = page["has_more"]
                if not isinstance(has_more, bool):
                    raise ComplianceError("Invalid chat continuation flag")
                cursor = _identifier(page["last_id"]) if has_more else None
                cursor_key = "after_id"
            else:
                cursor = page["next_page"]
                if cursor is not None:
                    cursor = _identifier(cursor)
                cursor_key = "page"
            if cursor is None:
                converted = convert_messages(source_messages, family=family)
                return Conversation(
                    family=family,
                    organization_id=organization_id,
                    conversation_id=conversation_id,
                    messages=converted.messages,
                    limitations=sorted(limitations | set(converted.limitations)),
                )
            if cursor in seen_cursors:
                raise ComplianceError("Repeated transcript cursor; refusing an incomplete import")
            seen_cursors.add(cursor)
            params[cursor_key] = cursor
        raise ComplianceError("Transcript exceeds max_pages; increase the bound and restart")


class ConvertedMessages(BaseModel):
    """Inspect message mappings with explicitly retained source capture limitations."""

    messages: list[JsonObject]
    limitations: list[str]


def convert_messages(raw_messages: list[JsonObject], *, family: Family) -> ConvertedMessages:
    """Preserve ordered text, complete tools, unavailable markers and source metadata.

    Truncated tool arguments, absent IDs, invalid JSON, unknown blocks and
    ambiguous tool identities raise ComplianceError. Text truncation, unavailable
    content and unverified provenance remain visible in metadata and limitations.
    Empty source content gets a labeled placeholder, never an unexplained blank
    message. Original timestamps are metadata: Watcher's generic ingest path dates the
    messages at import time. Attachments are not downloaded.
    """
    messages: list[JsonObject] = []
    limitations: set[str] = set()
    calls: set[str] = set()
    results: set[str] = set()
    for raw in raw_messages:
        try:
            source = _Message.model_validate(raw)
        except ValidationError:
            raise ComplianceError("Invalid source message shape") from None
        if source.created_at.tzinfo is None:
            raise ComplianceError("Source timestamps must include a UTC offset")
        provenance = raw.get("provenance")
        unavailable = raw.get("content_unavailable") is True or (
            isinstance(provenance, dict) and provenance.get("type") == "content_unavailable"
        )
        if provenance is not None or unavailable:
            limitations.add("Some source content is unavailable, synthetic or not verified as model output.")
        content_empty = not source.content and not unavailable
        if content_empty:
            limitations.add("The source returned a message with no content and no availability marker.")
        if any(raw.get(key) for key in ("files", "generated_files", "artifacts")):
            limitations.add("Attachments and artifacts are listed by the source but are not downloaded.")
        metadata: JsonObject = {
            "source": "claude-compliance",
            "family": family,
            "message_id": source.id,
            "created_at": source.created_at.isoformat(),
            "provenance": provenance,
            "content_unavailable": unavailable,
            "content_empty": content_empty,
        }
        if unavailable and source.content:
            raise ComplianceError("Unavailable source message unexpectedly contains content")
        placeholder = "[Transcript content unavailable]" if unavailable else "[Source message has no content]"
        blocks = source.content or [{"type": "text", "text": placeholder}]
        for index, block in enumerate(blocks):
            kind = block["type"]
            block_metadata = {**metadata, "block_index": index, "truncated": block.get("truncated", False)}
            message: JsonObject = {"id": f"{source.id}:{index}", "metadata": {"compliance": block_metadata}}
            if block.get("truncated") is True:
                limitations.add("Some returned text or tool results are truncated or omit non-text content.")
            if kind == "text":
                text = block["text"]
                if not isinstance(text, str):
                    raise ComplianceError("Expected text content")
                if block.get("thinking_redacted") is True:
                    limitations.add("The source redacted assistant reasoning from some text.")
                    block_metadata["thinking_redacted"] = True
                message.update(role=source.role, content=text)
            elif kind == "tool_use":
                if source.role != "assistant":
                    raise ComplianceError("A source tool call must belong to an assistant message")
                if block.get("truncated") is True:
                    raise ComplianceError("Truncated tool arguments cannot be imported faithfully")
                identity = _identifier(block["id"])
                if identity in calls or identity in results:
                    raise ComplianceError("Duplicate or out-of-order source tool identity")
                calls.add(identity)
                arguments = _object(_json(_identifier(block["input"])))
                message.update(
                    role="assistant",
                    content="",
                    tool_calls=[
                        {
                            "id": identity,
                            "function": _identifier(block["name"]),
                            "arguments": arguments,
                            "type": "function",
                        }
                    ],
                )
            elif kind == "tool_result":
                identity = _identifier(block["tool_use_id"])
                if identity not in calls or identity in results:
                    raise ComplianceError("A tool result lacks a unique earlier source call")
                results.add(identity)
                content = block["content"]
                if not isinstance(content, list):
                    raise ComplianceError("Expected text entries in a tool result")
                parts: list[JsonValue] = []
                for value in content:
                    entry = _object(value)
                    if entry["type"] != "text" or not isinstance(entry["text"], str):
                        raise ComplianceError("Non-text tool results are not supported")
                    parts.append({"type": "text", "text": entry["text"]})
                is_error = block["is_error"]
                if not isinstance(is_error, bool):
                    raise ComplianceError("Expected a Boolean tool error flag")
                message.update(role="tool", content=parts or "", tool_call_id=identity)
                if is_error:
                    message["error"] = {"type": "unknown", "message": "Tool reported an error"}
            else:
                raise ComplianceError("Unsupported source content block; nothing was imported")
            messages.append(message)
    return ConvertedMessages(messages=messages, limitations=sorted(limitations))


def _canonical(value: JsonValue) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def write_receipt(path: Path, receipt: ImportReceipt) -> None:
    """Atomically replace one local receipt after an accepted submission.

    One importer must own this path. It is an audit/resume aid, not a watermark
    or a reason to skip later imports: source history and destination state can
    change. A crash after delivery but before this write requires replay.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".receipt-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(receipt.model_dump_json(indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


async def import_conversation(
    source: ComplianceClient,
    watcher: AsyncWatcherClient,
    *,
    family: Family,
    conversation_id: str,
    receipt_path: Path | None = None,
) -> ImportReceipt:
    """Record one fully fetched transcript and optionally retain its local receipt.

    No tool evaluation is requested. A successful response schedules storage;
    verify the actual conversation through Watcher's query API or Analyzer.
    Source or HTTP submission errors leave an existing receipt unchanged, but
    do not establish whether an earlier request was stored. Every invocation
    fetches and sends the current transcript using the same external identity;
    this does not promise exactly-once delivery.
    """
    conversation = await source.fetch(family, conversation_id)
    if not conversation.messages:
        raise ComplianceError("The source returned no transcript messages")
    response = await watcher.pre_tool_use_hook(
        [],
        messages=conversation.messages,
        external_ids={"other": conversation.external_id},
    )
    if response != []:
        raise ComplianceError("Unexpected Watcher transcript-only response")
    receipt = ImportReceipt(
        external_id=conversation.external_id,
        source_digest=hashlib.sha256(_canonical(conversation.messages).encode()).hexdigest(),
        submitted_at=datetime.now(UTC),
        message_count=len(conversation.messages),
        limitations=conversation.limitations,
    )
    if receipt_path is not None:
        write_receipt(receipt_path, receipt)
    return receipt
