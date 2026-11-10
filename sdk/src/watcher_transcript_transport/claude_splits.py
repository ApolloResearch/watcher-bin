"""Answer the upload planner's Claude Code boundary questions for a whole snapshot in one pass.

The planner (`watcher_transcript_transport.incremental`) cuts a transcript into
bounded requests. A Claude Code cut is safe when two independently parsed pieces
keep the whole file's live-branch order (`claude.split_preserves_order`) and the
earlier piece does not end inside a tool cycle (`claude.trim_incomplete_tail`).
Each exact order check walks the conversation tree three times, and the planner
asks about cuts all through the file, so planning a long first upload chunk by
chunk is quadratic in its length.

`ClaudeSplitIndex` walks the tree once and proves, for every cut at once, the
order check true. A cut it cannot prove still gets the exact check from the
caller, so a missing proof costs time, never correctness; on a file whose walk
holds prompts back, where that time is exact parses of nearly the whole file,
the planner prefers a proven cut. It can also refute a
cut, from the whole file's live order alone, where the exact check is certain
to fail, which spares that check.
`TailCompleteness` answers the tool-cycle check for every end of one slice with
a single left fold.
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import accumulate

from watcher_transcript_transport.claude import (
    SplitOrderCheck,
    SuffixOrders,
    _ChainWalk,
    _Clock,
    _entry_walk_key,
    _HeldWalk,
    _late_prompt_witnesses,
    _live_chain_walk,
    _queued_command_redeliveries,
    _user_entry_text_key,
    _WalkTree,
    _written_age,
)
from watcher_transcript_transport.upload import JsonEntry


class TailCompleteness:
    """Whether ``trim_incomplete_tail(entries[start:end], ...)`` keeps all of its entries, for any ``end``.

    ``trim_incomplete_tail`` is a left fold, so one pass over ``entries[start:]``
    answers every end. The fold extends lazily to the largest end asked. It
    must stay the same fold as ``trim_incomplete_tail``; a property test
    compares the two on every prefix of random transcripts. Entries must be
    dicts, as `ClaudeSplitIndex` checks before a caller relies on this.
    """

    __slots__ = ("_entries", "_start", "_allow_trailing_assistant_text", "_pending", "_last_complete", "_flags")

    def __init__(self, entries: list[JsonEntry], start: int, *, allow_trailing_assistant_text: bool) -> None:
        self._entries = entries
        self._start = start
        self._allow_trailing_assistant_text = allow_trailing_assistant_text
        self._pending: set[object] = set()
        self._last_complete = 0
        # _flags[j]: whether the first j entries of the slice are complete. The empty slice is.
        self._flags = bytearray(b"\x01")

    def complete(self, end: int) -> bool:
        """Answer for ``entries[start:end]``; ``end`` must lie in ``start..len(entries)``."""
        if end - self._start >= len(self._flags):
            self._extend(end)
        return bool(self._flags[end - self._start])

    def _extend(self, end: int) -> None:
        entries, start, flags, pending = self._entries, self._start, self._flags, self._pending
        allow = self._allow_trailing_assistant_text
        last_complete = self._last_complete
        for index in range(start + len(flags) - 1, end):
            entry = entries[index]
            position = index - start
            message_type = entry.get("type", "")
            if message_type in ("progress", "file-history-snapshot"):
                flags.append(0)
                continue
            if message_type == "assistant":
                message = entry.get("message", {})
                content = message.get("content", []) if isinstance(message, dict) else []
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            pending.add(block.get("id", ""))
                if allow and not pending:
                    last_complete = position + 1
                flags.append(last_complete == position + 1)
                continue
            if message_type == "user":
                message = entry.get("message", {})
                content = message.get("content", []) if isinstance(message, dict) else []
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            pending.discard(block.get("tool_use_id", ""))
            if not pending:
                last_complete = position + 1
            flags.append(last_complete == position + 1)
        self._last_complete = last_complete


class ClaudeSplitIndex:
    """Proofs that ``split_preserves_order`` holds, for every cut of one snapshot, from one tree walk.

    ``proves(cut)`` true means ``split_preserves_order(entries, cut)`` is true.
    False means only "not proven": the caller runs the exact check.
    ``proves_window(start, cut)`` does the same for
    ``split_preserves_order(entries[start:], cut - start)``, which holds
    whenever both cuts hold for the whole file (the tree facts below that make
    a cut safe for the whole file also make it safe for any suffix that starts
    at a safe cut).

    The index also guarantees the planner's exact checks cannot raise on this
    snapshot (``valid``): every entry is a dict, tool ids are hashable and
    every sort key computes. The planner relies on that to test a cut before
    encoding its request without changing which exception it would raise.

    How a cut is proven (what the walk would do in each piece):

        file:   [ e0 e1 e2 ... e(k-1) | ek ... e(n-1) ]
                  prefix piece         suffix piece

    1. The whole tree must be one the walk never prunes, in any piece: unique
       uuids, no cycles, no deferred compaction segment, no compaction
       summary moved back into place, no rewound first prompts and no node with two children that could head competing user
       prompts once a piece cuts their subtrees. Then each piece's walk is the
       whole walk restricted to that piece, provided the cut keeps the shape:
    2. no entry before the cut hangs below an entry after it (nor a
       compaction segment root below a leaf after it), so the prefix is closed
       under ancestry and its walk is the whole walk's prefix order;
    3. at most one message after the cut has its nearest message ancestor
       before it. That message becomes a root of the suffix; with two, their
       relative order would follow sort keys instead of the tree;
    4. the whole walk emits every message before the cut ahead of every
       message after it;
    5. that one crossing message, if any, sorts ahead of the first true root
       after the cut, so the suffix walk visits it first as the whole walk does;
    6. no queued command before the cut is redelivered by a ``user`` entry
       after it, so deduplicating the pieces separately drops the same
       entries as deduplicating the whole chain (for a walk that held prompts
       back, in the final holding round's chain too, which is the one
       deduplicated);

    Facts 1 to 6 are checked against the breadth-first chain. They make each
    piece's breadth-first chain a slice of the whole one. Most files have no
    late prompt (``claude._late_prompt_witnesses``: a typed prompt that an
    older reply or tool result follows later in its compaction segment), and
    every walk is plain breadth-first. A file that has some is walked again
    holding back each late prompt (``claude._walk_chain``), in rounds that
    add any prompt a release left before older work; each piece does the same
    with the late prompts it finds. Then a cut also needs, of every round's
    walk:

    7. it visits every entry before the cut ahead of every entry after it,
       so whatever held a prompt back before the cut was itself before the
       cut. Only entries with a message at or below them count, here and in
       fact 8: any other emits nothing, waits with no age and never holds a
       prompt back, so where the walk visits it changes nothing. No entry after the cut is older (by ``claude._age_on_clock``)
       than a prompt held before the cut, since none is older than a prompt
       written before it (fact 10 keeps that so in each piece), so no age a
       waiting entry takes from below it (``claude._HoldAges``) changes a
       decision there;
    8. if it held a prompt after the cut, at most one entry after the cut has
       its parent before it, and that one is a message, so the walk after the
       cut starts from that message alone, as the suffix walk does from its
       root. (Without a held prompt there, entries the suffix walk never
       reaches only sat in the queue, and their age decides nothing.)
    9. the cut does not fall between a late prompt and the first older entry
       after it (its witness), nor between a queued command and its
       redelivery, in the chain the round started from, so each piece dates
       each redelivery by its command as the whole file does, and flags
       exactly the file's late prompts that fall in it;
    10. the cut does not fall between an entry and what it is dated by
       when stamped older than that (``claude._age_on_clock``): its newest
       ancestor stamped when written, or the newest typed prompt written
       before it in the file, so each piece dates it the same as the whole
       file does.

    Facts 2, 3, 6, 8 and 10 are counted for all cuts at once with difference
    arrays over each offending interval of cuts; 4 and 7 with a
    running maximum and a suffix minimum of walk positions; 5 per cut from the
    sorted roots; 9 with a difference array over each prompt-to-witness span.

    The index also keeps the whole snapshot's live order. Where the snapshot
    is known to split (a proven cut, or one whose receipt check passed), the
    order of the rest of the file is that order's tail (`window_order`), and a
    cut of the rest that would put an entry after it ahead of one before it in
    that order cannot keep it (`window_refutation`). Both spare exact parses on
    a file whose late prompts leave many cuts unproven.
    """

    __slots__ = (
        "entries",
        "count",
        "valid",
        "moves_summaries",
        "holds_prompts",
        "receipts",
        "whole_split",
        "_proven",
        "_acknowledgement_tail",
        "_order",
        "_order_at",
        "_order_before",
        "_later_order_min",
        "suffix_orders",
    )

    def __init__(self, entries: list[JsonEntry], walk: _ChainWalk | None) -> None:
        """Build from ``walk``, which must be ``_live_chain_walk(entries)`` (see `build`)."""
        self.entries = entries
        self.count = len(entries)
        # Whether this snapshot's chain had compaction summaries moved back into place.
        # The index then proves no interior cut (fact 1), but can still be valid.
        self.moves_summaries = walk is not None and walk.tree is not None and walk.tree.summaries_moved
        # Whether this snapshot's walk held prompts back, known even when nothing is proven.
        self.holds_prompts = walk is not None and walk.held is not None
        # Answers ``incremental._claude_acknowledgement_is_safe`` already computed for this snapshot, by
        # end. Like the proofs, they hold only while ``entries`` and its entry dicts stay unchanged.
        self.receipts: dict[int, bool] = {}
        # The exact order check for cuts of the whole snapshot, which parses it once for every cut asked.
        self.whole_split = SplitOrderCheck(entries)
        self._acknowledgement_tail: TailCompleteness | None = None
        # The whole snapshot's live order, and where each entry sits in it, for `window_order` and
        # `window_refutation`. A proven tree has unique uuids, so each uuid in the order names one entry.
        self._order: list[str] | None = None
        self._order_at: list[int] = []
        self._order_before: list[int] = []
        self._later_order_min: list[int] = []
        try:
            proven = _prove_cuts(entries, walk)
            if proven is not None and walk is not None:
                self._order = walk.live_branch().order
                self._order_at, self._order_before, self._later_order_min = _order_positions(entries, self._order)
        except Exception:  # noqa: BLE001
            # Any unexpected input shape means the index proves nothing and the
            # planner keeps its exact checks, which handle that input as before.
            proven = self._order = None
        self.valid = proven is not None
        self._proven = proven if proven is not None else bytearray()
        # The order after any cut, shared by the planner's checks of the rest of the file and of the whole.
        self.suffix_orders = SuffixOrders(entries, self.window_order)
        if self._order is not None:
            self.whole_split = SplitOrderCheck(entries, self._order, suffixes=self.suffix_orders)

    @classmethod
    def build(cls, entries: list[JsonEntry]) -> ClaudeSplitIndex:
        return cls(entries, _live_chain_walk(entries))

    def covers(self, entries: list[JsonEntry]) -> bool:
        """Whether this index is valid and was built for this exact list, unchanged in length."""
        return self.valid and entries is self.entries and len(entries) == self.count

    def proves(self, cut: int) -> bool:
        """``cut`` must lie in ``0..count``; the ends always split trivially."""
        return cut <= 0 or cut >= self.count or (self.valid and bool(self._proven[cut]))

    def proves_window(self, start: int, cut: int) -> bool:
        """Prove ``split_preserves_order(entries[start:], cut - start)``, for ``0 <= start < cut <= count``."""
        return self.proves(start) and self.proves(cut)

    def _splits_at(self, start: int) -> bool:
        """Whether a valid index knows the whole snapshot splits at ``start <= count``: proven, or its receipt passed."""
        return start == 0 or bool(self._proven[start]) or self.receipts.get(start) is True

    def window_order(self, start: int) -> list[str] | None:
        """``_live_branch(entries[start:]).order`` without parsing, or None when that is not known.

        It is known when the whole snapshot splits at ``start`` (`_splits_at`): the whole order is then the
        order before ``start`` followed by this one, and with unique uuids the entries before ``start`` are
        exactly the first ``_order_before[start]`` of it.
        """
        if self._order is None or not self._splits_at(start):
            return None
        return self._order[self._order_before[start] :]

    def window_refutation(self, start: int) -> Callable[[int], bool]:
        """Return ``refutes(cut)``: true only when ``split_preserves_order(entries[start:], cut - start)`` is false.

        False means only "not refuted". When the whole snapshot splits at ``start``, the order of
        ``entries[start:]`` is the whole order restricted to those entries (see `window_order`). Two
        pieces that keep it emit every entry before the cut ahead of every entry after it, so a cut is
        refuted when the whole order puts some entry after the cut ahead of an entry between ``start``
        and the cut: a running maximum of order positions from ``start`` against a suffix minimum.
        The running maximum lives in the returned function, so it is safe to share the index.
        """
        if self._order is None or not self._splits_at(start):
            return _never_refuted
        order_at, later_min, count = self._order_at, self._later_order_min, self.count
        running_max: list[int] = []

        def refutes(cut: int) -> bool:
            if not start < cut < count:
                return False
            top = running_max[-1] if running_max else -1
            for index in range(start + len(running_max), cut):
                top = max(top, order_at[index])
                running_max.append(top)
            return running_max[cut - start - 1] > later_min[cut]

        return refutes

    def acknowledgement_complete(self, end: int) -> bool:
        """``len(trim_incomplete_tail(entries[:end], allow_trailing_assistant_text=True)) == end``."""
        if self._acknowledgement_tail is None:
            self._acknowledgement_tail = TailCompleteness(self.entries, 0, allow_trailing_assistant_text=True)
        return self._acknowledgement_tail.complete(end)


def _never_refuted(cut: int) -> bool:
    return False


def _order_positions(entries: list[JsonEntry], order: list[str]) -> tuple[list[int], list[int], list[int]]:
    """For a proven snapshot's live ``order``: each entry's position in it (-1 if absent), by file index; how
    many entries before each file index it holds; and the smallest position at or after each file index
    (``len(order)`` if none). A uuid in ``order`` that names no main-chain entry raises KeyError.
    """
    index_of = {
        entry["uuid"]: index
        for index, entry in enumerate(entries)
        if isinstance(entry.get("uuid"), str) and entry["uuid"] and not entry.get("isSidechain", False)
    }
    order_at = [-1] * len(entries)
    for position, uuid in enumerate(order):
        order_at[index_of[uuid]] = position
    later_min = [len(order)] * (len(entries) + 1)
    for index in range(len(entries) - 1, -1, -1):
        position = order_at[index]
        later_min[index] = position if 0 <= position < later_min[index + 1] else later_min[index + 1]
    return order_at, [0, *accumulate(position >= 0 for position in order_at)], later_min


def _prove_cuts(entries: list[JsonEntry], walk: _ChainWalk | None) -> bytearray | None:
    """Return ``proven[cut]`` for cuts ``0..len(entries)``, or None when the tree fails fact 1.

    A tree that fails fact 1 only because compaction summaries were moved gets an
    all-false array instead of None: nothing is proven, but the snapshot passed the
    checks that make the index ``valid``.

    The steps match the numbered facts in `ClaudeSplitIndex`.
    """
    if walk is None or walk.tree is None or walk.abandons_branch or walk.tree.deferred:
        return None
    tree = walk.tree
    lookup, message_uuids = tree.entry_lookup, tree.message_uuids
    count = len(entries)

    # Fact 1 and totality: dict entries, unique uuids, hashable tool ids.
    index_of: dict[str, int] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not _tool_ids_hashable(entry):
            return None
        uuid = entry.get("uuid")
        if isinstance(uuid, str) and uuid and not entry.get("isSidechain", False):
            if uuid in index_of:
                return None
            index_of[uuid] = index
            _entry_walk_key(entry)
    # A chain whose compaction summaries were moved can be repaired differently in
    # each piece, so none of its cuts follow from the tree facts below: prove none,
    # but stay valid, since the exact checks still cannot raise. Pieces of an
    # unrepaired chain need no repair: each keeps a subsequence of its order.
    if tree.summaries_moved:
        return bytearray(count + 1)
    held = walk.held
    chain = walk.chain if held is None else held.breadth_first
    if len(index_of) != len(lookup) or len(chain) != len(message_uuids) or not _never_prunes(tree):
        return None

    # Facts 2 and 3: difference arrays over cuts 1..count-1.
    hangs_below = [0] * (count + 2)
    crossings = [0] * (count + 2)
    crossing_sum = [0] * (count + 2)
    nearest_message: dict[str, int] = {}

    def nearest_message_index(uuid: object) -> int:
        """File index of the nearest message at or above ``uuid``, or -1; memoised along the path."""
        path = []
        found = -1
        while isinstance(uuid, str) and uuid in lookup:
            if uuid in message_uuids:
                found = index_of[uuid]
                break
            known = nearest_message.get(uuid)
            if known is not None:
                found = known
                break
            path.append(uuid)
            uuid = lookup[uuid].get("parentUuid")
        for item in path:
            nearest_message[item] = found
        return found

    for uuid, index in index_of.items():
        parent = lookup[uuid].get("parentUuid")
        if not (isinstance(parent, str) and parent in lookup):
            continue
        parent_index = index_of[parent]
        if parent_index > index:
            hangs_below[index + 1] += 1
            hangs_below[parent_index + 1] -= 1
        if uuid in message_uuids:
            ancestor = nearest_message_index(parent)
            if 0 <= ancestor < index:
                crossings[ancestor + 1] += 1
                crossings[index + 1] -= 1
                crossing_sum[ancestor + 1] += index
                crossing_sum[index + 1] -= index
    for segment_root, owner_leaf in tree.segment_back_links.items():
        root_index, leaf_index = index_of[segment_root], index_of[owner_leaf]
        if leaf_index > root_index:
            hangs_below[root_index + 1] += 1
            hangs_below[leaf_index + 1] -= 1

    # Fact 4: chain position of every message, by file index.
    position_of = {entry["uuid"]: position for position, entry in enumerate(chain)}
    chain_position = [-1] * count
    for uuid, position in position_of.items():
        chain_position[index_of[uuid]] = position
    later_min = [len(chain)] * (count + 1)
    for index in range(count - 1, -1, -1):
        position = chain_position[index]
        later_min[index] = position if 0 <= position < later_min[index + 1] else later_min[index + 1]

    # Fact 5: roots in walk order with their effective sort key (stable sort over file order).
    roots = tree.roots
    root_keys = [(_entry_walk_key(root), index_of[root["uuid"]]) for root in roots]
    root_file_indexes = sorted(key[1] for key in root_keys)

    # Fact 6: a redelivery pair straddles every split of the chain between its two positions.
    straddling = [0] * (len(chain) + 2)
    for command, redelivery in _queued_command_redeliveries(chain):
        straddling[command + 1] += 1
        straddling[redelivery + 1] -= 1
    straddled = list(accumulate(straddling))

    clock = walk.clock or {}
    held_failures = (
        _held_walk_failures(count, held, clock, index_of, chain_position, tree) if held is not None else None
    )
    # Fact 10: the clock can rule out every late prompt, leaving nothing held; it binds the cuts all the same.
    clock_failures = _clock_failures(count, clock, index_of, lookup) if clock else None

    proven = bytearray(count + 1)
    proven[0] = 1
    proven[count] = 1
    hanging = crossing = crossing_total = 0
    earlier_max = -1
    messages_before = 0
    roots_before = 0
    for cut in range(1, count):
        hanging += hangs_below[cut]
        crossing += crossings[cut]
        crossing_total += crossing_sum[cut]
        position = chain_position[cut - 1]
        if position >= 0:
            messages_before += 1
            earlier_max = max(earlier_max, position)
        while roots_before < len(root_file_indexes) and root_file_indexes[roots_before] < cut:
            roots_before += 1
        # With fact 4, the chain's first messages_before messages are exactly those before the cut.
        if hanging or crossing > 1 or earlier_max >= later_min[cut] or straddled[messages_before]:
            continue
        if (held_failures is not None and held_failures[cut]) or (clock_failures is not None and clock_failures[cut]):
            continue
        # With fact 4, the roots before the cut are exactly the first roots_before in walk order.
        if crossing == 1 and roots_before < len(roots):
            crossing_entry = entries[crossing_total]
            if (_entry_walk_key(crossing_entry), crossing_total) >= root_keys[roots_before]:
                continue
        proven[cut] = 1
    return proven


def _clock_failures(count: int, clock: _Clock, index_of: dict[str, int], lookup: dict[str, JsonEntry]) -> bytearray:
    """Mark each cut that fails fact 10 by ``clock``, what the walk's clock recorded.

    An entry and what dates it fall in the same piece. A suffix holding that
    ancestor holds the path from it down (fact 2), so it dates the entry the
    same; a suffix holding that prompt holds every entry between the two, so
    no newer prompt written before the entry is missing from it either. A
    prefix holds everything written before its entries. This holds whether or
    not the walk then held anything back: without the entry that dates it, a
    piece could find a prompt late that the whole file does not.
    """
    spans = [0] * (count + 2)
    for uuid, index in index_of.items():
        above = clock.get(uuid)
        if above is not None and _written_age(lookup[uuid]) < above[0] and index_of[above[1]] < index:
            spans[index_of[above[1]] + 1] += 1
            spans[index + 1] -= 1
    return bytearray(depth > 0 for depth in accumulate(spans[: count + 1]))


def _held_walk_failures(
    count: int,
    held_walk: _HeldWalk,
    clock: _Clock,
    index_of: dict[str, int],
    chain_position: list[int],
    tree: _WalkTree,
) -> bytearray:
    """Mark each cut that fails fact 7, 8 or 9 in some holding round of ``held_walk``, or fact 6 in the last.

    ``clock`` is what the walk's breadth-first walk recorded, ``index_of`` maps
    each walked uuid to its file index and ``chain_position`` each file index
    to its breadth-first chain position (-1 for non-messages).
    """
    lookup, message_uuids = tree.entry_lookup, tree.message_uuids
    failed = bytearray(count + 1)
    leads_to_message = _leading_to_messages(tree)
    first = held_walk.rounds[0]
    entry_at = {index: uuid for uuid, index in index_of.items()}
    messages_before = [0, *accumulate(position >= 0 for position in chain_position)]

    def parent_index(uuid: str) -> int | None:
        parent = lookup[uuid].get("parentUuid")
        return index_of[parent] if isinstance(parent, str) and parent in index_of else None

    # Fact 8's crossing entries depend only on the tree: every round visits the same entries.
    crossing_cuts = [0] * (count + 2)
    crossing_sum = [0] * (count + 2)
    for uuid in first.emitted:
        if uuid not in leads_to_message:
            continue
        index, parent = index_of[uuid], parent_index(uuid)
        if parent is not None and parent < index:
            crossing_cuts[parent + 1] += 1
            crossing_cuts[index + 1] -= 1
            crossing_sum[parent + 1] += index
            crossing_sum[index + 1] -= index
    crossing = list(accumulate(crossing_cuts))
    crossing_index = list(accumulate(crossing_sum))
    starting_chain = held_walk.breadth_first
    for hold_round in held_walk.rounds:
        # Fact 7: a running maximum of walk positions before each cut against a suffix minimum after it.
        emitted_at = [-1] * count
        for position, uuid in enumerate(hold_round.emitted):
            if uuid in leads_to_message:
                emitted_at[index_of[uuid]] = position
        later = len(hold_round.emitted)
        later_emitted = [later] * (count + 1)
        for index in range(count - 1, -1, -1):
            if 0 <= emitted_at[index] < later:
                later = emitted_at[index]
            later_emitted[index] = later
        earlier = -1
        held_indexes = sorted(index_of[uuid] for uuid in hold_round.held)
        next_held = 0
        # Fact 9: a piece flags a late prompt only with its first witness, so no cut may fall between
        # them; and it dates a redelivery by its command only with both, so fact 6 holds here too.
        between = [0] * (len(starting_chain) + 2)
        for prompt, witness in _late_prompt_witnesses(starting_chain, clock):
            between[prompt + 1] += 1
            between[witness + 1] -= 1
        for command, redelivery in _queued_command_redeliveries(starting_chain):
            between[command + 1] += 1
            between[redelivery + 1] -= 1
        separates = list(accumulate(between))
        for cut in range(1, count):
            earlier = max(earlier, emitted_at[cut - 1])
            while next_held < len(held_indexes) and held_indexes[next_held] < cut:
                next_held += 1
            held_after = len(held_indexes) - next_held
            before = messages_before[cut]
            if (
                earlier >= later_emitted[cut]
                or (
                    held_after
                    and (
                        crossing[cut] > 1 or (crossing[cut] == 1 and entry_at[crossing_index[cut]] not in message_uuids)
                    )
                )
                or separates[before]
            ):
                failed[cut] = 1
        starting_chain = hold_round.chain
    # Fact 6 in the chain that is deduplicated: holding can bring a redelivery before the
    # assistant reply that used to clear its queued command. With fact 7, the first
    # messages_before[cut] messages of that chain are the ones before the cut.
    straddling = [0] * (len(starting_chain) + 2)
    for command, redelivery in _queued_command_redeliveries(starting_chain):
        straddling[command + 1] += 1
        straddling[redelivery + 1] -= 1
    straddled = list(accumulate(straddling))
    for cut in range(count + 1):
        if straddled[messages_before[cut]]:
            failed[cut] = 1
    return failed


def _leading_to_messages(tree: _WalkTree) -> set[str]:
    """Every uuid with a message at or below it, climbing from each message until an entry already found."""
    found: set[str] = set()
    for uuid in tree.message_uuids:
        current: object = uuid
        while isinstance(current, str) and current in tree.entry_lookup and current not in found:
            found.add(current)
            current = tree.entry_lookup[current].get("parentUuid")
    return found


def _tool_ids_hashable(entry: JsonEntry) -> bool:
    """Whether ``trim_incomplete_tail`` can put this entry's tool ids in a set (JSON lists and objects cannot)."""
    message_type = entry.get("type")
    if message_type not in ("assistant", "user"):
        return True
    message = entry.get("message", {})
    content = message.get("content", []) if isinstance(message, dict) else []
    if not isinstance(content, list):
        return True
    key = "id" if message_type == "assistant" else "tool_use_id"
    block_type = "tool_use" if message_type == "assistant" else "tool_result"
    return not any(
        isinstance(block, dict) and block.get("type") == block_type and isinstance(block.get(key, ""), (list, dict))
        for block in content
    )


def _never_prunes(tree: _WalkTree) -> bool:
    """Fact 1: no piece of this file can make the walk prune a branch or meet a cycle.

    A walk prunes siblings when two or more of them start with different user
    prompts. A message child always starts its own branch, so only its own
    prompt counts. A non-message child starts with whichever message its piece
    of the subtree reaches first, which can be any message below it, so any
    user prompt in its subtree counts. Rewound first prompts among roots are
    already ruled out, because the whole walk did not prune.
    """
    lookup, message_uuids, children = tree.entry_lookup, tree.message_uuids, tree.children
    for entry in lookup.values():
        back_link = entry.get("logicalParentUuid")
        parent = entry.get("parentUuid")
        # A compaction link below a parent could be found or missed depending on the cut.
        if isinstance(back_link, str) and back_link and isinstance(parent, str) and parent in lookup:
            return False
    tops = [
        uuid
        for uuid, entry in lookup.items()
        if not (isinstance(entry.get("parentUuid"), str) and entry["parentUuid"] in lookup)
    ]
    order: list[str] = []
    seen: set[str] = set()
    stack = list(tops)
    while stack:
        uuid = stack.pop()
        if uuid in seen:
            return False
        seen.add(uuid)
        order.append(uuid)
        stack.extend(child["uuid"] for child in children.get(uuid, ()))
    if len(seen) != len(lookup):
        return False  # entries on a parent cycle are unreachable from any top
    has_prompt: dict[str, bool] = {}
    for uuid in reversed(order):
        subtree_prompt = uuid in message_uuids and bool(_user_entry_text_key(lookup[uuid]))
        fixed_keys: set[tuple[str, ...]] = set()
        fixed = open_heads = 0
        for child in children.get(uuid, ()):
            child_uuid = child["uuid"]
            subtree_prompt = subtree_prompt or has_prompt[child_uuid]
            if child_uuid in message_uuids:
                key = _user_entry_text_key(child)
                if key:
                    fixed_keys.add(key)
                    fixed += 1
            elif has_prompt[child_uuid]:
                open_heads += 1
        if fixed + open_heads >= 2 and not (open_heads == 0 and len(fixed_keys) == 1):
            return False
        has_prompt[uuid] = subtree_prompt
    return True
