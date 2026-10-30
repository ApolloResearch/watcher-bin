"""Effect-free JSONL upload planning for Watcher ingestion clients.

The functions in this module make deterministic transport decisions without
performing filesystem, persistence, HTTP, deadline, or logging work. Runtimes
provide those effects around this shared core so Watcher Live and remote
collectors follow the same cursor, chunking, and recovery rules.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from enum import Enum
from typing import Any

__all__ = [
    "DEFAULT_UPLOAD_CHUNK_TARGET_BYTES",
    "UploadCursor",
    "UploadMode",
    "UploadReason",
    "choose_upload",
    "chunk_ends",
    "opening_end_candidates",
    "parse_jsonl_entries",
    "parse_jsonl_snapshot",
]

DEFAULT_UPLOAD_CHUNK_TARGET_BYTES = 8 * 1024 * 1024

JsonEntry = dict[str, Any]
BoundaryCheck = Callable[[int, int, bool], bool]
RebaselineCheck = Callable[[list[JsonEntry], int], bool]


class UploadMode(Enum):
    """Network operation selected for the current transcript snapshot."""

    FULL = "full"
    APPEND = "append"
    SKIP = "skip"


class UploadReason(Enum):
    """Why a transcript snapshot selected its upload mode."""

    NO_CURSOR = "no_cursor"
    PREFIX_MISMATCH = "prefix_mismatch"
    UNCHANGED = "unchanged"
    REBASELINE_REQUIRED = "rebaseline_required"
    APPENDABLE = "appendable"


# These records stay dependency-free for hook startup and cannot use the
# repository's preferred Pydantic models; dataclasses are prohibited by style.
class TranscriptSnapshot:  # noqa: B903
    """Valid JSONL entries and the cumulative fingerprint after each entry."""

    __slots__ = ("entries", "prefix_hashes", "retained_entries")

    entries: list[JsonEntry]
    prefix_hashes: list[str]

    def __init__(self, entries: list[JsonEntry], prefix_hashes: list[str], retained_entries: int = 0) -> None:
        self.entries = entries
        self.prefix_hashes = prefix_hashes
        self.retained_entries = retained_entries


class UploadCursor:  # noqa: B903
    """Runtime-independent cursor describing the transcript prefix on the server."""

    __slots__ = ("uploaded_entry_count", "uploaded_leaf_hash", "uploaded_prefix_hash")

    uploaded_entry_count: int
    uploaded_leaf_hash: str | None
    uploaded_prefix_hash: str | None

    def __init__(
        self,
        uploaded_entry_count: int,
        uploaded_leaf_hash: str | None,
        uploaded_prefix_hash: str | None,
    ) -> None:
        self.uploaded_entry_count = uploaded_entry_count
        self.uploaded_leaf_hash = uploaded_leaf_hash
        self.uploaded_prefix_hash = uploaded_prefix_hash


class UploadDecision:  # noqa: B903
    """Selected mode plus the caller-visible cursor action behind it."""

    __slots__ = ("mode", "reason", "should_clear_cursor")

    mode: UploadMode
    reason: UploadReason
    should_clear_cursor: bool

    def __init__(self, mode: UploadMode, reason: UploadReason, should_clear_cursor: bool) -> None:
        self.mode = mode
        self.reason = reason
        self.should_clear_cursor = should_clear_cursor


def _parse_jsonl(lines: Iterator[str], prefix_hashes: list[str] | None) -> list[JsonEntry]:
    """Parse valid JSONL lines, optionally fingerprinting accepted prefixes."""
    entries: list[JsonEntry] = []
    digest = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        entries.append(entry)
        if prefix_hashes is not None:
            if digest is None:
                digest = hashlib.sha256()
            encoded = line.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
            prefix_hashes.append(digest.hexdigest())
    return entries


def parse_jsonl_entries(lines: Iterator[str]) -> list[JsonEntry]:
    """Parse valid JSONL entries without computing upload fingerprints."""
    return _parse_jsonl(lines, None)


def parse_jsonl_snapshot(lines: Iterator[str]) -> TranscriptSnapshot:
    """Parse valid JSONL lines and fingerprint the accepted raw prefixes.

    Blank and malformed lines are ignored exactly as Watcher Live historically
    ignored them. Each fingerprint commits to the stripped bytes and their
    lengths, preventing concatenation ambiguity while allowing a persisted
    cursor to detect same-length rewrites and changed prefixes.
    """
    prefix_hashes: list[str] = []
    entries = _parse_jsonl(lines, prefix_hashes)
    return TranscriptSnapshot(entries, prefix_hashes)


def choose_upload(
    entries: list[JsonEntry],
    prefix_hashes: list[str],
    cursor: UploadCursor | None,
    rebaseline_check: RebaselineCheck | None,
) -> UploadDecision:
    """Choose full, append, or skip from one transcript snapshot and cursor.

    A missing or incomplete cursor selects a safe full upload. A cursor whose
    stored prefix no longer matches also requests that the runtime clear its
    persisted cursor before uploading in full. Only a matching, shorter prefix
    may append, and the platform-specific parser guard gets the final say.
    """
    if cursor is None or not cursor.uploaded_leaf_hash or cursor.uploaded_entry_count <= 0:
        return UploadDecision(UploadMode.FULL, UploadReason.NO_CURSOR, False)

    uploaded_count = cursor.uploaded_entry_count
    prefix_is_invalid = (
        cursor.uploaded_prefix_hash is None
        or uploaded_count > len(entries)
        or uploaded_count > len(prefix_hashes)
        or prefix_hashes[uploaded_count - 1] != cursor.uploaded_prefix_hash
    )
    if prefix_is_invalid:
        return UploadDecision(UploadMode.FULL, UploadReason.PREFIX_MISMATCH, True)
    if uploaded_count == len(entries):
        return UploadDecision(UploadMode.SKIP, UploadReason.UNCHANGED, False)
    if rebaseline_check is not None and rebaseline_check(entries, uploaded_count):
        return UploadDecision(UploadMode.FULL, UploadReason.REBASELINE_REQUIRED, False)
    return UploadDecision(UploadMode.APPEND, UploadReason.APPENDABLE, False)


def chunk_ends(
    entries: list[JsonEntry],
    start: int,
    boundary_check: BoundaryCheck | None,
    mode: UploadMode,
    target_bytes: int = DEFAULT_UPLOAD_CHUNK_TARGET_BYTES,
) -> list[int]:
    """Return exclusive safe chunk ends covering ``entries[start:]``.

    JSON size only proposes each boundary: every interior end becomes the
    cursor for a later append, so the optional platform guard may move it
    forward until both the remaining suffix and, for append chunks, the chunk
    itself parse independently. Correctness wins over the target size when no
    earlier safe boundary exists. A single oversized entry is likewise kept
    intact rather than making progress impossible.
    """
    ends: list[int] = []
    total = len(entries)
    sizes = [len(json.dumps(entry, separators=(",", ":"))) for entry in entries[start:]]
    chunk_start = start
    while chunk_start < total:
        size = 0
        end = chunk_start
        while end < total:
            entry_size = sizes[end - start]
            if size and size + entry_size > target_bytes:
                break
            size += entry_size
            end += 1
        if boundary_check is not None:
            chunk_is_append = mode == UploadMode.APPEND or bool(ends)
            while end < total and boundary_check(chunk_start, end, chunk_is_append):
                end += 1
        ends.append(end)
        chunk_start = end
    if not ends:
        ends.append(total)
    return ends


def opening_end_candidates(
    entries: list[JsonEntry],
    first_end: int,
    boundary_check: BoundaryCheck | None,
    acknowledged_entry_count: int | None,
) -> list[int]:
    """Return progressively larger full-ingest ends for an overtaken opening chunk.

    When a size-bounded opening chunk is already an interior snapshot of the
    server chain, it cannot become an append anchor. The next attempts jump one
    entry beyond the last acknowledged count when that helps, then restore the
    historical whole-file upload contract.
    """
    total = len(entries)
    candidates = [first_end]
    if first_end >= total:
        return candidates
    if acknowledged_entry_count is not None and acknowledged_entry_count > first_end:
        informed = min(acknowledged_entry_count + 1, total)
        if boundary_check is not None:
            while informed < total and boundary_check(0, informed, False):
                informed += 1
        if informed < total:
            candidates.append(informed)
    candidates.append(total)
    return candidates
