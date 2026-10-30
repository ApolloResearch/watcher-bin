"""Plan bounded, independently parseable uploads from a local acknowledgement log."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from watcher_transcript_transport.claude import branch_indices, split_preserves_order, trim_incomplete_tail
from watcher_transcript_transport.codex import scan_codex_call_cycles

MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_CHUNK_ENTRIES = 512


class UploadTooLarge(ValueError):
    """The smallest independently parseable request exceeds the wire limit."""


def encode(body: dict[str, Any]) -> bytes:
    """Serialize the exact bytes whose length the planner enforces."""
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()


def fold_context(entries: list[dict[str, Any]]) -> dict[str, str]:
    """Fold nonempty Codex context fields independently, matching its parser."""
    context = {}
    for entry in entries:
        if entry.get("type") == "turn_context" and isinstance(entry.get("payload"), dict):
            for key in ("model", "user_instructions", "developer_instructions"):
                value = entry["payload"].get(key)
                if isinstance(value, str) and value:
                    context[key] = value
    return context


def _claude_acknowledgement_is_safe(entries: list[dict[str, Any]], end: int) -> bool:
    # A saved receipt may include closing assistant text the caller marked final,
    # but cannot cut an open tool cycle when more source entries arrive.
    return end == len(entries) or (
        split_preserves_order(entries, end)
        and len(trim_incomplete_tail(entries[:end], allow_trailing_assistant_text=True)) == end
    )


def matching_acknowledgements(
    entries: list[dict[str, Any]], prefixes: list[str], acknowledgements: list[dict[str, Any]], format: str
) -> list[dict[str, Any]]:
    """Keep matching source prefixes; a Claude fork also needs a parse-safe start."""
    valid = [
        ack
        for ack in acknowledgements
        if ack.get("branch_end") is None
        and 0 < ack["end"] <= len(prefixes)
        and prefixes[ack["end"] - 1] == ack["prefix"]
    ]
    if format == "claude-code-jsonl":
        while valid and not _claude_acknowledgement_is_safe(entries, valid[-1]["end"]):
            valid.pop()
    else:
        safe_ends = set(scan_codex_call_cycles(entries, allow_trailing_assistant_output=False).boundaries)
        safe_ends.add(scan_codex_call_cycles(entries, allow_trailing_assistant_output=True).complete_until)
        safe_ends.add(len(entries))
        while valid and valid[-1]["end"] not in safe_ends:
            end = valid[-1]["end"]
            # Bookkeeping after an acknowledged closing message does not alter it.
            next_response = next(
                (i for i in range(end, len(entries)) if entries[i].get("type") in ("response_item", "compacted")),
                len(entries),
            )
            if next_response in safe_ends and (
                scan_codex_call_cycles(entries[:end], allow_trailing_assistant_output=True).complete_until == end
            ):
                break
            valid.pop()
    return valid


class Chunk:  # noqa: B903
    """A request and the exclusive local entry offset it acknowledges."""

    __slots__ = ("body", "end", "start", "branch_end", "branch_prefix")

    def __init__(self, body: bytes, start: int, end: int) -> None:
        self.body = body
        self.start = start
        self.end = end
        self.branch_end: int | None = None
        self.branch_prefix: str | None = None


def next_chunk(
    template: dict[str, Any], entries: list[dict[str, Any]], start: int, anchor: dict[str, Any] | None, fork: bool
) -> Chunk:
    """Choose a complete parser interval within the exact 8 MiB request bound.

    Codex compactions start unanchored windows. Context comes from local source,
    including the first session metadata that identifies inherited child work.
    Claude cuts preserve both tree order and complete tool-use/result cycles.
    Callers trim live snapshots before planning; the final boundary preserves
    any open calls deliberately retained for an exited process. A boundary may
    exceed the entry-count target, but never the byte limit.
    """
    if start >= len(entries):
        raise ValueError("No entries remain")
    codex = template["format"] == "codex-jsonl"
    stop = len(entries)
    resets: list[int] = []
    if codex:
        resets = [
            i
            for i, e in enumerate(entries)
            if e.get("type") == "compacted"
            and isinstance(e.get("payload"), dict)
            and (e["payload"].get("replacement_history") is not None or e["payload"].get("message"))
        ]
        stop = next((i for i in resets if i > start), len(entries))
        if start in resets:
            anchor = None
        scan = scan_codex_call_cycles(entries[start:stop], allow_trailing_assistant_output=True)
        safe_ends = set(scan_codex_call_cycles(entries[start:stop], allow_trailing_assistant_output=False).boundaries)
        safe_ends.add(scan.complete_until)
        if stop == len(entries):
            safe_ends.add(stop - start)
        candidates = [start + i for i in sorted(safe_ends) if i > 0]
    else:
        candidates = range(start + 1, len(entries) + 1)

    def body(end: int) -> bytes:
        selected = entries[start:end]
        if codex and start:
            meta = next((e for e in entries[:start] if e.get("type") == "session_meta"), None)
            context = fold_context(entries[:start])
            seeds = [meta] if meta is not None else []
            if start in resets and meta is not None:
                boundary = meta.get("payload", {}).get("subagent_history_start_ordinal")
                if isinstance(boundary, int):
                    # Replacement history carries native IDs, but loses ordinals.
                    # Parse its inherited prefix first so those IDs keep their
                    # provenance when the compaction replaces the messages.
                    seeds.extend(
                        e
                        for e in entries[:start]
                        if e is not meta and isinstance(e.get("ordinal"), int) and e["ordinal"] < boundary
                    )
            if context:
                seeds.append(
                    {
                        "type": "turn_context",
                        "timestamp": entries[start].get("timestamp", template["timestamp"]),
                        "payload": context,
                    }
                )
            selected = [*seeds, *selected]
        return encode(
            {
                "source": "watcher",
                "trajectories": [{**template, "entries": selected, "append_after": anchor, "fork": fork}],
            }
        )

    def safe(end: int) -> bool:
        return (
            codex
            or end == len(entries)
            or (
                split_preserves_order(entries[start:], end - start)
                and len(trim_incomplete_tail(entries[start:end], allow_trailing_assistant_text=False)) == end - start
            )
        )

    preferred = min(start + MAX_CHUNK_ENTRIES, stop)
    # Try the largest target boundary first. Linear histories normally need one
    # parse, rather than reparsing every possible boundary in the transcript.
    for end in reversed([i for i in candidates if i <= preferred]):
        encoded = body(end)
        if len(encoded) <= MAX_BODY_BYTES and safe(end):
            return Chunk(encoded, start, end)
    for end in candidates:
        if end <= preferred:
            continue
        encoded = body(end)
        if len(encoded) > MAX_BODY_BYTES:
            break
        if safe(end):
            return Chunk(encoded, start, end)
    raise UploadTooLarge("No independently parseable interval fits in an 8 MiB request")


class UploadPlan:
    """Schedule each raw Claude branch against durable, content-verified anchors.

    Checkpoints fingerprint a branch prefix rather than a contiguous file span.
    Appending a rewind therefore keeps the old branch's acknowledgements and
    can reuse the shared prefix while uploading the new branch independently.
    Ordinary non-fork histories continue through the existing linear planner.
    """

    def __init__(self, template: dict[str, Any], entries: list[dict[str, Any]], prefixes: list[str]) -> None:
        self.template = template
        self.entries = entries
        self.prefixes = prefixes
        self.positions = branch_indices(entries) if template["format"] == "claude-code-jsonl" else []
        self.is_branched = len(self.positions) > 1
        self.hashes: list[list[str]] = []
        self.last_anchor: dict[str, Any] | None = None
        if self.is_branched:
            for positions in self.positions:
                digest = hashlib.sha256()
                hashes = []
                for index in positions:
                    digest.update(encode(entries[index]))
                    digest.update(b"\n")
                    hashes.append(digest.hexdigest())
                self.hashes.append(hashes)

    def valid_acknowledgements(self, acknowledgements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Retain unchanged branch prefixes and matching legacy file prefixes."""
        if not self.is_branched:
            return matching_acknowledgements(self.entries, self.prefixes, acknowledgements, self.template["format"])
        valid = []
        for ack in acknowledgements:
            branch_end = ack.get("branch_end")
            if branch_end is not None:
                if any(
                    0 < branch_end <= len(hashes) and hashes[branch_end - 1] == ack.get("branch_prefix")
                    for hashes in self.hashes
                ):
                    valid.append(ack)
            elif 0 < ack["end"] <= len(self.prefixes) and self.prefixes[ack["end"] - 1] == ack["prefix"]:
                valid.append(ack)
        return valid

    def next_chunk(self, acknowledgements: list[dict[str, Any]], fork: bool) -> Chunk | None:
        """Choose the next bounded request, or None after every branch is acknowledged."""
        if not self.is_branched:
            start = acknowledgements[-1]["end"] if acknowledgements else 0
            self.last_anchor = acknowledgements[-1]["anchor"] if acknowledgements else None
            if start == len(self.entries):
                return None
            return next_chunk(self.template, self.entries, start, self.last_anchor, fork)
        for positions, hashes in zip(self.positions, self.hashes, strict=True):
            branch = [self.entries[index] for index in positions]
            start = 0
            anchor = None
            for ack in acknowledgements:
                branch_end = ack.get("branch_end")
                if branch_end is None:
                    branch_end = ack["end"]
                    matches = positions[:branch_end] == list(range(branch_end))
                else:
                    matches = branch_end <= len(hashes) and hashes[branch_end - 1] == ack.get("branch_prefix")
                if (
                    matches
                    and start < branch_end <= len(branch)
                    and _claude_acknowledgement_is_safe(branch, branch_end)
                ):
                    start, anchor = branch_end, ack["anchor"]
            self.last_anchor = anchor
            if start == len(branch):
                continue
            chunk = next_chunk(self.template, branch, start, anchor, True)
            chunk.branch_end = chunk.end
            chunk.branch_prefix = hashes[chunk.end - 1]
            chunk.end = positions[chunk.end - 1] + 1
            return chunk
        return None


class UploadState:
    """Shared acknowledgement, replay and refusal decisions; callers own I/O and locking."""

    def __init__(self, plan: UploadPlan) -> None:
        self.plan = plan
        self.acknowledgements: list[dict[str, Any]] = []
        self.blocked_body: str | None = None
        self.forking = False
        self.restarted = False
        self.finished = False
        self.chunk: Chunk | None = None

    def load(self, acknowledgements: list[dict[str, Any]], blocked_body: str | None, forking: bool) -> bool:
        """Reconcile durable state with this snapshot; return whether every checkpoint still matches."""
        valid = self.plan.valid_acknowledgements(acknowledgements)
        old_end = acknowledgements[-1]["end"] if acknowledgements else 0
        new_end = valid[-1]["end"] if valid else 0
        self.acknowledgements = valid
        self.blocked_body = blocked_body
        self.forking = forking or new_end < old_end
        self.finished = False
        return len(valid) == len(acknowledgements)

    def next_chunk(self) -> Chunk | None:
        self.chunk = self.plan.next_chunk(self.acknowledgements, self.forking)
        if self.chunk is None:
            self.finished = True
            if self.plan.entries:
                completion = {
                    "end": len(self.plan.entries),
                    "prefix": self.plan.prefixes[-1],
                    "anchor": self.plan.last_anchor,
                    "branch_end": None,
                    "branch_prefix": None,
                }
                if not self.acknowledgements or self.acknowledgements[-1] != completion:
                    self.acknowledgements.append(completion)
            self.forking = False
        elif hashlib.sha256(self.chunk.body).hexdigest() == self.blocked_body:
            return None
        return self.chunk

    def accept(self, anchor: dict[str, Any] | None) -> None:
        """Advance only after the caller has accepted the server's response."""
        assert self.chunk is not None
        self.acknowledgements.append(
            {
                "end": self.chunk.end,
                "prefix": self.plan.prefixes[self.chunk.end - 1],
                "anchor": anchor,
                "branch_end": self.chunk.branch_end,
                "branch_prefix": self.chunk.branch_prefix,
            }
        )
        self.blocked_body = None
        self.forking = self.forking and self.chunk.end < len(self.plan.entries)

    def reject(self, missing_anchor: bool, content_refusal: bool) -> Literal["retry", "stop", "raise"]:
        """Restart once for missing state; preserve and suppress a refused request."""
        assert self.chunk is not None
        if missing_anchor and not self.restarted:
            self.acknowledgements = []
            self.blocked_body = None
            self.forking = False
            self.restarted = True
            return "retry"
        if content_refusal:
            self.blocked_body = hashlib.sha256(self.chunk.body).hexdigest()
            return "stop"
        return "raise"

    def to_dict(self) -> dict[str, Any]:
        return {
            "acknowledgements": self.acknowledgements,
            "blocked_body": self.blocked_body,
            "forking": self.forking,
        }
