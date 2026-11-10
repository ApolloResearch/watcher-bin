"""Claude Code transcript boundaries shared by Watcher ingestion clients.

Claude transcripts are UUID trees rather than simple chronological streams.
These functions reproduce the server parser's stored-message ordering and
identify suffixes or partial tool cycles that cannot be uploaded independently.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import deque
from datetime import datetime, timezone
from functools import lru_cache
from typing import TYPE_CHECKING, Any, cast

from watcher_transcript_transport.upload import JsonEntry, shared_result

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

__all__ = [
    "TailTrimScan",
    "current_trajectory",
    "current_trajectory_groups",
    "delta_needs_full_upload",
    "live_compaction_start",
    "trim_incomplete_tail",
]


def trim_incomplete_tail(
    entries: list[JsonEntry],
    *,
    allow_trailing_assistant_text: bool,
) -> list[JsonEntry]:
    """Trim a Claude Code suffix that ends inside a tool-use/result cycle.

    ``allow_trailing_assistant_text`` is true for Stop-style events, where a
    text-only assistant tail is complete, and false for mid-turn events that
    may have observed the transcript while Claude was still writing it.
    """
    if not entries:
        return entries

    scan = TailTrimScan(allow_trailing_assistant_text=allow_trailing_assistant_text)
    for entry in entries:
        scan.feed(entry)
    if scan.complete_until >= len(entries):
        return entries
    return entries[: scan.complete_until]


class TailTrimScan:
    """`trim_incomplete_tail`'s scan as a fold that can resume where it stopped.

    Feed entries in file order; ``complete_until`` is then the length of the
    prefix `trim_incomplete_tail` would keep from the entries fed so far. A
    reader that only appends to a transcript can keep one scan and feed it new
    entries instead of rescanning the file, and `copy` lets it try entries it
    may not keep (an unterminated last line) without disturbing the original.
    """

    __slots__ = ("allow_trailing_assistant_text", "complete_until", "count", "pending_tool_use_ids")

    allow_trailing_assistant_text: bool
    complete_until: int
    count: int
    pending_tool_use_ids: set[str]

    def __init__(self, *, allow_trailing_assistant_text: bool) -> None:
        self.allow_trailing_assistant_text = allow_trailing_assistant_text
        self.complete_until = 0
        self.count = 0
        self.pending_tool_use_ids = set()

    def copy(self) -> TailTrimScan:
        """An independent scan at the same position."""
        other = TailTrimScan(allow_trailing_assistant_text=self.allow_trailing_assistant_text)
        other.complete_until = self.complete_until
        other.count = self.count
        other.pending_tool_use_ids = set(self.pending_tool_use_ids)
        return other

    def feed(self, entry: JsonEntry) -> None:
        """Advance past one entry."""
        index = self.count
        self.count += 1
        message_type = entry.get("type", "")

        if message_type in ("progress", "file-history-snapshot"):
            return

        if message_type == "assistant":
            message = entry.get("message", {})
            content = message.get("content", []) if isinstance(message, dict) else []
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        self.pending_tool_use_ids.add(block.get("id", ""))
            if self.allow_trailing_assistant_text and not self.pending_tool_use_ids:
                self.complete_until = index + 1
            return

        if message_type == "user":
            message = entry.get("message", {})
            content = message.get("content", []) if isinstance(message, dict) else []
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        self.pending_tool_use_ids.discard(block.get("tool_use_id", ""))

        if not self.pending_tool_use_ids:
            self.complete_until = index + 1


def _queued_command_prompt(entry: JsonEntry) -> str | list[JsonEntry] | None:
    """Return the human message carried by a queued-command attachment."""
    if entry.get("type") != "attachment":
        return None
    attachment = entry.get("attachment")
    if not isinstance(attachment, dict) or attachment.get("type") != "queued_command":
        return None
    prompt = attachment.get("prompt")
    if not prompt or not isinstance(prompt, str | list):
        return None
    return prompt


def _text_blocks_key(content: list[Any]) -> tuple[str, ...]:
    """Return the ordered non-empty text of a content-block list."""
    return tuple(
        block["text"]
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
        and block["text"]
    )


def _user_entry_text_key(entry: JsonEntry) -> tuple[str, ...]:
    """Return the ordered text content of a Claude ``user`` entry."""
    if entry.get("type") != "user":
        return ()
    message = entry.get("message")
    if not isinstance(message, dict):
        return ()
    content = message.get("content")
    if isinstance(content, str):
        return (content,) if content else ()
    if not isinstance(content, list):
        return ()
    return _text_blocks_key(content)


def _prompt_text_key(prompt: str | list[JsonEntry]) -> tuple[str, ...]:
    """Return the ordered text content of a queued-command prompt."""
    if isinstance(prompt, str):
        return (prompt,)
    return _text_blocks_key(prompt)


def _drop_redelivered_queued_commands(chain: list[JsonEntry]) -> list[JsonEntry]:
    """Drop queued-command attachments later redelivered as ``user`` entries."""
    dropped = {command for command, _ in _queued_command_redeliveries(chain)}
    return [entry for index, entry in enumerate(chain) if index not in dropped]


def _queued_command_redeliveries(chain: list[JsonEntry]) -> list[tuple[int, int]]:
    """Pair each redelivered queued command with the ``user`` entry that redelivers it, as chain positions.

    A command waits until the next assistant entry; the oldest waiting command
    with the same text is the one a ``user`` entry redelivers.
    """
    pending: dict[tuple[str, ...], list[int]] = {}
    pairs: list[tuple[int, int]] = []
    for index, entry in enumerate(chain):
        if entry.get("type") == "assistant":
            pending.clear()
            continue
        prompt = _queued_command_prompt(entry)
        if prompt is not None:
            key = _prompt_text_key(prompt)
            if key:
                pending.setdefault(key, []).append(index)
            continue
        matches = pending.get(_user_entry_text_key(entry))
        if matches:
            pairs.append((matches.pop(0), index))
    return pairs


# Room for every timestamp of a session of a quarter of a million entries. Planning reads each timestamp
# many times in file order, so a cache smaller than the file evicts every one before it is read again.
_TIMESTAMP_CACHE_SIZE = 1 << 18


def _parse_event_timestamp(entry: JsonEntry) -> float | None:
    timestamp = entry.get("timestamp")
    return _parse_timestamp_string(timestamp) if isinstance(timestamp, str) else None


@lru_cache(maxsize=_TIMESTAMP_CACHE_SIZE)
def _parse_timestamp_string(timestamp: str) -> float | None:
    """``_parse_event_timestamp`` for one string, cached: every walk sorts siblings by it, and a cut check walks often."""
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def release_parse_caches() -> None:
    """Empty the timestamp parse caches, which otherwise keep up to 262,144 strings each.

    Full, the two hold about 90 MB, counting the strings they keep alive. The upload loop calls this after an upload completes, as a best-effort release of
    these bounded process-wide caches: an attempt that ends early, or any other
    parse, can leave entries behind until the next completed upload.
    """
    _parse_timestamp_string.cache_clear()
    _parse_time_order_key.cache_clear()


def _entry_walk_key(entry: JsonEntry) -> tuple[bool, float]:
    """Sibling ordering for every tree walk: timestamped entries first, oldest first.

    Entries without a parseable timestamp sort after timestamped siblings.
    Equal keys retain their input order when used with Python's stable sort.
    """
    timestamp = _parse_event_timestamp(entry)
    return timestamp is None, timestamp or 0.0


def _time_order_key(entry: JsonEntry) -> tuple[bool, float]:
    """Mirror of the server's ``_time_order_key``: an entry's age for comparing across branches.

    A timestamp without a zone is read as UTC, so entries from different
    branches always compare.
    """
    timestamp = entry.get("timestamp")
    return _parse_time_order_key(timestamp) if isinstance(timestamp, str) else (True, 0.0)


@lru_cache(maxsize=_TIMESTAMP_CACHE_SIZE)
def _parse_time_order_key(timestamp: str) -> tuple[bool, float]:
    """``_time_order_key`` for one timestamp string, cached: a holding walk compares every entry's age."""
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return (True, 0.0)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)  # noqa: UP017 - the Remote Collector runs this module on Python 3.10
    return (False, parsed.timestamp())


def _carries_tool_result(entry: JsonEntry) -> bool:
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") == "tool_result" for block in content
    )


def _is_typed_prompt(entry: JsonEntry) -> bool:
    """Mirror of the server's ``_is_typed_prompt``: a prompt with text, or a queued-command attachment.

    It reads only the entry, so a piece of a split upload answers as the whole file does.
    """
    if _queued_command_prompt(entry) is not None:
        return True
    return (
        bool(_user_entry_text_key(entry)) and not _is_compaction_segment_root(entry) and not _carries_tool_result(entry)
    )


# `_HoldAges` of an entry with nothing stamped when written at or below it: after every timestamp.
_NO_HOLD_AGE = (True, 0.0)


def _written_age(entry: JsonEntry) -> tuple[bool, float]:
    """Mirror of the server's ``_written_age``: the age of a reply, tool result or typed ``user`` prompt."""
    entry_type = entry.get("type")
    if (
        entry_type == "assistant"
        or (entry_type == "user" and _carries_tool_result(entry))
        or (entry_type == "user" and _is_typed_prompt(entry))
    ):
        return _time_order_key(entry)
    return _NO_HOLD_AGE


# Mirror of the server's ``_Clock``: per uuid, the newest age it counts as no older than and the entry setting
# it (its newest ancestor stamped when written, or a newer typed prompt written before it).
_Clock = dict[str, tuple[tuple[bool, float], str]]


def _record_clock(clock: _Clock, parent: JsonEntry, children: list[JsonEntry]) -> None:
    """Mirror of the server's ``_record_clock``: note each new child's newest ancestor stamped when written."""
    above = clock.get(parent["uuid"])
    age = _written_age(parent)
    if not age[0] and (above is None or above[0] < age):
        above = (age, parent["uuid"])
    if above is not None:
        for child in children:
            clock.setdefault(child["uuid"], above)


def _record_prompts_written_before(clock: _Clock, entries: Iterable[JsonEntry]) -> None:
    """Mirror of the server's ``_record_prompts_written_before``: no entry is older than a prompt written before it."""
    newest: tuple[tuple[bool, float], str] | None = None
    seen: set[str] = set()
    for entry in entries:
        uid = entry["uuid"]
        if uid in seen:
            continue
        seen.add(uid)
        if newest is not None:
            above = clock.get(uid)
            if above is None or above[0] < newest[0]:
                clock[uid] = newest
        key = _time_order_key(entry)
        if not key[0] and (newest is None or newest[0] < key) and _is_typed_prompt(entry):
            newest = (key, uid)


def _age_on_clock(entry: JsonEntry, clock: _Clock) -> tuple[bool, float]:
    """Mirror of the server's ``_age_on_clock``: ``_written_age``, no older than what ``clock`` dates the entry by."""
    age = _written_age(entry)
    above = clock.get(entry["uuid"])
    return above[0] if above is not None and age < above[0] else age


class _HoldAges:
    """Mirror of the server's ``_EntryTreeWalk.hold_ages`` for one selection's walk, each uuid answered once.

    Calling it with an entry gives the `_time_order_key` of the oldest entry
    at or below it stamped when written (``_written_age``), through only the
    children the selection walks (``walked``: walk order, abandoned rewind
    branches and compaction summaries left out), or ``_NO_HOLD_AGE``. The
    first call answers every uuid, climbing from each parent in ``children``'s
    order, as the server does, so a cycle through duplicate uuids (where a
    uuid met again on its own path adds nothing) resolves the same on both
    sides whichever entry is asked first. An entry counts as no older than
    its newest ancestor stamped when written or a typed prompt written before
    it (``_age_on_clock``, by ``clock``).
    """

    __slots__ = ("_below", "_children", "_clock", "_walked")

    def __init__(
        self,
        children: dict[str, list[JsonEntry]],
        walked: Callable[[str], list[JsonEntry]],
        below: dict[str, tuple[bool, float]],
        clock: _Clock,
    ) -> None:
        self._children = children
        self._walked = walked
        self._clock = clock
        # The memo: each parent uuid's age from strictly below it, filled on the first call.
        self._below = below

    def __call__(self, entry: JsonEntry) -> tuple[bool, float]:
        if _is_compaction_segment_root(entry):
            return _NO_HOLD_AGE
        if not self._below:
            self._fill()
        return min(_age_on_clock(entry, self._clock), self._below.get(entry["uuid"], _NO_HOLD_AGE))

    def _fill(self) -> None:
        below, clock = self._below, self._clock
        walked: dict[str, list[JsonEntry]] = {}
        on_path: set[str] = set()
        for parent in self._children:
            stack: list[tuple[str, bool]] = [(parent, False)]
            while stack:
                node, finished = stack.pop()
                if finished:
                    below[node] = min(
                        (
                            min(_age_on_clock(child, clock), below.get(child["uuid"], _NO_HOLD_AGE))
                            for child in walked[node]
                        ),
                        default=_NO_HOLD_AGE,
                    )
                    on_path.discard(node)
                elif node not in below and node not in on_path:
                    on_path.add(node)
                    walked[node] = self._walked(node)
                    stack.append((node, True))
                    stack.extend((child["uuid"], False) for child in walked[node])


class _WalkFrontier:
    """Mirror of the server's ``_WalkFrontier``: breadth-first, optionally holding late prompts back.

    Each prompt in ``prompts_to_hold`` (by uuid) is held back when reached
    while a waiting entry is older by its ``hold_age``, or an older prompt is
    held, with its subtree, until no waiting entry is; held
    prompts are released oldest first, a held redelivery as old as its queued
    command (``typed_at``), and none overtakes an older one still held. A
    waiting entry with nothing timestamped that counts at or below it never
    holds a prompt back. A held queued command's redelivering child is emitted
    right after the command. The walk extends the frontier with an entry's
    children right after popping it.
    """

    __slots__ = (
        "_ages",
        "_gone",
        "_held",
        "_hold_age",
        "_holds",
        "_next",
        "_queue",
        "_reached",
        "_released",
        "_to_hold",
        "_typed_at",
        "held_entries",
    )

    def __init__(
        self,
        root: JsonEntry,
        *,
        prompts_to_hold: frozenset[str],
        hold_age: Callable[[JsonEntry], tuple[bool, float]],
        typed_at: dict[str, tuple[bool, float]],
    ) -> None:
        self._to_hold = prompts_to_hold
        self._typed_at = typed_at
        self._holds = bool(prompts_to_hold)
        self._hold_age = hold_age
        # Every prompt this frontier held back, in the order it held them.
        self.held_entries: list[JsonEntry] = []
        self._queue: deque[tuple[int, JsonEntry]] = deque()
        self._ages: list[tuple[tuple[bool, float], int]] = []
        self._gone: set[int] = set()
        self._held: list[tuple[tuple[bool, float], int, JsonEntry]] = []
        self._reached = 0
        # The held prompt the last pop released, whose redelivering child is emitted next (``_next``).
        self._released: JsonEntry | None = None
        self._next: JsonEntry | None = None
        self.extend([root])

    def __bool__(self) -> bool:
        return bool(self._queue) or bool(self._held) or self._next is not None

    # heapq is imported only on the holding path, which keeps it out of the module set
    # hook startup loads (see the hook import budget test).

    def _oldest_waiting(self) -> tuple[bool, float] | None:
        import heapq

        while self._ages and self._ages[0][1] in self._gone:
            self._gone.discard(heapq.heappop(self._ages)[1])
        return self._ages[0][0] if self._ages else None

    def pop(self) -> JsonEntry:
        if not self._holds:
            return self._queue.popleft()[1]
        import heapq

        self._released = None
        if self._next is not None:
            entry, self._next = self._next, None
            return entry
        while True:
            oldest = self._oldest_waiting() if self._held else None
            if self._held and (oldest is None or oldest >= self._held[0][0]):
                self._released = heapq.heappop(self._held)[2]
                return self._released
            reached, entry = self._queue.popleft()
            self._gone.add(reached)
            key = _time_order_key(entry)
            if not key[0] and entry["uuid"] in self._to_hold:
                key = self._typed_at.get(entry["uuid"], key)
                oldest = self._oldest_waiting()
                # Behind an older held prompt too, so held prompts always leave oldest first.
                if (oldest is not None and oldest < key) or (self._held and self._held[0][0] < key):
                    heapq.heappush(self._held, (key, reached, entry))
                    self.held_entries.append(entry)
                    continue
            return entry

    def extend(self, entries: list[JsonEntry]) -> None:
        released, self._released = self._released, None
        command = _queued_command_prompt(released) if released is not None else None
        key = _prompt_text_key(command) if command is not None else ()
        for entry in entries:
            if key and self._next is None and entry.get("type") == "user" and _user_entry_text_key(entry) == key:
                self._next = entry
                continue
            self._queue.append((self._reached, entry))
            if self._holds:
                import heapq

                heapq.heappush(self._ages, (self._hold_age(entry), self._reached))
            self._reached += 1


def _late_prompt_witnesses(chain: list[JsonEntry], clock: _Clock) -> list[tuple[int, int]]:
    """Mirror of the server's ``_inversion_prompts``, with where each late prompt is seen to be late.

    Returns ``(prompt, witness)`` chain positions, prompts ascending: each
    typed prompt that an assistant message or tool result older than the
    prompt follows later in its compaction segment, and the first such entry
    after it. A ``user`` entry redelivering a queued command is as old as the
    command when that is older, since the command carries the time it was
    typed. A reply or tool result is no older than its newest ancestor stamped
    when written or a typed prompt written before it (``_age_on_clock``, by
    ``clock``). A slice of ``chain`` that keeps every redelivery with
    its command flags the prompt exactly when it holds both positions, which
    the cut proofs rely on (facts 6, 9 and 10 in `claude_splits.ClaudeSplitIndex`).
    """
    witnesses = _first_older_work(chain, {}, clock)
    if witnesses:
        # Rare, so the redeliveries' text keys are only built once some prompt looks late.
        late = {prompt for prompt, _ in witnesses}
        typed_at = {
            redelivery: min(_time_order_key(chain[command]), _time_order_key(chain[redelivery]))
            for command, redelivery in _queued_command_redeliveries(chain)
            if redelivery in late
        }
        if typed_at:
            witnesses = _first_older_work(chain, typed_at, clock)
    return witnesses


def _first_older_work(
    chain: list[JsonEntry], typed_at: dict[int, tuple[bool, float]], clock: _Clock
) -> list[tuple[int, int]]:
    """``_late_prompt_witnesses`` with each prompt as old as ``typed_at`` gives by position, else its own timestamp.

    One right-to-left pass keeps the replies and tool results that could
    still be the first older entry for some prompt to their left: each one
    hides every later candidate at least as old, so the kept ages fall from
    the nearest candidate outward, and the first older one is found by
    bisection.
    """
    witnesses: list[tuple[int, int]] = []
    ages: list[tuple[bool, float]] = []  # kept candidates, farthest (oldest) first
    positions: list[int] = []
    # Text is read last, and only once something older lies ahead, since building a prompt's key is the cost.
    for position in range(len(chain) - 1, -1, -1):
        entry = chain[position]
        entry_type = entry.get("type")
        if entry_type == "assistant" or (entry_type == "user" and _carries_tool_result(entry)):
            # ``_age_on_clock`` for an entry already known to be a reply or tool result.
            age = _time_order_key(entry)
            above = clock.get(entry["uuid"]) if clock else None
            if above is not None and age < above[0]:
                age = above[0]
            if not age[0]:
                while ages and ages[-1] >= age:
                    ages.pop()
                    positions.pop()
                ages.append(age)
                positions.append(position)
        elif ages and entry_type in ("user", "attachment"):
            if _is_compaction_segment_root(entry):
                ages.clear()
                positions.clear()
                continue
            age = typed_at.get(position) or _time_order_key(entry)
            # The entry carries no tool result and starts no compaction segment, so this is _is_typed_prompt.
            if (
                not age[0]
                and ages[0] < age
                and (_queued_command_prompt(entry) is not None or bool(_user_entry_text_key(entry)))
            ):
                # Imported only for a late prompt, which keeps bisect out of the modules hook startup loads.
                from bisect import bisect_left

                witnesses.append((position, positions[bisect_left(ages, age) - 1]))
    witnesses.reverse()
    return witnesses


def _redelivered_prompt_ages(chain: list[JsonEntry], prompts: frozenset[str]) -> dict[str, tuple[bool, float]]:
    """Mirror of the server's ``_redelivered_prompt_ages``: each of ``prompts`` redelivering an older command, its age."""
    return {
        chain[redelivery]["uuid"]: _time_order_key(chain[command])
        for command, redelivery in _queued_command_redeliveries(chain)
        if chain[redelivery]["uuid"] in prompts and _time_order_key(chain[command]) < _time_order_key(chain[redelivery])
    }


def _inversion_prompts(chain: list[JsonEntry], clock: _Clock) -> frozenset[str]:
    """Mirror of the server's ``_inversion_prompts``: the uuids of the late prompts in ``chain``.

    ``chain`` is one selection's walk output before queued-command deduplication, as on the server,
    and ``clock`` what its breadth-first walk recorded (``_record_clock``).
    """
    return frozenset(chain[prompt]["uuid"] for prompt, _ in _late_prompt_witnesses(chain, clock))


def _branch_head_message(
    branch_root: JsonEntry,
    children: dict[str, list[JsonEntry]],
    message_uuids: set[str],
) -> JsonEntry | None:
    """First message entry the chain walk would emit from this branch, or None.

    Use the same breadth-first traversal and timestamp-ordered siblings as the
    chain walk. A global timestamp sort could choose a different first prompt
    and incorrectly classify a fork as a rewind. Cycles are visited once.
    """
    queue = deque([branch_root])
    seen: set[str] = set()
    while queue:
        current = queue.popleft()
        uuid = current["uuid"]
        if uuid in seen:
            continue
        seen.add(uuid)
        if uuid in message_uuids:
            return current
        next_entries = [child for child in children.get(uuid, []) if child["uuid"] not in seen]
        next_entries.sort(key=_entry_walk_key)
        queue.extend(next_entries)
    return None


def _branch_last_activity(
    branch_root: JsonEntry,
    children: dict[str, list[JsonEntry]],
    message_uuids: set[str],
    segments_by_owner: dict[str, list[JsonEntry]],
    memo: dict[str, float | None],
) -> float | None:
    """Newest message timestamp on this branch, including its owned segments, or None.

    Rewind selection keeps the branch written to most recently, not the branch
    that started latest. Include compaction segments attached by
    ``segments_by_owner`` (owner-leaf UUID to continuing segment roots), even
    though those segments are separate roots in the physical transcript.
    """
    if branch_root["uuid"] in memo:
        return memo[branch_root["uuid"]]
    in_progress: set[str] = set()
    stack = [(branch_root, False)]
    while stack:
        current, expanded = stack.pop()
        uuid = current["uuid"]
        if uuid in memo or (not expanded and uuid in in_progress):
            continue
        below = [*children.get(uuid, []), *segments_by_owner.get(uuid, [])]
        if not expanded:
            in_progress.add(uuid)
            stack.append((current, True))
            stack.extend((child, False) for child in below if child["uuid"] not in memo)
            continue
        last = _parse_event_timestamp(current) if uuid in message_uuids else None
        for child in below:
            activity = memo.get(child["uuid"])
            if activity is not None and (last is None or activity > last):
                last = activity
        memo[uuid] = last
        in_progress.discard(uuid)
    return memo[branch_root["uuid"]]


def _drop_abandoned_rewind_branches(
    siblings: list[JsonEntry],
    children: dict[str, list[JsonEntry]],
    message_uuids: set[str],
    segments_by_owner: dict[str, list[JsonEntry]],
    activity_by_uuid: dict[str, float | None],
) -> list[JsonEntry]:
    """Filter a fork's children down to the live branch — the one the user continued.

    Only sibling branches whose first messages contain different user prompt
    text compete. Keep the contender with the newest activity and all siblings
    that do not compete. Same-prompt and non-user forks pass through unchanged.
    The client anchors deltas on the live chain's last leaf. A rewind forces a
    full upload, allowing the server to recover abandoned branches separately.
    """
    if len(siblings) < 2:
        return siblings
    heads = [_branch_head_message(sibling, children, message_uuids) for sibling in siblings]
    prompt_keys = [() if head is None else _user_entry_text_key(head) for head in heads]
    contenders = [i for i, key in enumerate(prompt_keys) if key]
    if len(contenders) < 2 or len({prompt_keys[i] for i in contenders}) < 2:
        return siblings

    survivor = contenders[0]
    survivor_activity = _branch_last_activity(
        siblings[survivor], children, message_uuids, segments_by_owner, activity_by_uuid
    )
    for i in contenders[1:]:
        activity = _branch_last_activity(siblings[i], children, message_uuids, segments_by_owner, activity_by_uuid)
        if survivor_activity is None or (activity is not None and activity >= survivor_activity):
            survivor = i
            survivor_activity = activity
    dropped = {i for i in contenders if i != survivor}
    return [sibling for i, sibling in enumerate(siblings) if i not in dropped]


def _climbs_to_root(
    uuid: str,
    entry_lookup: dict[str, JsonEntry],
    root_uuids: set[str],
    segment_root_uuid: str,
) -> bool:
    """Check whether an ancestry chain connects a segment to another known root.

    Return false for a missing parent, cycle, or path through
    ``segment_root_uuid``. The last case identifies replayed history within the
    segment, which must not be treated as a link to an earlier segment.
    """
    current = entry_lookup.get(uuid)
    seen: set[str] = set()
    while current is not None:
        current_uuid = current.get("uuid")
        if current_uuid == segment_root_uuid:
            return False
        if current_uuid in root_uuids:
            return True
        if not isinstance(current_uuid, str) or current_uuid in seen:
            return False
        seen.add(current_uuid)
        parent = current.get("parentUuid")
        current = entry_lookup.get(parent) if isinstance(parent, str) else None
    return False


def _segment_logical_parent(
    segment_root: JsonEntry,
    entry_lookup: dict[str, JsonEntry],
    root_uuids: set[str],
) -> str | None:
    """The in-file leaf a compaction segment continues from, or None for a base segment.

    Follow parent ancestry to a compaction boundary's ``logicalParentUuid``.
    Accept that leaf only when it connects to another root in this file. A
    missing, external, dangling, cyclic or self-contained link yields None,
    leaving the segment independent rather than attaching it to the wrong branch.
    """
    current: JsonEntry | None = segment_root
    seen: set[str] = set()
    while current is not None:
        back_link = current.get("logicalParentUuid")
        if isinstance(back_link, str) and back_link:
            root_uuid = segment_root["uuid"]
            return back_link if _climbs_to_root(back_link, entry_lookup, root_uuids, root_uuid) else None
        current_uuid = current.get("uuid")
        if not isinstance(current_uuid, str) or current_uuid in seen:
            return None
        seen.add(current_uuid)
        parent = current.get("parentUuid")
        current = entry_lookup.get(parent) if isinstance(parent, str) else None
    return None


def _segment_back_links(
    roots: list[JsonEntry],
    entry_lookup: dict[str, JsonEntry],
) -> dict[str, str]:
    """Segment-root uuid -> the pre-compaction leaf it continues from.

    A walk includes a segment root only once it has visited the named leaf, so
    a segment owned by an abandoned branch (whose leaf the live walk never
    reaches) stays off the live chain. Base segments (no resolvable back-link)
    are absent from the map and walked unconditionally.
    """
    root_uuids = {root["uuid"] for root in roots}
    return {
        root["uuid"]: back_link
        for root in roots
        if (back_link := _segment_logical_parent(root, entry_lookup, root_uuids)) is not None
    }


def _is_compaction_segment_root(root: JsonEntry) -> bool:
    """Recognize explicit summaries and the legacy continuation-prompt prefix.

    These roots continue earlier history and must not compete as rewritten
    first prompts when selecting a live branch.
    """
    if root.get("isCompactSummary"):
        return True
    key = _user_entry_text_key(root)
    return bool(key) and key[0].startswith("This session is being continued")


def _segments_by_owner(
    segment_back_links: dict[str, str],
    entry_lookup: dict[str, JsonEntry],
) -> dict[str, list[JsonEntry]]:
    """Invert ``segment_back_links``: owner-leaf uuid → the segment roots continuing from it.

    A segment hangs off its own root, unreachable through the ``children`` map, so
    ``_branch_last_activity`` needs this to fold a segment's activity into the
    branch that produced it.
    """
    by_owner: dict[str, list[JsonEntry]] = {}
    for segment_uuid, owner_leaf in segment_back_links.items():
        segment_root = entry_lookup.get(segment_uuid)
        if segment_root is not None:
            by_owner.setdefault(owner_leaf, []).append(segment_root)
    return by_owner


def _drop_abandoned_root_prompts(
    roots: list[JsonEntry],
    groups: list[str | None],
    children: dict[str, list[JsonEntry]],
    message_uuids: set[str],
    segments_by_owner: dict[str, list[JsonEntry]],
    activity_by_uuid: dict[str, float | None],
) -> list[JsonEntry]:
    """Drop the abandoned first-prompt roots when the first prompt was rewound.

    ``groups`` holds each root's rewind group (see ``_message_order``): ``""``
    for a parentless root, the uuid of the parentless entry atop its
    non-message ancestry otherwise (current Claude Code writes session-start
    hook attachments before the first prompt, and every rewound version names
    them as its parent), and None for a root above a parent missing from the
    file. Contenders are user-text roots of one group that are not compaction
    summaries and have different prompt text; every such group is a fork (a
    file can hold several trees, each with its own rewound first prompt). Keep
    each group's newest-activity contender and every non-contender root;
    dangling-parent and same-text roots remain as segments. The later walk
    uses ``segment_back_links`` to include compaction segments only after
    visiting the branch that owns them.
    """
    if len(roots) < 2:
        return roots
    prompt_keys = [
        _user_entry_text_key(root) if group is not None and not _is_compaction_segment_root(root) else ()
        for root, group in zip(roots, groups, strict=True)
    ]
    members_by_group: dict[str | None, list[int]] = {}
    for i, key in enumerate(prompt_keys):
        if key:
            members_by_group.setdefault(groups[i], []).append(i)
    abandoned_indices: set[int] = set()
    for contenders in members_by_group.values():
        if len(contenders) < 2 or len({prompt_keys[i] for i in contenders}) < 2:
            continue
        survivor = contenders[0]
        survivor_activity = _branch_last_activity(
            roots[survivor], children, message_uuids, segments_by_owner, activity_by_uuid
        )
        for i in contenders[1:]:
            activity = _branch_last_activity(roots[i], children, message_uuids, segments_by_owner, activity_by_uuid)
            if survivor_activity is None or (activity is not None and activity >= survivor_activity):
                survivor = i
                survivor_activity = activity
        abandoned_indices.update(i for i in contenders if i != survivor)
    return [root for i, root in enumerate(roots) if i not in abandoned_indices]


# Dependency-free for hook startup, like the records in ``upload``.
class _BranchSelection:  # noqa: B903
    """Forced rewind choices and the last base segment belonging to that version."""

    def __init__(self, choices: dict[str, str], root_limit: int | None) -> None:
        self.choices = choices
        self.root_limit = root_limit


class _LiveBranch:  # noqa: B903
    """The server parser's live branch of a Claude UUID tree, as the client replicates it.

    ``entries`` holds the selected conversation before queued-command
    redelivery deduplication. Keeping those attachments lets the server retain
    their source-ID aliases when a compaction refers to them. ``order`` is the
    deduplicated UUID sequence used by upload planning. ``abandons_branch``
    reports whether historical ingestion would also emit abandoned branches.
    """

    __slots__ = ("abandons_branch", "entries", "order", "visited", "alternatives")

    entries: list[JsonEntry]
    order: list[str]
    abandons_branch: bool

    def __init__(
        self, entries: list[JsonEntry], abandons_branch: bool, visited: set[str], alternatives: list[_BranchSelection]
    ) -> None:
        self.entries = entries
        self.order = [entry["uuid"] for entry in _drop_redelivered_queued_commands(entries)]
        self.abandons_branch = abandons_branch
        self.visited = visited
        self.alternatives = alternatives


class _WalkTree:  # noqa: B903
    """The tree a full walk built: what a proof about other pieces of the same file reuses.

    ``roots`` are every root the walk sorted, in walk order and before any
    rewind pruning; ``deferred`` says whether any compaction segment root had
    to wait for its owner leaf; ``summaries_moved`` says whether the chain was
    reordered to put compaction summaries back (``_place_compaction_summaries``).
    """

    __slots__ = (
        "entry_lookup",
        "message_uuids",
        "children",
        "roots",
        "segment_back_links",
        "deferred",
        "summaries_moved",
    )

    def __init__(
        self,
        entry_lookup: dict[str, JsonEntry],
        message_uuids: set[str],
        children: dict[str, list[JsonEntry]],
        roots: list[JsonEntry],
        segment_back_links: dict[str, str],
        deferred: bool,
        summaries_moved: bool,
    ) -> None:
        self.entry_lookup = entry_lookup
        self.message_uuids = message_uuids
        self.children = children
        self.roots = roots
        self.segment_back_links = segment_back_links
        self.deferred = deferred
        self.summaries_moved = summaries_moved


# Rounds of holding a walk may take before it stops with what it has (see _walk_chain).
MAX_HOLD_ROUNDS = 8


class _HoldRound:  # noqa: B903
    """One walk of a branch holding late prompts back, as the upload cut proofs read it.

    ``flagged`` are the late prompts found so far (see ``_inversion_prompts``),
    ``chain`` the messages this walk emitted, ``emitted`` the uuid of every
    entry it visited, in visiting order, and ``held`` the prompts it held back.
    """

    __slots__ = ("flagged", "chain", "emitted", "held")

    def __init__(self, flagged: frozenset[str]) -> None:
        self.flagged = flagged
        self.chain: list[JsonEntry] = []
        self.emitted: list[str] = []
        self.held: set[str] = set()


class _HeldWalk:  # noqa: B903
    """What a walk that held late prompts back did: its plain breadth-first chain, then each holding round."""

    __slots__ = ("breadth_first", "rounds")

    def __init__(self, breadth_first: list[JsonEntry], rounds: list[_HoldRound]) -> None:
        self.breadth_first = breadth_first
        self.rounds = rounds


class _ChainWalk:  # noqa: B903
    """One walk's message chain before queued-command deduplication (see ``_walk_chain``).

    ``tree`` is None when the walk returned early: no messages, or no root
    because every message has a message ancestor (a cycle). ``held`` is set
    when the walk held late prompts back (see ``_WalkFrontier``). ``clock`` is
    what the breadth-first walk recorded (``_record_clock``) when some prompt
    looked late by its entries' own timestamps, held back or not; the cut
    proofs need it either way.
    """

    __slots__ = ("chain", "abandons_branch", "visited", "alternatives", "tree", "held", "clock")

    def __init__(
        self,
        chain: list[JsonEntry],
        abandons_branch: bool,
        visited: set[str],
        alternatives: list[_BranchSelection],
        tree: _WalkTree | None,
        *,
        held: _HeldWalk | None = None,
        clock: _Clock | None = None,
    ) -> None:
        self.chain = chain
        self.abandons_branch = abandons_branch
        self.visited = visited
        self.alternatives = alternatives
        self.tree = tree
        self.held = held
        self.clock = clock

    def live_branch(self) -> _LiveBranch:
        return _LiveBranch(
            self.chain,
            self.abandons_branch,
            self.visited,
            self.alternatives,
        )


def _message_order(entries: list[JsonEntry]) -> list[str] | None:
    """Reproduce the server parser's live-branch message order from a Claude UUID tree.

    ``None`` means the raw tree cannot be ordered safely, and callers must use
    full ingestion rather than trusting an independently parsed suffix.
    """
    branch = _live_branch(entries)
    return None if branch is None else branch.order


def _current_compaction_boundaries(
    entries: list[JsonEntry], selected: list[JsonEntry], *, include_sidechains: bool
) -> list[JsonEntry]:
    """Keep compaction ownership stable after discarding historical summaries.

    A boundary marks one summary: its explicit anchor, otherwise the first
    claimant in file order. Removing an abandoned owner must not transfer its
    retained context to a live summary. Resolve ownership once over metadata,
    then pin surviving owners explicitly and clear other boundaries' retained
    context. No historical message contents are copied into the projection.
    """
    by_uuid = {entry["uuid"]: entry for entry in entries if entry.get("uuid")}
    boundaries = [
        entry for entry in entries if entry.get("type") == "system" and entry.get("subtype") == "compact_boundary"
    ]
    anchored: dict[str, JsonEntry] = {}
    for boundary in boundaries:
        boundary_metadata = boundary.get("compactMetadata")
        if not isinstance(boundary_metadata, dict):
            continue
        for key in ("preservedMessages", "preservedSegment"):
            section = boundary_metadata.get(key)
            if isinstance(section, dict) and isinstance(section.get("anchorUuid"), str):
                anchored[section["anchorUuid"]] = boundary
    summaries: dict[str, JsonEntry] = {}
    for entry in entries:
        if (
            entry.get("type") != "user"
            or not entry.get("uuid")
            or (entry.get("isSidechain") and not include_sidechains)
        ):
            continue
        parent = by_uuid.get(entry.get("parentUuid"))
        is_root = entry.get("parentUuid") is None or (
            parent is not None and parent.get("type") == "system" and parent.get("subtype") == "compact_boundary"
        )
        if entry.get("isCompactSummary") or (is_root and _is_compaction_segment_root(entry)):
            summaries[entry["uuid"]] = entry
    owners = {id(anchored[uuid]): uuid for uuid in reversed(summaries) if uuid in anchored}
    for uuid, entry in summaries.items():
        boundary = anchored.get(uuid) or by_uuid.get(entry.get("parentUuid"))
        if boundary is not None:
            owners.setdefault(id(boundary), uuid)
    selected_ids = {entry["uuid"] for entry in selected}
    result: list[JsonEntry] = []
    for boundary in boundaries:
        owner = owners.get(id(boundary))
        original = boundary.get("compactMetadata")
        metadata: dict[str, Any] = {}
        if owner in selected_ids and isinstance(original, dict):
            preserved = original.get("preservedMessages")
            segment = original.get("preservedSegment")
            if isinstance(preserved, dict) and isinstance(preserved.get("uuids"), list):
                metadata = {"preservedMessages": {"anchorUuid": owner, "uuids": preserved["uuids"]}}
            elif isinstance(segment, dict) and isinstance(segment.get("headUuid"), str):
                metadata = {"preservedSegment": {"anchorUuid": owner, "headUuid": segment["headUuid"]}}
        result.append({**boundary, "compactMetadata": metadata})
    return result


def current_trajectory(entries: list[JsonEntry], *, include_sidechains: bool = False) -> list[JsonEntry]:
    """Select the current conversation for grading, preserving native message facts.

    The result is an ordered conversation, not another JSONL tree: consumers
    must read its messages in the supplied order. Compaction boundary records
    precede the messages so native conversion can retain the same context
    markers as a full upload. Queued-command attachments remain until native
    conversion deduplicates them and records their replacement aliases.
    Message entries are borrowed without mutation; callers must treat them as
    read-only. Boundary metadata is copied to preserve summary ownership.
    Raises ``ValueError`` if the tree cannot be ordered safely.

    One tree walk selects the live continuation, including parallel results
    and owned compaction segments. It never reconstructs the shared prefix
    separately for each abandoned branch.
    Set ``include_sidechains`` only for a dedicated child transcript whose
    native identity has been validated; root conversations exclude sidechains.
    """
    branch = _live_branch(entries, include_sidechains=include_sidechains)
    if branch is None:
        raise ValueError("Cannot select a current trajectory from a cyclic transcript")
    boundaries = _current_compaction_boundaries(entries, branch.entries, include_sidechains=include_sidechains)
    return [*boundaries, *branch.entries]


def current_trajectory_groups(entries: list[JsonEntry], *, include_sidechains: bool = False) -> list[list[JsonEntry]]:
    """Select current context in groups that can be converted independently.

    Splitting an arbitrary entry sequence can detach a compaction boundary
    from its summary or a queued command from its redelivery. Either changes
    canonical message metadata and the context used for grading.

    1. Select the current trajectory once, retaining native aliases.
    2. Attach each summary's boundary to that summary, rather than putting all
       boundaries at the beginning where a new compaction invalidates every
       earlier checkpoint.
    3. Keep a queued-command block together until the next assistant entry.
       If a later user entry replaces a queued command, that group's contents
       change, so a fingerprinted checkpoint cannot reuse the obsolete form.

    Concatenating groups is equivalent to ``current_trajectory`` for ordered
    native conversion. A group may contain an unfinished tool cycle; native
    entries are independently converted and results can arrive in later groups.
    ``include_sidechains`` follows ``current_trajectory``: enable it only for
    a validated, dedicated child transcript.
    """
    selected = current_trajectory(entries, include_sidechains=include_sidechains)
    boundaries: dict[str, JsonEntry] = {}
    anchored: dict[str, JsonEntry] = {}
    for entry in selected:
        if entry.get("type") != "system" or entry.get("subtype") != "compact_boundary":
            continue
        if isinstance(entry.get("uuid"), str):
            boundaries[entry["uuid"]] = entry
        metadata = entry.get("compactMetadata")
        if isinstance(metadata, dict):
            for key in ("preservedMessages", "preservedSegment"):
                section = metadata.get(key)
                if isinstance(section, dict) and isinstance(section.get("anchorUuid"), str):
                    anchored[section["anchorUuid"]] = entry

    owners = {id(boundary): uuid for uuid, boundary in anchored.items()}
    groups: list[list[JsonEntry]] = []
    queued: list[JsonEntry] = []
    for entry in selected:
        if entry.get("type") == "system" and entry.get("subtype") == "compact_boundary":
            continue
        if entry.get("type") == "assistant" and queued:
            groups.append(queued)
            queued = []
        uuid = cast(str, entry["uuid"])
        parent = entry.get("parentUuid")
        boundary = anchored.get(uuid) or (boundaries.get(parent) if isinstance(parent, str) else None)
        if boundary is not None and owners.setdefault(id(boundary), uuid) != uuid:
            boundary = {**boundary, "compactMetadata": {}}
        group = [boundary, entry] if boundary is not None else [entry]
        if queued or _queued_command_prompt(entry) is not None:
            queued.extend(group)
        else:
            groups.append(group)
    if queued:
        groups.append(queued)
    return groups


def _live_branch(entries: list[JsonEntry], *, include_sidechains: bool = False) -> _LiveBranch | None:
    return _walk_branch(entries, _BranchSelection({}, None), include_sidechains=include_sidechains)


def _walk_branch(
    entries: list[JsonEntry], selection: _BranchSelection, *, include_sidechains: bool = False
) -> _LiveBranch | None:
    """Walk a Claude UUID tree the way the server parser walks its live branch.

    Besides the order (see ``_message_order``) this reports whether any rewound
    branch was abandoned on the way: at a rewind fork, or between rewound
    versions of a first prompt. The server parser yields every abandoned
    branch as its own conversation, so a delta whose own walk abandons one
    parses to several conversations, which the append endpoint refuses.
    ``None`` means the tree cannot be ordered safely.

    """
    walk = _walk_chain(entries, selection, include_sidechains=include_sidechains)
    return None if walk is None else walk.live_branch()


def _live_chain_walk(entries: list[JsonEntry]) -> _ChainWalk | None:
    """The live walk with its tree, for a caller that needs both the branch and the tree."""
    return _walk_chain(entries, _BranchSelection({}, None))


def _walk_chain(
    entries: list[JsonEntry], selection: _BranchSelection, *, include_sidechains: bool = False
) -> _ChainWalk | None:
    """``_walk_branch`` before queued-command deduplication, keeping the tree it built (see ``_walk_chain_uncached``).

    Inside a ``upload.SharedPlanning`` block, a live walk of the same entries as
    the block's latest one is not repeated: one hook's grading plan and upload
    plan walk each snapshot several times in a row, and a walk holding late
    prompts back costs several breadth-first passes. Callers do not mutate a walk.
    """
    if selection.choices or selection.root_limit is not None:
        return _walk_chain_uncached(entries, selection, include_sidechains=include_sidechains)
    return shared_result(
        "claude-live-walk-with-sidechains" if include_sidechains else "claude-live-walk",
        entries,
        lambda: _walk_chain_uncached(entries, selection, include_sidechains=include_sidechains),
    )


def _walk_chain_uncached(
    entries: list[JsonEntry], selection: _BranchSelection, *, include_sidechains: bool = False
) -> _ChainWalk | None:
    """``_walk_branch`` before queued-command deduplication, keeping the tree it built.

    Keep in sync with ``claude_splits._never_prunes`` and
    ``claude_splits._prove_cuts``: they prove which cuts this walk preserves
    from its rules for pruning rewound siblings, grouping and sorting roots,
    deferring compaction segments and moving compaction summaries. A new or changed rule here can make
    them prove a cut that is no longer safe, so update their conditions with
    it.

    Like the server parser, a selection is walked breadth-first unless its
    breadth-first chain puts a typed prompt before older messages
    (``_inversion_prompts``, with each message no older than its newest
    ancestor stamped when written or a typed prompt written before it:
    ``_age_on_clock``); then it is walked again
    holding those prompts back (``_WalkFrontier``). A release can let a prompt
    on the other branch meet older work in turn, so that walk is checked the
    same way and repeated with any new late prompts added, until none appear
    (at most ``MAX_HOLD_ROUNDS`` times). The abandoned selections still come
    from the breadth-first walk, as on the server, so branches keep the same
    order either way.
    """
    # Every walk below is of the same tree, so they share its fork answers.
    fork_memo: dict[str, tuple[list[JsonEntry], list[JsonEntry]]] = {}
    visits: list[tuple[JsonEntry, list[JsonEntry]]] = []
    walk = _walk_chain_in_order(
        entries,
        selection,
        include_sidechains=include_sidechains,
        hold=frozenset(),
        typed_at={},
        fork_memo=fork_memo,
        visits=visits,
    )
    if walk is None or walk.tree is None or not _inversion_prompts(walk.chain, {}):
        return _with_summaries_placed(walk)
    # A clock only rules prompts out, so it is recorded only once some prompt looks late. The server
    # records it by walking again holding nothing, which visits exactly as this walk did, so replaying
    # this walk's visits records the same clock without a second walk.
    clock: _Clock = {}
    for parent, walked in visits:
        _record_clock(clock, parent, walked)
    # Only prompts this walk reached date its entries, as on the server: not one on a branch abandoned at a rewind.
    _record_prompts_written_before(
        clock,
        (
            entry
            for entry in entries
            if isinstance(entry.get("uuid"), str)
            and entry["uuid"] in walk.visited
            and (include_sidechains or not entry.get("isSidechain", False))
        ),
    )
    walk.clock = clock
    new = _inversion_prompts(walk.chain, clock)
    if not new:
        return _with_summaries_placed(walk)
    rounds: list[_HoldRound] = []
    flagged: frozenset[str] = frozenset()
    typed_at: dict[str, tuple[bool, float]] = {}
    # Hold ages depend only on the tree and the selection, so every round shares one fill.
    hold_ages_below: dict[str, tuple[bool, float]] = {}
    held = walk
    for round_number in range(MAX_HOLD_ROUNDS):
        # The first round's late prompts are the ones just found on the breadth-first chain.
        if round_number:
            new = _inversion_prompts(held.chain, clock) - flagged
        if not new:
            break
        flagged |= new
        typed_at = {**typed_at, **_redelivered_prompt_ages(held.chain, flagged)}
        record = _HoldRound(flagged)
        # The same tree walked again, so it cannot come back empty where the first walk did not.
        held = cast(
            _ChainWalk,
            _walk_chain_in_order(
                entries,
                selection,
                include_sidechains=include_sidechains,
                hold=flagged,
                typed_at=typed_at,
                clock=clock,
                hold_ages_below=hold_ages_below,
                fork_memo=fork_memo,
                record=record,
            ),
        )
        record.chain = held.chain
        rounds.append(record)
    return _with_summaries_placed(
        _ChainWalk(
            held.chain,
            walk.abandons_branch,
            held.visited,
            walk.alternatives,
            held.tree,
            held=_HeldWalk(walk.chain, rounds),
            clock=clock,
        )
    )


def _with_summaries_placed(walk: _ChainWalk | None) -> _ChainWalk | None:
    """``walk`` with its chain's compaction summaries moved back into place (``_place_compaction_summaries``).

    As on the server, summaries are placed once, on the chain the walk settled on, after any
    rounds of holding late prompts back: those rounds look for late prompts in the chain as
    walked, and moving a summary first could take away the evidence that flags one. The
    breadth-first chain and each round's chain in ``walk.held`` stay as walked.

    ``walk.tree.summaries_moved`` is set when placing would move a summary in any of those
    chains, not only the final one, so the cut proofs decline every chain a piece could repair.
    A walk with no tree (no messages, or no root) is returned unchanged.
    """
    if walk is None or walk.tree is None:
        return walk
    lookup = walk.tree.entry_lookup
    placed = _place_compaction_summaries(walk.chain, lookup)
    walked = (
        [] if walk.held is None else [walk.held.breadth_first, *(hold_round.chain for hold_round in walk.held.rounds)]
    )
    walk.tree.summaries_moved = placed is not walk.chain or any(
        _place_compaction_summaries(chain, lookup) is not chain for chain in walked
    )
    walk.chain = placed
    return walk


def _walk_chain_in_order(
    entries: list[JsonEntry],
    selection: _BranchSelection,
    *,
    include_sidechains: bool,
    hold: frozenset[str],
    typed_at: dict[str, tuple[bool, float]],
    clock: _Clock | None = None,
    hold_ages_below: dict[str, tuple[bool, float]] | None = None,
    fork_memo: dict[str, tuple[list[JsonEntry], list[JsonEntry]]] | None = None,
    record: _HoldRound | None = None,
    visits: list[tuple[JsonEntry, list[JsonEntry]]] | None = None,
) -> _ChainWalk | None:
    """One walk of ``selection``: breadth-first, holding back the prompts in ``hold`` (see ``_walk_chain``).

    ``typed_at`` dates held redeliveries by their queued commands (``_redelivered_prompt_ages``).
    ``clock``, if given, is the clock this tree and selection's breadth-first walk recorded
    (``_record_clock``), which a holding walk reads.
    ``hold_ages_below``, if given, is ``_HoldAges``'s memo for this tree and selection, filled by
    whichever walk asks first; ``fork_memo`` likewise keeps each uuid's children in walk order and
    the ones a rewind there leaves, for any walk of the same entries.

    ``record``, if given, collects the visiting order and the prompts held back. ``visits``, if
    given, collects each visited entry with the children the walk queued after it, in visiting
    order: what ``_record_clock`` reads, so a caller can record the clock from it afterwards.
    """
    choices = selection.choices
    entry_lookup = {
        entry["uuid"]: entry
        for entry in entries
        if isinstance(entry.get("uuid"), str)
        and entry["uuid"]
        and (include_sidechains or not entry.get("isSidechain", False))
    }
    message_entries = [
        entry
        for entry in entries
        if (
            (entry.get("type") in ("user", "assistant") and entry.get("message") is not None)
            or _queued_command_prompt(entry) is not None
        )
        and isinstance(entry.get("uuid"), str)
        and entry["uuid"]
        and (include_sidechains or not entry.get("isSidechain", False))
    ]
    if not message_entries:
        return _ChainWalk([], False, set(), [], None)

    message_uuids = {entry["uuid"] for entry in message_entries}
    children: dict[str, list[JsonEntry]] = {}
    for entry in entries:
        parent_uuid = entry.get("parentUuid")
        uuid = entry.get("uuid")
        if (
            isinstance(parent_uuid, str)
            and parent_uuid in entry_lookup
            and isinstance(uuid, str)
            and uuid
            and (include_sidechains or not entry.get("isSidechain", False))
        ):
            children.setdefault(parent_uuid, []).append(entry)

    roots: list[JsonEntry] = []
    # Each root's first-prompt rewind group, by entry identity (see _drop_abandoned_root_prompts).
    root_groups: dict[int, str | None] = {}
    for entry in message_entries:
        parent_uuid = entry.get("parentUuid")
        visited_ancestors: set[str] = set()
        top_ancestor = ""
        has_message_ancestor = False
        while isinstance(parent_uuid, str) and parent_uuid in entry_lookup:
            if parent_uuid in message_uuids:
                has_message_ancestor = True
                break
            if parent_uuid in visited_ancestors:
                return None
            visited_ancestors.add(parent_uuid)
            top_ancestor = parent_uuid
            parent_uuid = entry_lookup[parent_uuid].get("parentUuid")
        if not has_message_ancestor:
            roots.append(entry)
            root_groups[id(entry)] = top_ancestor if parent_uuid is None else None

    if not roots:
        return _ChainWalk(message_entries, False, set(entry_lookup), [], None)

    roots.sort(key=_entry_walk_key)
    sorted_roots = roots
    # Ownership resolves against every root (a segment can be owned by an
    # abandoned first-prompt version), so build the map before pruning roots.
    segment_back_links = _segment_back_links(roots, entry_lookup)
    segments_by_owner = _segments_by_owner(segment_back_links, entry_lookup)
    activity_by_uuid: dict[str, float | None] = {}
    alternatives: list[_BranchSelection] = []
    root_positions = {root["uuid"]: i for i, root in enumerate(roots)}
    current_root_index = 0

    def choose(siblings: list[JsonEntry], survivors: list[JsonEntry], key: str) -> tuple[list[JsonEntry], str | None]:
        """The competing prompt branches among ``siblings`` and the uuid of the one this selection follows."""
        candidates = [
            sibling
            for sibling in siblings
            if (head := _branch_head_message(sibling, children, message_uuids)) is not None
            and _user_entry_text_key(head)
            and not (key.startswith("root:") and _is_compaction_segment_root(sibling))
        ]
        candidate_ids = {candidate["uuid"] for candidate in candidates}
        winner = next(sibling["uuid"] for sibling in survivors if sibling["uuid"] in candidate_ids)
        forced = choices.get(key)
        # As the server: a forced branch another path already consumed falls back to the newest-activity one.
        return candidates, forced if forced in candidate_ids else winner

    def select(siblings: list[JsonEntry], survivors: list[JsonEntry], key: str) -> list[JsonEntry]:
        if len(siblings) == len(survivors):
            return survivors
        candidates, chosen = choose(siblings, survivors, key)
        candidate_ids = {candidate["uuid"] for candidate in candidates}
        is_root = key.startswith("root:")
        if key not in choices and not (is_root and choices):
            for candidate in candidates:
                if candidate["uuid"] == chosen:
                    continue
                limit = root_positions[candidate["uuid"]] if is_root else current_root_index
                if selection.root_limit is not None:
                    limit = min(limit, selection.root_limit)
                alternatives.append(_BranchSelection({**choices, key: candidate["uuid"]}, limit))
        return [sibling for sibling in siblings if sibling["uuid"] not in candidate_ids or sibling["uuid"] == chosen]

    live_roots = []
    for group in dict.fromkeys(root_groups.values()):
        grouped = [root for root in roots if root_groups[id(root)] == group]
        survivors = _drop_abandoned_root_prompts(
            grouped, [group] * len(grouped), children, message_uuids, segments_by_owner, activity_by_uuid
        )
        live_roots.extend(select(grouped, survivors, f"root:{group}"))
    live_ids = {root["uuid"] for root in live_roots}
    live_roots = [root for root in roots if root["uuid"] in live_ids]
    abandons_branch = len(live_roots) < len(roots)
    # An abandoned version ends at its fork's base segment. Later segments
    # belong only to the live version unless an explicit back-link owns them.
    roots = [
        root
        for root in live_roots
        if selection.root_limit is None
        or root_positions[root["uuid"]] <= selection.root_limit
        or root["uuid"] in segment_back_links
    ]
    chain: list[JsonEntry] = []
    visited: set[str] = set()

    known_forks = {} if fork_memo is None else fork_memo

    def fork_children(uuid: str) -> tuple[list[JsonEntry], list[JsonEntry]]:
        """All of ``uuid``'s children in walk order, and those a rewind there does not abandon (any selection)."""
        known = known_forks.get(uuid)
        if known is None:
            siblings = sorted(children.get(uuid, []), key=_entry_walk_key)
            survivors = _drop_abandoned_rewind_branches(
                siblings, children, message_uuids, segments_by_owner, activity_by_uuid
            )
            known = known_forks[uuid] = (siblings, survivors)
        return known

    def walked_children(uuid: str) -> list[JsonEntry]:
        """The children this selection's walk continues through below ``uuid``, in walk order, bar summaries."""
        siblings, survivors = fork_children(uuid)
        if len(survivors) < len(siblings):
            candidates, chosen = choose(siblings, survivors, uuid)
            competing = {candidate["uuid"] for candidate in candidates}
            survivors = [
                sibling for sibling in siblings if sibling["uuid"] not in competing or sibling["uuid"] == chosen
            ]
        return [child for child in survivors if not _is_compaction_segment_root(child)]

    hold_ages = _HoldAges(
        children, walked_children, {} if hold_ages_below is None else hold_ages_below, {} if clock is None else clock
    )

    def walk_from(root: JsonEntry) -> None:
        nonlocal abandons_branch
        queue = _WalkFrontier(root, prompts_to_hold=hold, hold_age=hold_ages, typed_at=typed_at)
        while queue:
            current = queue.pop()
            uuid = current["uuid"]
            if uuid in visited:
                continue
            visited.add(uuid)
            if record is not None:
                record.emitted.append(uuid)
            if uuid in message_uuids:
                chain.append(current)
            all_children, survivors = fork_children(uuid)
            next_entries = [child for child in all_children if child["uuid"] not in visited]
            if len(next_entries) < len(all_children):
                # A duplicate-uuid copy was already visited: decide on the children left, as before.
                survivors = _drop_abandoned_rewind_branches(
                    next_entries, children, message_uuids, segments_by_owner, activity_by_uuid
                )
            live_entries = select(next_entries, survivors, uuid)
            abandons_branch = abandons_branch or len(live_entries) < len(next_entries)
            if visits is not None:
                visits.append((current, live_entries))
            queue.extend(live_entries)
        if record is not None:
            record.held.update(entry["uuid"] for entry in queue.held_entries)

    deferred: list[JsonEntry] = []
    for root in roots:
        current_root_index = root_positions[root["uuid"]]
        owner_leaf = segment_back_links.get(root["uuid"])
        if owner_leaf is not None and owner_leaf not in visited:
            deferred.append(root)
            continue
        walk_from(root)
    any_deferred = bool(deferred)

    # Mirror of the server's deferred second pass (see _EntryTreeWalk._walk): an
    # untimestamped owner root sorts last (_entry_walk_key), so a segment's own
    # root can come up before its owner leaf is visited and be wrongly skipped.
    # Re-offer skipped segment roots once their owner leaf is reached, to a
    # fixpoint; one still unclaimed belongs to a branch this walk abandoned.
    progressed = True
    while progressed:
        progressed = False
        remaining: list[JsonEntry] = []
        for root in deferred:
            if root["uuid"] in visited:
                continue
            if segment_back_links.get(root["uuid"]) in visited:
                current_root_index = root_positions[root["uuid"]]
                walk_from(root)
                progressed = True
            else:
                remaining.append(root)
        deferred = remaining

    tree = _WalkTree(entry_lookup, message_uuids, children, sorted_roots, segment_back_links, any_deferred, False)
    return _ChainWalk(chain, abandons_branch, visited, alternatives, tree)


def _utc_epoch(entry: JsonEntry) -> float | None:
    """The entry's timestamp in seconds since the epoch, reading a naive one as UTC, or None if unparseable."""
    timestamp = entry.get("timestamp")
    if not isinstance(timestamp, str):
        return None
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)).timestamp()  # noqa: UP017


def _place_compaction_summaries(chain: list[JsonEntry], entry_lookup: dict[str, JsonEntry]) -> list[JsonEntry]:
    """Move each compaction summary to where the compaction happened; mirror of the server's repair.

    Returns ``chain`` itself unless some compaction summary in it comes after a
    message stamped later than the summary, as when Claude Code links the
    conversation after a compaction to the pre-compaction tree. Then:

    1. a summary and the entries right after it not stamped later than it (the
       turn it replays) form its block;
    2. the blocks, by summary time, cut the conversation into eras; every other
       message goes to the era its timestamp falls in (an untimestamped one to
       its predecessor's), a queued-command attachment joins the era of the
       ``user`` entry re-delivering it, and no message goes earlier than the
       nearest message above it in this chain;
    3. the blocks replaying a tool call take its last results in time order, one
       each; a taken result placed before its block, when no other result for the
       call lands after it, moves to the start of the block's era, so the live
       cut at the last complete tool cycle does not stop at the summary;
    4. era 0 comes first, then each block followed by its era, in walk order.

    A summary is the flagged entry, or the legacy preamble only on a segment root
    (``_is_compaction_summary``), with no message above it in this chain: one the
    walk placed under a message is already in causal order.

    Must match the server parser's repair exactly:
    stored chains and upload cut points depend on both sides agreeing.
    """
    epochs = [_utc_epoch(entry) for entry in chain]
    in_chain = {entry["uuid"] for entry in chain}
    nearest_listed: dict[str, str | None] = {}

    def is_summary(index: int) -> bool:
        return (
            epochs[index] is not None
            and _is_compaction_summary(chain[index], entry_lookup)
            and _nearest_listed_ancestor(chain[index], entry_lookup, in_chain, nearest_listed) is None
        )

    newest: float | None = None
    gated = False
    for index, epoch in enumerate(epochs):
        if newest is not None and is_summary(index) and newest > cast(float, epoch):
            gated = True
            break
        if epoch is not None and (newest is None or epoch > newest):
            newest = epoch
    if not gated:
        return chain

    blocks: list[tuple[float, list[int]]] = []
    block_of: dict[int, int] = {}
    index = 0
    while index < len(chain):
        if not is_summary(index):
            index += 1
            continue
        summary_epoch = cast(float, epochs[index])
        members = [index]
        index += 1
        while index < len(chain) and not is_summary(index):
            epoch = epochs[index]
            if epoch is not None and epoch > summary_epoch:
                break
            members.append(index)
            index += 1
        for member in members:
            block_of[member] = len(blocks)
        blocks.append((summary_epoch, members))

    ranked = sorted(range(len(blocks)), key=lambda block: blocks[block][0])
    rank_of = {block: rank for rank, block in enumerate(ranked)}
    thresholds = [blocks[block][0] for block in ranked]
    by_time: dict[int, int] = {}
    previous_era = 0
    for index, epoch in enumerate(epochs):
        if index not in block_of:
            previous_era = by_time[index] = previous_era if epoch is None else bisect_left(thresholds, epoch)
    for attachment, redelivery in _queued_command_redeliveries(chain):
        if attachment in by_time and redelivery in by_time:
            by_time[attachment] = max(by_time[attachment], by_time[redelivery])

    def assign(floor: dict[int, int]) -> list[int]:
        era_at = [0] * len(chain)
        era_of: dict[str, int] = {}
        previous_era = 0
        for index, entry in enumerate(chain):
            if index in block_of:
                era_at[index] = era_of[entry["uuid"]] = rank_of[block_of[index]] + 1
                continue
            era = by_time[index] if epochs[index] is not None else max(by_time[index], previous_era)
            era = max(era, floor.get(index, 0))
            parent = _nearest_listed_ancestor(entry, entry_lookup, in_chain, nearest_listed)
            if parent is not None:
                era = max(era, era_of.get(parent, 0))
            era_at[index] = era_of[entry["uuid"]] = previous_era = era
        return era_at

    era_at = assign({})
    results: dict[str, list[int]] = {}
    for index, entry in enumerate(chain):
        if index not in block_of:
            for tool_id in _entry_tool_ids(entry, "user", "tool_result", "tool_use_id"):
                results.setdefault(tool_id, []).append(index)
    replaying: dict[str, list[int]] = {}
    for block in ranked:
        members = blocks[block][1]
        replayed = {tool_id for m in members for tool_id in _entry_tool_ids(chain[m], "assistant", "tool_use", "id")}
        replayed -= {
            tool_id for m in members for tool_id in _entry_tool_ids(chain[m], "user", "tool_result", "tool_use_id")
        }
        for tool_id in replayed:
            replaying.setdefault(tool_id, []).append(rank_of[block] + 1)
    floor: dict[int, int] = {}
    for tool_id, opening in sorted(replaying.items()):
        # The blocks replaying a call, in time order, take its last results, one each.
        placed = results.get(tool_id, [])
        chosen = placed[-len(opening) :]
        # A spare result lands after a block exactly when the latest-placed spare does,
        # so one pass per call keeps this linear however many blocks replay it.
        spare_era = max((era_at[other] for other in placed[: len(placed) - len(chosen)]), default=-1)
        for opens, index in zip(opening[len(opening) - len(chosen) :], chosen, strict=True):
            if era_at[index] < opens and spare_era < opens:
                # One entry can answer several calls; it goes after the latest block needing it.
                floor[index] = max(floor.get(index, 0), opens)
    if floor:
        era_at = assign(floor)
    eras: list[list[int]] = [[] for _ in range(len(blocks) + 1)]
    for index in range(len(chain)):
        if index not in block_of:
            eras[era_at[index]].append(index)

    order = list(eras[0])
    for rank, block in enumerate(ranked):
        order.extend(blocks[block][1])
        order.extend(eras[rank + 1])
    return [chain[position] for position in order]


def _nearest_listed_ancestor(
    entry: JsonEntry, entry_lookup: dict[str, JsonEntry], listed: set[str], memo: dict[str, str | None]
) -> str | None:
    """The uuid of the nearest entry above ``entry`` that is in ``listed``, or None; mirror of the server's.

    ``memo`` records the answer for every unlisted entry a climb passes, so shared
    ancestors are climbed once. A missing parent or a cycle ends the climb with None.
    """
    path: list[str] = []
    on_path: set[str] = set()
    found: str | None = None
    parent = entry.get("parentUuid")
    while isinstance(parent, str):
        if parent in listed:
            found = parent
            break
        if parent in memo:
            found = memo[parent]
            break
        if parent in on_path or parent not in entry_lookup:
            break
        path.append(parent)
        on_path.add(parent)
        parent = entry_lookup[parent].get("parentUuid")
    for uuid in path:
        memo[uuid] = found
    return found


def _entry_tool_ids(entry: JsonEntry, entry_type: str, block_type: str, key: str) -> list[str]:
    """The string ``key`` values of ``entry``'s ``block_type`` content blocks, when it is an ``entry_type`` entry."""
    message = entry.get("message") if entry.get("type") == entry_type else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [
        block[key]
        for block in content
        if isinstance(block, dict) and block.get("type") == block_type and isinstance(block.get(key), str)
    ]


def _is_compaction_summary(entry: JsonEntry, entry_lookup: dict[str, JsonEntry]) -> bool:
    """Whether ``entry`` is a compaction summary, by the server parser's rule.

    The flag counts anywhere. The legacy preamble counts only on a segment root:
    no parent, or a ``compact_boundary`` entry present here as parent.
    """
    if entry.get("type") != "user":
        return False
    if entry.get("isCompactSummary"):
        return True
    key = _user_entry_text_key(entry)
    if not key or not key[0].startswith("This session is being continued"):
        return False
    parent = entry.get("parentUuid")
    if parent is None:
        return True
    boundary = entry_lookup.get(parent) if isinstance(parent, str) else None
    return boundary is not None and boundary.get("type") == "system" and boundary.get("subtype") == "compact_boundary"


def _unfinished_compaction(entries: list[JsonEntry]) -> tuple[int, float] | None:
    """The position and stamp of the file's last compaction summary if nothing after it is stamped later, else None.

    That is what a compaction Claude Code is still writing looks like: the
    summary is followed only by the turn it replays, which carries older stamps.
    A session that stopped mid-compaction looks the same, so this is a hint, not
    proof. If an earlier compaction already needs ``_place_compaction_summaries``,
    the whole file places the new summary at once, but a later piece of the file
    parsed alone has no summary stamped before a newer message, so it is not
    repaired until the next turn arrives. Until then, cuts between the two
    compactions do not split the file cleanly, though they may again once it does.
    """
    lookup: dict[str, JsonEntry] | None = None
    newest_after: float | None = None
    for index in range(len(entries) - 1, -1, -1):
        entry = entries[index]
        epoch = _utc_epoch(entry)
        if entry.get("type") == "user" and epoch is not None:
            if lookup is None:
                lookup = {e["uuid"]: e for e in entries if isinstance(e.get("uuid"), str)}
            if _is_compaction_summary(entry, lookup):
                return (index, epoch) if newest_after is None or newest_after <= epoch else None
        if epoch is not None and (newest_after is None or epoch > newest_after):
            newest_after = epoch
    return None


class _RewindReach:  # noqa: B903
    """The last cursor whose suffix still holds a rewind, remembered for one transcript snapshot.

    Kept for the most recent ``entries`` list only (compared by identity and
    length), since a chunk planner asks about many cursors of one snapshot in
    a row and then moves on.
    """

    __slots__ = ("entries", "entry_count", "last_cursor")

    entries: list[JsonEntry]
    entry_count: int
    last_cursor: int

    def __init__(self, entries: list[JsonEntry], last_cursor: int) -> None:
        self.entries = entries
        self.entry_count = len(entries)
        self.last_cursor = last_cursor


_rewind_reach: _RewindReach | None = None


def _last_cursor_before_a_rewind(entries: list[JsonEntry]) -> int:
    """Return the largest cursor whose suffix parses with an abandoned branch, or -1 if none is found.

    A chunk planner probes boundaries one entry at a time, and every boundary
    before a rewind near the end of a large transcript is unsafe; checking each
    with three whole-tree walks is quadratic and can outlast the collector's
    deadline. The cursors whose suffix abandons a branch are, in practice, a
    prefix of the transcript (a suffix keeps a rewind as long as it starts
    before the fork), so a binary search finds where that prefix ends in a
    logarithmic number of suffix walks. Only the refusal side uses the result:
    any cursor at or before it is refused outright, which at worst refuses a
    boundary the exact check would have accepted. Every later cursor still
    gets the exact check, so nothing unsafe is ever accepted.
    """
    global _rewind_reach
    reach = _rewind_reach
    if reach is not None and reach.entries is entries and reach.entry_count == len(entries):
        return reach.last_cursor

    def abandons(cursor: int) -> bool:
        branch = _live_branch(entries[cursor:])
        return branch is not None and branch.abandons_branch

    last_cursor = -1
    if entries and abandons(0):
        # Invariant: the suffix at ``low`` abandons a branch; the one at ``high`` (the empty suffix) does not.
        low, high = 0, len(entries)
        while high - low > 1:
            middle = (low + high) // 2
            if abandons(middle):
                low = middle
            else:
                high = middle
        last_cursor = low
    _rewind_reach = _RewindReach(entries, last_cursor)
    return last_cursor


def delta_needs_full_upload(entries: list[JsonEntry], cursor: int) -> bool:
    """Return whether the suffix from ``cursor`` cannot be appended to the prefix before it.

    Two cases need a full upload instead. Parsing the suffix alone could change
    the message order the whole file parses to. Or the suffix itself contains
    a rewind (a fork, or a rewound first prompt) and parses to more than one
    conversation, which the append endpoint refuses even when the live branch
    order would line up. Chunked uploads use this as their boundary guard too,
    so a rewind always lands in a full-ingest chunk rather than an append.

    """
    if cursor <= _last_cursor_before_a_rewind(entries):
        return True
    prefix = _live_branch(entries[:cursor])
    delta = _live_branch(entries[cursor:])
    full = _live_branch(entries)
    return (
        prefix is None
        or delta is None
        or full is None
        or delta.abandons_branch
        or full.order != [*prefix.order, *delta.order]
    )


def split_preserves_order(entries: list[JsonEntry], cursor: int) -> bool:
    """Whether two independently parsed pieces retain the full live-branch order.

    Unlike the legacy append guard, this permits multiple branches inside the
    suffix: incremental ingestion stores them under an explicit fork flag.
    To check many cuts of one list, use `SplitOrderCheck`, which parses the
    whole list once.
    """
    return SplitOrderCheck(entries)(cursor)


class SuffixOrders:
    """Live orders of the suffixes ``entries[position:]`` of one list, shared by the order checks of its pieces.

    The planner checks a cut of the rest of the file and then the same cut of the whole file, and both
    need the order of what follows the cut. ``known(position)`` gives that order when the caller already
    knows it, or None; otherwise it is parsed and kept for the next few questions. The caller must not
    change ``entries`` or its entry dicts while it keeps this object.
    """

    __slots__ = ("_entries", "_known", "_recent")

    _KEPT = 8

    def __init__(self, entries: list[JsonEntry], known: Callable[[int], list[str] | None]) -> None:
        self._entries = entries
        self._known = known
        self._recent: dict[int, list[str] | None] = {}

    def __call__(self, position: int) -> list[str] | None:
        """``_live_branch(entries[position:]).order``, or None when that suffix cannot be ordered."""
        known = self._known(position)
        if known is not None:
            return known
        recent = self._recent
        if position in recent:
            return recent[position]
        branch = _live_branch(self._entries[position:])
        if len(recent) >= self._KEPT:
            # Replace rather than trim, so threads sharing this object never see a dict change size mid-read.
            self._recent = recent = {}
        recent[position] = order = None if branch is None else branch.order
        return order


class SplitOrderCheck:
    """``split_preserves_order(entries, cursor)`` for many cursors of one list, parsing the whole list once.

    A chunk planner checks many cuts of one window, and the receipt of each
    chunk against the whole file, so the whole list's parse is the repeated
    cost. The parse is kept on this object, so it lives exactly as long as the
    caller keeps the check, and the caller must not change ``entries`` or its
    entry dicts meanwhile. ``order``, when given, must be
    ``_live_branch(entries).order`` and spares that parse. ``suffixes``, when
    given, must answer for a list whose slice from ``offset`` is ``entries``;
    each cut then takes the order after it from there.
    """

    __slots__ = ("_entries", "_order", "_parsed", "_suffixes", "_offset")

    def __init__(
        self,
        entries: list[JsonEntry],
        order: list[str] | None = None,
        *,
        suffixes: SuffixOrders | None = None,
        offset: int = 0,
    ) -> None:
        self._entries = entries
        self._order = order
        self._parsed = order is not None
        self._suffixes = suffixes
        self._offset = offset

    def __call__(self, cursor: int) -> bool:
        entries = self._entries
        if cursor == 0 or cursor == len(entries):
            return True
        if not self._parsed:
            full = _live_branch(entries)
            self._order, self._parsed = None if full is None else full.order, True
        order = self._order
        prefix = _live_branch(entries[:cursor])
        if self._suffixes is not None:
            suffix_order = self._suffixes(self._offset + cursor)
        else:
            suffix = _live_branch(entries[cursor:])
            suffix_order = None if suffix is None else suffix.order
        return (
            prefix is not None
            and suffix_order is not None
            and order is not None
            and order == prefix.order + suffix_order
        )


def branch_indices(entries: list[JsonEntry]) -> list[list[int]]:
    """Return raw source positions for every Claude branch, live branch last.

    Use the same rewind classification, sibling order and compaction ownership
    as the live walk. Shared ancestors appear in each branch; the uploader can
    reuse their acknowledged hashes instead of sending them again.
    """
    return _branch_indices_from_walk(entries, _live_chain_walk(entries))


def _branch_indices_from_walk(entries: list[JsonEntry], live_walk: _ChainWalk | None) -> list[list[int]]:
    """``branch_indices`` for a caller that already holds ``_live_chain_walk(entries)``."""
    live = None if live_walk is None else live_walk.live_branch()
    if live is None or not live.abandons_branch:
        return [list(range(len(entries)))]
    pending = list(live.alternatives)
    walks = []
    # Only which entries each branch keeps matters here. With every uuid written once, holding prompts back
    # reorders a branch but never changes what it visits or where it forks, so each branch is told apart by its
    # breadth-first order and an abandoned branch is walked breadth-first only, without the walks a late prompt
    # would add. A replayed copy of a uuid can be reached first instead once a prompt is held, so then each
    # branch is walked in full.
    uuids = [entry["uuid"] for entry in entries if isinstance(entry.get("uuid"), str)]
    held = None if live_walk is None else live_walk.held
    plain_walks = len(set(uuids)) == len(uuids)
    breadth_first = live.entries
    if plain_walks and held is not None and live_walk is not None and live_walk.tree is not None:
        # Placed like the breadth-first walks below, which ``_with_summaries_placed`` returns placed.
        breadth_first = _place_compaction_summaries(held.breadth_first, live_walk.tree.entry_lookup)
    seen: set[tuple[str, ...]] = {tuple(entry["uuid"] for entry in _drop_redelivered_queued_commands(breadth_first))}
    while pending:
        selection = pending.pop()
        if plain_walks:
            plain = _with_summaries_placed(
                _walk_chain_in_order(entries, selection, include_sidechains=False, hold=frozenset(), typed_at={})
            )
            walk = None if plain is None else plain.live_branch()
        else:
            walk = _walk_branch(entries, selection)
        if walk is None or tuple(walk.order) in seen:
            continue
        seen.add(tuple(walk.order))
        walks.append(walk)
        pending.extend(walk.alternatives)
    return [_branch_indices(entries, walk) for walk in [*walks, live]]


def current_branch_indices(entries: list[JsonEntry], *, include_sidechains: bool = False) -> list[int]:
    """Source positions fingerprinted by the uploader for the current branch only.

    Unlike current_trajectory, this retains native file order and bookkeeping.
    Use it to match upload acknowledgments, not as an ordered grading payload.
    No abandoned branch is reconstructed. A cyclic tree raises ValueError.
    """
    live = _live_branch(entries, include_sidechains=include_sidechains)
    if live is None:
        raise ValueError("Cannot select a current trajectory from a cyclic transcript")
    return _branch_indices(entries, live) if live.abandons_branch else list(range(len(entries)))


def _branch_indices(entries: list[JsonEntry], walk: _LiveBranch) -> list[int]:
    """Keep the branch's visited records and transparent parents in source order."""
    lookup = {entry["uuid"]: entry for entry in entries if isinstance(entry.get("uuid"), str)}
    included = set(walk.visited)
    for uid in list(included):
        parent = lookup[uid].get("parentUuid")
        while isinstance(parent, str) and parent in lookup and parent not in included:
            included.add(parent)
            parent = lookup[parent].get("parentUuid")
    return [i for i, entry in enumerate(entries) if entry.get("uuid") in included or not entry.get("uuid")]


def live_compaction_start(entries: list[JsonEntry]) -> int:
    """Return where the agent's current context starts in the file: its live branch's last compaction, or 0.

    Claude Code continues a compacted conversation from a ``compact_boundary``
    system entry with no parent (older files: an ``isCompactSummary`` user entry
    as the new root), and the server grades only what the last compaction kept.
    Its ``compactMetadata`` may keep earlier messages too
    (``preservedMessages.uuids``, or a ``preservedSegment`` from ``headUuid``
    on), which sit before the boundary in the file, so the context starts at
    the earliest of those. A summary is matched to its boundary by the
    metadata's ``anchorUuid`` or by its parent link. A compaction on a rewound
    branch is skipped: the live branch does not continue it.
    """
    live = branch_indices(entries)[-1]
    positions = {entries[index].get("uuid"): index for index in live if isinstance(entries[index].get("uuid"), str)}
    for index in reversed(live):
        entry = entries[index]
        if _is_boundary(entry):
            boundary = index
        elif entry.get("isCompactSummary"):
            boundary = next(
                (
                    position
                    for position in reversed(live[: live.index(index)])
                    if _is_boundary(entries[position]) and _anchors(entries[position], entry)
                ),
                None,
            )
            if boundary is None:
                return index
        else:
            continue
        return min([boundary, *_kept_positions(entries[boundary], positions)])
    return 0


def _is_boundary(entry: JsonEntry) -> bool:
    return entry.get("type") == "system" and entry.get("subtype") == "compact_boundary"


def _anchors(boundary: JsonEntry, summary: JsonEntry) -> bool:
    """Whether ``boundary`` belongs to ``summary``: its metadata anchors to it, or it is the summary's parent."""
    uuid = summary.get("uuid")
    if summary.get("parentUuid") == boundary.get("uuid"):
        return True
    metadata = boundary.get("compactMetadata")
    return isinstance(metadata, dict) and any(
        isinstance(metadata.get(key), dict) and metadata[key].get("anchorUuid") == uuid
        for key in ("preservedMessages", "preservedSegment")
    )


def _kept_positions(boundary: JsonEntry, positions: dict[Any, int]) -> list[int]:
    """The live-branch positions of the earlier messages ``boundary``'s compaction kept."""
    metadata = boundary.get("compactMetadata")
    if not isinstance(metadata, dict):
        return []
    preserved = metadata.get("preservedMessages")
    if isinstance(preserved, dict) and isinstance(preserved.get("uuids"), list):
        return [positions[uuid] for uuid in preserved["uuids"] if isinstance(uuid, str) and uuid in positions]
    segment = metadata.get("preservedSegment")
    if isinstance(segment, dict) and segment.get("headUuid") in positions:
        return [positions[segment["headUuid"]]]
    return []
