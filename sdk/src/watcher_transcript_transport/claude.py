"""Claude Code transcript boundaries shared by Watcher ingestion clients.

Claude transcripts are UUID trees rather than simple chronological streams.
These functions reproduce the server parser's stored-message ordering and
identify suffixes or partial tool cycles that cannot be uploaded independently.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from watcher_transcript_transport.upload import JsonEntry

__all__ = ["delta_needs_full_upload", "trim_incomplete_tail"]


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

    pending_tool_use_ids: set[str] = set()
    last_complete_idx = 0

    for index, entry in enumerate(entries):
        message_type = entry.get("type", "")

        if message_type in ("progress", "file-history-snapshot"):
            continue

        if message_type == "assistant":
            message = entry.get("message", {})
            content = message.get("content", []) if isinstance(message, dict) else []
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        pending_tool_use_ids.add(block.get("id", ""))
            if allow_trailing_assistant_text and not pending_tool_use_ids:
                last_complete_idx = index + 1
            continue

        if message_type == "user":
            message = entry.get("message", {})
            content = message.get("content", []) if isinstance(message, dict) else []
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        pending_tool_use_ids.discard(block.get("tool_use_id", ""))

        if not pending_tool_use_ids:
            last_complete_idx = index + 1

    if last_complete_idx >= len(entries):
        return entries
    return entries[:last_complete_idx]


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
    pending: dict[tuple[str, ...], list[int]] = {}
    dropped: set[int] = set()
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
            dropped.add(matches.pop(0))
    return [entry for index, entry in enumerate(chain) if index not in dropped]


def _parse_event_timestamp(entry: JsonEntry) -> float | None:
    timestamp = entry.get("timestamp")
    if not isinstance(timestamp, str):
        return None
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _entry_walk_key(entry: JsonEntry) -> tuple[bool, float]:
    """Sibling ordering for every tree walk: timestamped entries first, oldest first.

    Entries without a parseable timestamp sort after timestamped siblings.
    Equal keys retain their input order when used with Python's stable sort.
    """
    timestamp = _parse_event_timestamp(entry)
    return timestamp is None, timestamp or 0.0


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
    queue = [branch_root]
    seen: set[str] = set()
    while queue:
        current = queue.pop(0)
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
) -> float | None:
    """Newest message timestamp on this branch, including its owned segments, or None.

    Rewind selection keeps the branch written to most recently, not the branch
    that started latest. Include compaction segments attached by
    ``segments_by_owner`` (owner-leaf UUID to continuing segment roots), even
    though those segments are separate roots in the physical transcript.
    """
    last: float | None = None
    queue = [branch_root]
    seen: set[str] = set()
    while queue:
        current = queue.pop(0)
        uuid = current["uuid"]
        if uuid in seen:
            continue
        seen.add(uuid)
        if uuid in message_uuids:
            timestamp = _parse_event_timestamp(current)
            if timestamp is not None and (last is None or timestamp > last):
                last = timestamp
        queue.extend(child for child in children.get(uuid, []) if child["uuid"] not in seen)
        queue.extend(seg for seg in segments_by_owner.get(uuid, []) if seg["uuid"] not in seen)
    return last


def _drop_abandoned_rewind_branches(
    siblings: list[JsonEntry],
    children: dict[str, list[JsonEntry]],
    message_uuids: set[str],
    segments_by_owner: dict[str, list[JsonEntry]],
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
    survivor_activity = _branch_last_activity(siblings[survivor], children, message_uuids, segments_by_owner)
    for i in contenders[1:]:
        activity = _branch_last_activity(siblings[i], children, message_uuids, segments_by_owner)
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
        survivor_activity = _branch_last_activity(roots[survivor], children, message_uuids, segments_by_owner)
        for i in contenders[1:]:
            activity = _branch_last_activity(roots[i], children, message_uuids, segments_by_owner)
            if survivor_activity is None or (activity is not None and activity >= survivor_activity):
                survivor = i
                survivor_activity = activity
        abandoned_indices.update(i for i in contenders if i != survivor)
    return [root for i, root in enumerate(roots) if i not in abandoned_indices]


# Dependency-free for hook startup, like the records in ``upload``.
class _LiveBranch:  # noqa: B903
    """The server parser's live branch of a Claude UUID tree, as the client replicates it.

    ``order`` holds the uuids of the live branch's messages in the order the
    server stores them; ``abandons_branch`` says whether the walk dropped a
    rewound branch, which the server stores as an extra conversation.
    """

    __slots__ = ("abandons_branch", "order")

    order: list[str]
    abandons_branch: bool

    def __init__(self, order: list[str], abandons_branch: bool) -> None:
        self.order = order
        self.abandons_branch = abandons_branch


def _message_order(entries: list[JsonEntry]) -> list[str] | None:
    """Reproduce the server parser's live-branch message order from a Claude UUID tree.

    ``None`` means the raw tree cannot be ordered safely, and callers must use
    full ingestion rather than trusting an independently parsed suffix.
    """
    branch = _live_branch(entries)
    return None if branch is None else branch.order


def _live_branch(entries: list[JsonEntry]) -> _LiveBranch | None:
    """Walk a Claude UUID tree the way the server parser walks its live branch.

    Besides the order (see ``_message_order``) this reports whether any rewound
    branch was abandoned on the way: at a rewind fork, or between rewound
    versions of a first prompt. The server parser yields every abandoned
    branch as its own conversation, so a delta whose own walk abandons one
    parses to several conversations, which the append endpoint refuses.
    ``None`` means the tree cannot be ordered safely.
    """
    entry_lookup = {
        entry["uuid"]: entry
        for entry in entries
        if isinstance(entry.get("uuid"), str) and entry["uuid"] and not entry.get("isSidechain", False)
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
        and not entry.get("isSidechain", False)
    ]
    if not message_entries:
        return _LiveBranch([], False)

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
            and not entry.get("isSidechain", False)
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
        return _LiveBranch([entry["uuid"] for entry in _drop_redelivered_queued_commands(message_entries)], False)

    roots.sort(key=_entry_walk_key)
    # Ownership resolves against every root (a segment can be owned by an
    # abandoned first-prompt version), so build the map before pruning roots.
    segment_back_links = _segment_back_links(roots, entry_lookup)
    segments_by_owner = _segments_by_owner(segment_back_links, entry_lookup)
    live_roots = _drop_abandoned_root_prompts(
        roots, [root_groups[id(root)] for root in roots], children, message_uuids, segments_by_owner
    )
    abandons_branch = len(live_roots) < len(roots)
    roots = live_roots
    chain: list[JsonEntry] = []
    visited: set[str] = set()

    def walk_from(root: JsonEntry) -> None:
        nonlocal abandons_branch
        queue = [root]
        while queue:
            current = queue.pop(0)
            uuid = current["uuid"]
            if uuid in visited:
                continue
            visited.add(uuid)
            if uuid in message_uuids:
                chain.append(current)
            next_entries = [child for child in children.get(uuid, []) if child["uuid"] not in visited]
            next_entries.sort(key=_entry_walk_key)
            live_entries = _drop_abandoned_rewind_branches(next_entries, children, message_uuids, segments_by_owner)
            abandons_branch = abandons_branch or len(live_entries) < len(next_entries)
            queue.extend(live_entries)

    deferred: list[JsonEntry] = []
    for root in roots:
        owner_leaf = segment_back_links.get(root["uuid"])
        if owner_leaf is not None and owner_leaf not in visited:
            deferred.append(root)
            continue
        walk_from(root)

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
                walk_from(root)
                progressed = True
            else:
                remaining.append(root)
        deferred = remaining

    return _LiveBranch([entry["uuid"] for entry in _drop_redelivered_queued_commands(chain)], abandons_branch)


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
