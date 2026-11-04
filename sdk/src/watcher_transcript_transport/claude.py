"""Claude Code transcript boundaries shared by Watcher ingestion clients.

Claude transcripts are UUID trees rather than simple chronological streams.
These functions reproduce the server parser's stored-message ordering and
identify suffixes or partial tool cycles that cannot be uploaded independently.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any, cast

from watcher_transcript_transport.upload import JsonEntry

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
    to wait for its owner leaf.
    """

    __slots__ = ("entry_lookup", "message_uuids", "children", "roots", "segment_back_links", "deferred")

    def __init__(
        self,
        entry_lookup: dict[str, JsonEntry],
        message_uuids: set[str],
        children: dict[str, list[JsonEntry]],
        roots: list[JsonEntry],
        segment_back_links: dict[str, str],
        deferred: bool,
    ) -> None:
        self.entry_lookup = entry_lookup
        self.message_uuids = message_uuids
        self.children = children
        self.roots = roots
        self.segment_back_links = segment_back_links
        self.deferred = deferred


class _ChainWalk:  # noqa: B903
    """One walk's message chain before queued-command deduplication (see ``_walk_chain``).

    ``tree`` is None when the walk returned early: no messages, or no root
    because every message has a message ancestor (a cycle).
    """

    __slots__ = ("chain", "abandons_branch", "visited", "alternatives", "tree")

    def __init__(
        self,
        chain: list[JsonEntry],
        abandons_branch: bool,
        visited: set[str],
        alternatives: list[_BranchSelection],
        tree: _WalkTree | None,
    ) -> None:
        self.chain = chain
        self.abandons_branch = abandons_branch
        self.visited = visited
        self.alternatives = alternatives
        self.tree = tree

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
    """``_walk_branch`` before queued-command deduplication, keeping the tree it built.

    Keep in sync with ``claude_splits._never_prunes`` and
    ``claude_splits._prove_cuts``: they prove which cuts this walk preserves
    from its rules for pruning rewound siblings, grouping and sorting roots,
    and deferring compaction segments. A new or changed rule here can make
    them prove a cut that is no longer safe, so update their conditions with
    it.
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

    def select(siblings: list[JsonEntry], survivors: list[JsonEntry], key: str) -> list[JsonEntry]:
        if len(siblings) == len(survivors):
            return survivors
        candidates = [
            sibling
            for sibling in siblings
            if (head := _branch_head_message(sibling, children, message_uuids)) is not None
            and _user_entry_text_key(head)
            and not (key.startswith("root:") and _is_compaction_segment_root(sibling))
        ]
        candidate_ids = {candidate["uuid"] for candidate in candidates}
        winner = next(sibling["uuid"] for sibling in survivors if sibling["uuid"] in candidate_ids)
        chosen = choices.get(key, winner)
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

    def walk_from(root: JsonEntry) -> None:
        nonlocal abandons_branch
        queue = deque([root])
        while queue:
            current = queue.popleft()
            uuid = current["uuid"]
            if uuid in visited:
                continue
            visited.add(uuid)
            if uuid in message_uuids:
                chain.append(current)
            next_entries = [child for child in children.get(uuid, []) if child["uuid"] not in visited]
            next_entries.sort(key=_entry_walk_key)
            live_entries = select(
                next_entries,
                _drop_abandoned_rewind_branches(
                    next_entries, children, message_uuids, segments_by_owner, activity_by_uuid
                ),
                uuid,
            )
            abandons_branch = abandons_branch or len(live_entries) < len(next_entries)
            queue.extend(live_entries)

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

    tree = _WalkTree(entry_lookup, message_uuids, children, sorted_roots, segment_back_links, any_deferred)
    return _ChainWalk(chain, abandons_branch, visited, alternatives, tree)


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
    """
    if cursor == 0 or cursor == len(entries):
        return True
    prefix = _live_branch(entries[:cursor])
    suffix = _live_branch(entries[cursor:])
    full = _live_branch(entries)
    return prefix is not None and suffix is not None and full is not None and full.order == prefix.order + suffix.order


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
    seen: set[tuple[str, ...]] = {tuple(live.order)}
    while pending:
        walk = _walk_branch(entries, pending.pop())
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
