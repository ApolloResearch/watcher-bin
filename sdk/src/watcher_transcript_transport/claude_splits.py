"""Answer the upload planner's Claude Code boundary questions for a whole snapshot in one pass.

The planner (`watcher_transcript_transport.incremental`) cuts a transcript into
bounded requests. A Claude Code cut is safe when two independently parsed pieces
keep the whole file's live-branch order (`claude.split_preserves_order`) and the
earlier piece does not end inside a tool cycle (`claude.trim_incomplete_tail`).
Each exact order check walks the conversation tree three times, and the planner
asks about cuts all through the file, so planning a long first upload chunk by
chunk is quadratic in its length.

`ClaudeSplitIndex` walks the tree once and proves, for every cut at once, the
order check true. It only ever proves: a cut it cannot prove still gets the
exact check from the caller, so a missing proof costs time, never correctness.
`TailCompleteness` answers the tool-cycle check for every end of one slice with
a single left fold.
"""

from __future__ import annotations

from itertools import accumulate

from watcher_transcript_transport.claude import (
    _ChainWalk,
    _entry_walk_key,
    _live_chain_walk,
    _queued_command_redeliveries,
    _user_entry_text_key,
    _WalkTree,
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
       uuids, no cycles, no deferred compaction segment, no rewound first
       prompts and no node with two children that could head competing user
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
       entries as deduplicating the whole chain.

    Facts 2, 3 and 6 are counted for all cuts at once with difference arrays
    over each offending interval of cuts; 4 with a running maximum and a
    suffix minimum of chain positions; 5 per cut from the sorted roots.
    """

    __slots__ = ("entries", "count", "valid", "_proven", "_acknowledgement_tail")

    def __init__(self, entries: list[JsonEntry], walk: _ChainWalk | None) -> None:
        """Build from ``walk``, which must be ``_live_chain_walk(entries)`` (see `build`)."""
        self.entries = entries
        self.count = len(entries)
        self._acknowledgement_tail: TailCompleteness | None = None
        try:
            proven = _prove_cuts(entries, walk)
        except Exception:  # noqa: BLE001
            # Any unexpected input shape means the index proves nothing and the
            # planner keeps its exact checks, which handle that input as before.
            proven = None
        self.valid = proven is not None
        self._proven = proven if proven is not None else bytearray()

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

    def acknowledgement_complete(self, end: int) -> bool:
        """``len(trim_incomplete_tail(entries[:end], allow_trailing_assistant_text=True)) == end``."""
        if self._acknowledgement_tail is None:
            self._acknowledgement_tail = TailCompleteness(self.entries, 0, allow_trailing_assistant_text=True)
        return self._acknowledgement_tail.complete(end)


def _prove_cuts(entries: list[JsonEntry], walk: _ChainWalk | None) -> bytearray | None:
    """Return ``proven[cut]`` for cuts ``0..len(entries)``, or None when the tree fails fact 1.

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
    chain = walk.chain
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
        # With fact 4, the roots before the cut are exactly the first roots_before in walk order.
        if crossing == 1 and roots_before < len(roots):
            crossing_entry = entries[crossing_total]
            if (_entry_walk_key(crossing_entry), crossing_total) >= root_keys[roots_before]:
                continue
        proven[cut] = 1
    return proven


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
