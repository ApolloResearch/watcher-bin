"""Plan bounded, independently parseable uploads from a local acknowledgement log."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from watcher_transcript_transport.claude import (
    _branch_indices_from_walk,
    _live_chain_walk,
    split_preserves_order,
    trim_incomplete_tail,
)
from watcher_transcript_transport.claude_splits import ClaudeSplitIndex, TailCompleteness
from watcher_transcript_transport.codex import scan_codex_call_cycles
from watcher_transcript_transport.codex_splits import CodexScanIndex
from watcher_transcript_transport.copilot import CopilotSplitIndex
from watcher_transcript_transport.elision import elide_entry

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


def _claude_acknowledgement_is_safe(
    entries: list[dict[str, Any]], end: int, index: ClaudeSplitIndex | None = None
) -> bool:
    # A saved receipt may include closing assistant text the caller marked final,
    # but cannot cut an open tool cycle when more source entries arrive.
    if index is not None and index.covers(entries) and type(end) is int and 0 <= end <= len(entries):
        # Same answer as below: the index's checks cannot raise, so their order does not matter.
        return end == len(entries) or (
            index.acknowledgement_complete(end) and (index.proves(end) or split_preserves_order(entries, end))
        )
    return end == len(entries) or (
        split_preserves_order(entries, end)
        and len(trim_incomplete_tail(entries[:end], allow_trailing_assistant_text=True)) == end
    )


def matching_acknowledgements(
    entries: list[dict[str, Any]],
    prefixes: list[str],
    acknowledgements: list[dict[str, Any]],
    format: str,
    index: ClaudeSplitIndex | CodexScanIndex | CopilotSplitIndex | None = None,
) -> list[dict[str, Any]]:
    """Keep matching source prefixes whose resumed parse preserves the history.

    ``index``, built for ``entries``, only makes the safety checks cheaper.
    """
    valid = [
        ack
        for ack in acknowledgements
        if ack.get("branch_end") is None
        and 0 < ack["end"] <= len(prefixes)
        and prefixes[ack["end"] - 1] == ack["prefix"]
    ]
    if format == "claude-code-jsonl":
        claude_index = index if isinstance(index, ClaudeSplitIndex) else None
        while valid and not _claude_acknowledgement_is_safe(entries, valid[-1]["end"], claude_index):
            valid.pop()
    elif format == "copilot-events-jsonl":
        copilot_index = (
            index if isinstance(index, CopilotSplitIndex) and index.covers(entries) else CopilotSplitIndex(entries)
        )
        while valid and not copilot_index.is_safe(valid[-1]["end"]):
            valid.pop()
    else:
        codex_index = index if isinstance(index, CodexScanIndex) and index.covers(entries) else None
        if codex_index is not None:
            safe_ends = codex_index.safe_ends
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
                (
                    codex_index.prefix_complete_until(end)
                    if codex_index is not None and type(end) is int and 0 <= end <= len(entries)
                    else scan_codex_call_cycles(entries[:end], allow_trailing_assistant_output=True).complete_until
                )
                == end
            ):
                break
            valid.pop()
    return valid


class Chunk:  # noqa: B903
    """A request and the exclusive local entry offset it acknowledges.

    ``anchor`` and ``fork`` are the request's ``append_after`` and ``fork`` fields.
    """

    __slots__ = ("body", "end", "start", "anchor", "fork", "branch_end", "branch_prefix")

    def __init__(self, body: bytes, start: int, end: int, anchor: dict[str, Any] | None, fork: bool) -> None:
        self.body = body
        self.start = start
        self.end = end
        self.anchor = anchor
        self.fork = fork
        self.branch_end: int | None = None
        self.branch_prefix: str | None = None


def next_chunk(
    template: dict[str, Any],
    entries: list[dict[str, Any]],
    start: int,
    anchor: dict[str, Any] | None,
    fork: bool,
    index: ClaudeSplitIndex | CodexScanIndex | CopilotSplitIndex | None = None,
) -> Chunk:
    """Choose an independently parseable native transcript interval.

    Codex compactions start unanchored windows. Context comes from local source,
    including the first session metadata that identifies inherited child work.
    Claude cuts preserve both tree order and complete tool-use/result cycles.
    Callers trim live snapshots before planning; the final boundary preserves
    any open calls deliberately retained for an exited process. A boundary may
    exceed the entry-count target, but never the byte limit for Claude or Codex.
    Copilot instead treats 8 MiB as a target: its first indivisible interval may
    exceed it so a large tool result and all events it depends on stay intact.

    ``index``, built for this exact ``entries`` list, makes the checks cheap: a
    `ClaudeSplitIndex` also lets the tool-cycle check run before a target is
    encoded, a `CodexScanIndex` replaces the window scans and the fold of
    everything before ``start``, and a `CopilotSplitIndex` indexes cut safety. The chunk returned, and any exception raised,
    stay the same.
    """
    if start >= len(entries):
        raise ValueError("No entries remain")
    if template["format"] == "copilot-events-jsonl":
        copilot_index = (
            index if isinstance(index, CopilotSplitIndex) and index.covers(entries) else CopilotSplitIndex(entries)
        )
        return _next_copilot_chunk(template, entries, start, anchor, fork, copilot_index)
    codex = template["format"] == "codex-jsonl"
    codex_index = index if codex and isinstance(index, CodexScanIndex) and index.covers(entries) else None
    stop = len(entries)
    starts_window = False
    if codex and codex_index is not None:
        stop = codex_index.next_reset_after(start)
        starts_window = codex_index.is_reset(start)
        if starts_window:
            anchor = None
        candidates = codex_index.candidates(start, stop, min(start + MAX_CHUNK_ENTRIES, stop))
    elif codex:
        resets = [
            i
            for i, e in enumerate(entries)
            if e.get("type") == "compacted"
            and isinstance(e.get("payload"), dict)
            and (e["payload"].get("replacement_history") is not None or e["payload"].get("message"))
        ]
        stop = next((i for i in resets if i > start), len(entries))
        starts_window = start in resets
        if starts_window:
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
            if codex_index is not None:
                meta, context = codex_index.session_meta_before(start), codex_index.context_before(start)
            else:
                meta = next((e for e in entries[:start] if e.get("type") == "session_meta"), None)
                context = fold_context(entries[:start])
            seeds = [meta] if meta is not None else []
            if starts_window and meta is not None:
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

    tail = proof = None
    if isinstance(index, ClaudeSplitIndex) and not codex and index.covers(entries):
        tail, proof = TailCompleteness(entries, start, allow_trailing_assistant_text=False), index

    def safe(end: int) -> bool:
        if tail is not None and proof is not None and end != len(entries):
            # Same answer as below: neither check can raise on an indexed snapshot.
            return tail.complete(end) and (
                proof.proves_window(start, end) or split_preserves_order(entries[start:], end - start)
            )
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
    targets = [i for i in candidates if i <= preferred]
    targets.reverse()
    # With an index, a target that ends inside a tool cycle is skipped before
    # it is encoded. That returns the same target, because on an indexed
    # snapshot only encoding can raise (a lone surrogate, extreme nesting), and
    # encoding fails for every target at or past the first bad entry: the
    # plain loop raises exactly when encoding its first target raises. When
    # that first target was skipped, it is encoded anyway wherever the plain
    # loop would have met it first: on an exception, before falling through to
    # the larger targets, or when an entry between the chosen end and it fails
    # a cheap per-entry probe. Every encode stays at this function's call depth.
    skipped = None
    if tail is not None and targets and targets[0] != len(entries) and not tail.complete(targets[0]):
        skipped = targets[0]
    found = None
    try:
        for end in targets:
            if tail is not None and end != len(entries) and not tail.complete(end):
                continue
            encoded = body(end)
            if len(encoded) <= MAX_BODY_BYTES and safe(end):
                found = Chunk(encoded, start, end, anchor, fork)
                break
    except Exception:
        if skipped is not None:
            body(skipped)
        raise
    if skipped is not None and (found is None or not _entries_encode(entries[found.end : skipped])):
        body(skipped)
    if found is not None:
        return found
    for end in candidates:
        if end <= preferred:
            continue
        encoded = body(end)
        if len(encoded) > MAX_BODY_BYTES:
            break
        if safe(end):
            return Chunk(encoded, start, end, anchor, fork)
    raise UploadTooLarge("No independently parseable interval fits in an 8 MiB request")


def _next_copilot_chunk(
    template: dict[str, Any],
    entries: list[dict[str, Any]],
    start: int,
    anchor: dict[str, Any] | None,
    fork: bool,
    index: CopilotSplitIndex,
) -> Chunk:
    """Keep the first indivisible Copilot interval whole, even above 8 MiB.

    Only cut where the remaining events can be parsed as an append, including
    dependencies that close or reuse earlier calls. A resumed chunk carries the
    original session.start and referenced skill invocations as context seeds,
    which do not count toward the acknowledged source offset. Tool outputs are
    capped on the wire, while offsets and hashes still identify the raw source.
    Callers may retain an incomplete final interval after its process exits;
    a later extension revalidates that acknowledgement.

    First find the byte/count target without repeatedly encoding growing bodies.
    Prefer the last indexed safe cut before it, otherwise extend to the first
    safe cut. Once the starting cut is globally safe, it stays safe for every
    shorter suffix, so selecting an endpoint requires no prefix rescans.
    This preserves progress without growing an opening request to the whole file
    merely because the server has already stored later messages.
    """
    if start and not index.is_safe(start):
        raise ValueError("Copilot append depends on events before its cursor")
    seeded = index.seed_entries(start, start)
    envelope: dict[str, Any] = {
        "source": "watcher",
        "trajectories": [{**template, "entries": seeded, "append_after": anchor, "fork": fork}],
    }
    size = len(encode(envelope))
    preferred = start
    skill_sources: set[int] = set()
    for end in range(start + 1, min(start + MAX_CHUNK_ENTRIES, len(entries)) + 1):
        source = index.skill_sources.get(end - 1)
        needs_skill = source is not None and source < start and source not in skill_sources
        preceding = len(seeded) + len(skill_sources) + end - start - 1
        entry_size = len(encode(elide_entry(entries[end - 1]))) + int(preceding > 0 or needs_skill)
        if needs_skill:
            assert source is not None
            entry_size += len(encode(entries[source])) + int(preceding > 0)
        if preferred > start and size + entry_size > MAX_BODY_BYTES:
            break
        size += entry_size
        if needs_skill:
            assert source is not None
            skill_sources.add(source)
        preferred = end

    for end in range(preferred, start, -1):
        if index.is_safe(end):
            break
    else:
        end = preferred + 1
        while end < len(entries) and not index.is_safe(end):
            end += 1
    envelope["trajectories"][0]["entries"] = [
        elide_entry(entry) for entry in [*index.seed_entries(start, end), *entries[start:end]]
    ]
    return Chunk(encode(envelope), start, end, anchor, fork)


def _entries_encode(entries: list[dict[str, Any]]) -> bool:
    """Whether each entry encodes on its own, nested as deep as a request body nests it.

    A cheap probe of a few entries instead of a whole chunk. A failure only
    sends the caller to encode the full target, whose outcome decides.
    """
    try:
        for entry in entries:
            encode({"source": "watcher", "trajectories": [{"entries": [entry]}]})
    except Exception:  # noqa: BLE001
        return False
    return True


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
        claude = template["format"] == "claude-code-jsonl"
        walk = _live_chain_walk(entries) if claude else None
        self.positions = _branch_indices_from_walk(entries, walk) if claude else []
        self.is_branched = len(self.positions) > 1
        self.hashes: list[list[str]] = []
        self.last_anchor: dict[str, Any] | None = None
        # Boundary indexes are built on first use: a linear Claude file reuses
        # the walk above, a branched one gets an index per branch list, and a
        # Codex rollout or Copilot conversation gets one scan index.
        self._linear_index_due = (claude and not self.is_branched) or template["format"] in (
            "codex-jsonl",
            "copilot-events-jsonl",
        )
        self._linear_walk = walk if claude and self._linear_index_due else None
        self._linear_index: ClaudeSplitIndex | CodexScanIndex | CopilotSplitIndex | None = None
        branches = self.positions if self.is_branched else []
        self._branches = [[entries[index] for index in positions] for positions in branches]
        self._branch_indexes: list[ClaudeSplitIndex | None] = [None] * len(branches)
        # How many leading positions of each branch are 0, 1, 2, ...: a legacy file-prefix
        # acknowledgement lies on the branch exactly when it ends within them.
        self._identity_prefixes = [_identity_prefix(positions) for positions in branches]
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
            return matching_acknowledgements(
                self.entries, self.prefixes, acknowledgements, self.template["format"], self._index()
            )
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
            return next_chunk(self.template, self.entries, start, self.last_anchor, fork, self._index())
        # Earlier receipts remain useful for rewinds, but validating each one
        # repeats whole-branch parsing before reaching the furthest safe prefix.
        ordered_acknowledgements = sorted(
            acknowledgements,
            key=lambda ack: ack["end"] if ack.get("branch_end") is None else ack["branch_end"],
            reverse=True,
        )
        for number, (positions, hashes) in enumerate(zip(self.positions, self.hashes, strict=True)):
            branch = self._branches[number]
            start = 0
            anchor = None
            for ack in ordered_acknowledgements:
                branch_end = ack.get("branch_end")
                if branch_end is None:
                    branch_end = ack["end"]
                    if type(branch_end) is int and branch_end >= 0:
                        matches = branch_end <= self._identity_prefixes[number]
                    else:
                        matches = positions[:branch_end] == list(range(branch_end))
                else:
                    matches = branch_end <= len(hashes) and hashes[branch_end - 1] == ack.get("branch_prefix")
                if (
                    matches
                    and start < branch_end <= len(branch)
                    and (
                        branch_end == len(branch)
                        or _claude_acknowledgement_is_safe(branch, branch_end, self._branch_index(number))
                    )
                ):
                    start, anchor = branch_end, ack["anchor"]
                    break
            self.last_anchor = anchor
            if start == len(branch):
                continue
            chunk = next_chunk(self.template, branch, start, anchor, True, self._branch_index(number))
            chunk.branch_end = chunk.end
            chunk.branch_prefix = hashes[chunk.end - 1]
            chunk.end = positions[chunk.end - 1] + 1
            return chunk
        return None

    def _index(self) -> ClaudeSplitIndex | CodexScanIndex | CopilotSplitIndex | None:
        """The unbranched snapshot's boundary index, built once; None for formats without one."""
        if self._linear_index_due:
            if self.template["format"] == "codex-jsonl":
                self._linear_index = CodexScanIndex(self.entries)
            elif self.template["format"] == "copilot-events-jsonl":
                self._linear_index = CopilotSplitIndex(self.entries)
            else:
                self._linear_index = ClaudeSplitIndex(self.entries, self._linear_walk)
            self._linear_index_due = False
        self._linear_walk = None
        return self._linear_index

    def _branch_index(self, number: int) -> ClaudeSplitIndex:
        index = self._branch_indexes[number]
        if index is None:
            index = self._branch_indexes[number] = ClaudeSplitIndex.build(self._branches[number])
        return index


def _identity_prefix(positions: list[int]) -> int:
    """The length of the longest prefix of ``positions`` that reads 0, 1, 2, ..."""
    length = 0
    while length < len(positions) and positions[length] == length:
        length += 1
    return length


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
        elif self.refusal_key(self.chunk) == self.blocked_body:
            return None
        return self.chunk

    def refusal_key(self, chunk: Chunk) -> str:
        """Identify the chunk by what the server's refusal depends on.

        The body itself would not do: its template carries the transcript's last
        timestamp, so a refused chunk would look new, and be sent again, on every
        pass after the transcript grows. The range, the content hash of every
        entry up to its end, the anchor and the fork flag stay put until one of
        them changes the request in a way the server could judge differently.
        Keys stored in the older whole-body format never match, so the chunk
        they blocked is sent once more and then blocked under this key.
        """
        identity = {
            "start": chunk.start,
            "end": chunk.end,
            "prefix": self.plan.prefixes[chunk.end - 1],
            "branch_end": chunk.branch_end,
            "branch_prefix": chunk.branch_prefix,
            "anchor": chunk.anchor,
            "fork": chunk.fork,
        }
        return hashlib.sha256(encode(identity)).hexdigest()

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

    def reject(
        self, missing_anchor: bool, content_refusal: bool, reason: str | None = None
    ) -> Literal["retry", "stop", "raise"]:
        """Restart once for missing state; fork once onto an occupied parent; else suppress a refused request.

        ``reason`` is the server's refusal message (``anchor_not_leaf`` and so on),
        or None when the caller has none. ``anchor_not_leaf`` means the server
        already stores a different child under the chunk's first new message,
        for example content past the last acknowledgement whose receipt was
        lost, and the source then continued from an earlier message. Sending
        the same anchored chunk with ``fork`` stores the continuation as a
        branch, as a whole-file upload would; ``accept`` keeps forking until the
        upload reaches the end of the snapshot. A chunk already sent with
        ``fork`` is suppressed instead, so each chunk gets at most one such retry.
        """
        assert self.chunk is not None
        if missing_anchor and not self.restarted:
            self.acknowledgements = []
            self.blocked_body = None
            self.forking = False
            self.restarted = True
            return "retry"
        if content_refusal and reason == "anchor_not_leaf" and self.chunk.anchor is not None and not self.chunk.fork:
            self.blocked_body = None
            self.forking = True
            return "retry"
        if content_refusal:
            self.blocked_body = self.refusal_key(self.chunk)
            return "stop"
        return "raise"

    def to_dict(self) -> dict[str, Any]:
        return {
            "acknowledgements": self.acknowledgements,
            "blocked_body": self.blocked_body,
            "forking": self.forking,
        }
