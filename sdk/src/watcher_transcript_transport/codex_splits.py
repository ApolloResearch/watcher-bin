"""Answer the upload planner's Codex boundary questions for a whole rollout from two scans.

The planner (`watcher_transcript_transport.incremental`) needs to know where a
rollout's call cycles are complete: over the whole rollout, to check its saved
receipts on every step, and over each request's window (its start up to the
next compaction). Each answer is a call-cycle scan
(`codex.scan_codex_call_cycles`) of everything it covers, so planning a long
first upload request by request is quadratic in the rollout's length.

`CodexScanIndex` scans the rollout once per flag (`codex.CodexCallCycleScan`),
recording the scan's state before every entry (`CallCycleTrace`). A window
scan reaches the same decisions as the whole-rollout scan from the first entry
where both are in a new scan's state, so it scans only until then and takes the
rest from the record, and only the ends the planner can choose from are listed.
The context a request after the start of the rollout carries is looked up per
field instead of refolding everything before it.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right

from watcher_transcript_transport.codex import CodexCallCycles, CodexCallCycleScan
from watcher_transcript_transport.upload import JsonEntry

_CONTEXT_FIELDS = ("model", "user_instructions", "developer_instructions")


def is_resetting_compaction(entry: JsonEntry) -> bool:
    """A compaction after which Codex's parser starts a new window (see ``scan_codex_call_cycles``)."""
    return (
        entry.get("type") == "compacted"
        and isinstance(entry.get("payload"), dict)
        and (entry["payload"].get("replacement_history") is not None or bool(entry["payload"].get("message")))
    )


class CallCycleTrace:
    """A whole-rollout `scan_codex_call_cycles`'s state before each entry, for reuse by later questions.

    Index ``p`` runs over ``0..len(entries)``. ``fresh[p]`` says the scan's
    state before entry ``p`` is the state a new scan starts in (nothing
    pending, no assistant message open, cut at ``p``), so a scan of any
    window that reaches that state at ``p`` decides everything after ``p``
    as this one did. ``boundary_count[p]`` is how many boundaries it had
    recorded before entry ``p``, and ``complete_after[p]`` its
    ``complete_until`` for the first ``p`` entries.
    """

    __slots__ = ("fresh", "boundary_count", "complete_after")

    def __init__(self) -> None:
        self.fresh = bytearray()
        self.boundary_count: list[int] = []
        self.complete_after: list[int] = []

    def record(self, scan: CodexCallCycleScan) -> None:
        """Append the state ``scan`` is in before its next entry."""
        self.fresh.append(_is_fresh(scan))
        self.boundary_count.append(len(scan.boundaries))
        self.complete_after.append(scan.complete_until)


def _is_fresh(scan: CodexCallCycleScan) -> bool:
    """Whether ``scan`` is in the state a new scan starts in, relative to the entries it has seen."""
    return not scan.pending_openings and not scan.assistant_pending and scan.complete_until == scan.count


def _scan_call_cycles(
    entries: list[JsonEntry],
    allow_trailing_assistant_output: bool,
    start: int,
    stop: int,
    trace: CallCycleTrace | None,
    rejoin: CallCycleTrace | None,
) -> tuple[CodexCallCycles, int | None]:
    """Scan ``entries[start:stop]`` as a rollout of its own, with indices relative to ``start``.

    ``trace``, for a whole-rollout scan, records the state before every entry.
    ``rejoin``, the trace of a whole-rollout scan with the same flag, makes the
    scan stop at the first entry after ``start`` where both scans are fresh,
    returning what it found so far and that entry's position: from there the
    two make the same decisions, so the caller can take the rest from the
    trace. The position is None when the scan ran to ``stop``.
    """
    scan = CodexCallCycleScan(allow_trailing_assistant_output=allow_trailing_assistant_output)
    for position in range(start, stop):
        if trace is not None:
            trace.record(scan)
        elif rejoin is not None and scan.count and rejoin.fresh[position] and _is_fresh(scan):
            return CodexCallCycles(scan.complete_until, scan.interrupted_openings, scan.boundaries), position
        scan.feed(entries[position])
    if trace is not None:
        trace.record(scan)
    return CodexCallCycles(scan.complete_until, scan.interrupted_openings, scan.boundaries), None


class CodexScanIndex:
    """Every call-cycle question the planner asks about one rollout snapshot, answered from two scans.

    Each method returns exactly what the planner's own reads would, for the
    list the index was built from (`covers`), and only as much as the planner
    uses. When building fails on an unexpected entry, ``valid`` is false and
    the planner scans as before, which then fails the same way.
    """

    __slots__ = (
        "entries",
        "count",
        "valid",
        "safe_ends",
        "_strict",
        "_strict_trace",
        "_trailing_trace",
        "_resets",
        "_session_meta_index",
        "_context_fields",
    )

    def __init__(self, entries: list[JsonEntry]) -> None:
        self.entries = entries
        self.count = len(entries)
        self._strict_trace = CallCycleTrace()
        self._trailing_trace = CallCycleTrace()
        try:
            self._strict = _scan_call_cycles(entries, False, 0, self.count, self._strict_trace, None)[0]
            trailing = _scan_call_cycles(entries, True, 0, self.count, self._trailing_trace, None)[0]
            self._resets = [index for index, entry in enumerate(entries) if is_resetting_compaction(entry)]
            self._session_meta_index = next(
                (index for index, entry in enumerate(entries) if entry.get("type") == "session_meta"), None
            )
            self._context_fields = _context_fields(entries)
        except Exception:  # noqa: BLE001
            # The planner's own scans meet the same entry and fail as they always did.
            self.valid = False
            return
        self.valid = True
        # Where the planner may resume: the strict scan's boundaries, the
        # trailing scan's last complete point, and the end of the rollout.
        self.safe_ends = {*self._strict.boundaries, trailing.complete_until, self.count}

    def covers(self, entries: list[JsonEntry]) -> bool:
        """Whether this index is valid and was built for this exact list, unchanged in length."""
        return self.valid and entries is self.entries and len(entries) == self.count

    def prefix_complete_until(self, end: int) -> int:
        """``scan_codex_call_cycles(entries[:end], allow_trailing_assistant_output=True).complete_until``."""
        return self._trailing_trace.complete_after[end]

    def next_reset_after(self, start: int) -> int:
        """The first resetting compaction after ``start``, or the end of the rollout: a request's window end."""
        found = bisect_right(self._resets, start)
        return self._resets[found] if found < len(self._resets) else self.count

    def is_reset(self, position: int) -> bool:
        found = bisect_left(self._resets, position)
        return found < len(self._resets) and self._resets[found] == position

    def candidates(self, start: int, stop: int, limit: int) -> list[int]:
        """The request ends ``next_chunk`` reads for a window, ascending: those up to ``limit``, then the next one.

        The window ``entries[start:stop]``'s ends are its strict scan's
        boundaries, its trailing scan's complete point and, when ``stop`` is
        the end of the rollout, ``stop`` itself, as positions after ``start``.
        ``next_chunk`` tries those up to ``limit`` and at most the first one
        past it (a Codex window is always safe, so that one is either taken or
        too large), so the rest of a long window is never listed. Requires
        ``0 <= start < stop <= count``.

        A window that starts where the whole scan is in a new scan's state
        repeats the whole scan, except that only the whole scan records
        ``start`` itself before a compaction there (dropped as not after
        ``start``). Any other window is scanned until it rejoins the whole
        scan, and the record supplies the rest.
        """
        strict_trace, boundaries = self._strict_trace, self._strict.boundaries
        ends = {start + self._trailing_complete_until(start, stop)}
        if stop == self.count:
            ends.add(stop)
        low = high = strict_trace.boundary_count[stop]
        if strict_trace.fresh[start]:
            low = strict_trace.boundary_count[start]
        else:
            head, rejoined = _scan_call_cycles(self.entries, False, start, stop, None, strict_trace)
            ends.update(start + boundary for boundary in head.boundaries)
            if rejoined is not None:
                low = strict_trace.boundary_count[rejoined]
        # The whole scan's boundaries are recorded in ascending order.
        cut = bisect_right(boundaries, limit, low, high)
        listed = sorted({end for end in ends if start < end <= limit}.union(boundaries[low:cut]) - {start})
        beyond = [end for end in ends if end > limit]
        if cut < high:
            beyond.append(boundaries[cut])
        return [*listed, min(beyond)] if beyond else listed

    def _trailing_complete_until(self, start: int, stop: int) -> int:
        """``scan_codex_call_cycles(entries[start:stop], allow_trailing_assistant_output=True).complete_until``."""
        trace = self._trailing_trace
        if trace.fresh[start]:
            return trace.complete_after[stop] - start
        head, rejoined = _scan_call_cycles(self.entries, True, start, stop, None, trace)
        return head.complete_until if rejoined is None else trace.complete_after[stop] - start

    def session_meta_before(self, start: int) -> JsonEntry | None:
        """The rollout's first ``session_meta`` entry, if it comes before ``start``."""
        index = self._session_meta_index
        return self.entries[index] if index is not None and index < start else None

    def context_before(self, start: int) -> dict[str, str]:
        """``fold_context(entries[:start])``: the last nonempty value of each field, in first-seen order."""
        context: dict[str, str] = {}
        for field, positions, values in self._context_fields:
            found = bisect_left(positions, start)
            if found:
                context[field] = values[found - 1]
        return context


def _context_fields(entries: list[JsonEntry]) -> list[tuple[str, list[int], list[str]]]:
    """Each context field's nonempty settings as (field, positions, values), fields in first-seen order.

    ``fold_context`` adds a field to its result the first time it sees it, so
    the order fields first appear in the rollout is the order of the dict it
    builds, which is part of the request bytes.
    """
    settings: dict[str, tuple[list[int], list[str]]] = {}
    for index, entry in enumerate(entries):
        if entry.get("type") == "turn_context" and isinstance(entry.get("payload"), dict):
            for field in _CONTEXT_FIELDS:
                value = entry["payload"].get(field)
                if isinstance(value, str) and value:
                    positions, values = settings.setdefault(field, ([], []))
                    positions.append(index)
                    values.append(value)
    return [(field, positions, values) for field, (positions, values) in settings.items()]
