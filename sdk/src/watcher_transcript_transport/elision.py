"""Cap very large tool outputs in native transcript entries, identically for every uploader and the server.

A tool output can be far larger than anything that grades it or shows it: a
log or a file read of tens of megabytes. One such entry can exceed a bounded
upload request on its own, so the upload could never pass it. Watcher
therefore caps an output of more than `TOOL_OUTPUT_CAP_CHARS` characters,
counting all its text blocks together when it has several: it
first replaces any image embedded in its text with a short marker, as graders
do before judging a text's length, and if the text is still too long keeps its
start and end with the middle replaced by a marker naming how much was removed
and the SHA-256 of the text it was removed from, so two outputs that differ
only in their middle stay distinct. An output embedding more than one image per
`_MIN_CHARS_PER_IMAGE` characters keeps its images and is cut as it is: each
marker costs a hash and is longer than a tiny image, so replacing them all
would cost far more than the output's size, and the server caps outputs while
it validates a request.

Every path applies `elide_entry` to raw entries: the server's request models
for full uploads, appends and hook requests, and the client's transcript
readers. Stored messages are hashed from their content, so the cap must be
the same everywhere, and it is idempotent: an output it already capped is
left as it is, so a client that capped an entry and one that did not produce
the same stored message.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from typing import Any

from watcher_transcript_transport.images import count_images, is_image_payload, replace_images

__all__ = ["TOOL_OUTPUT_CAP_CHARS", "elide_entry", "elide_text"]

# One parsed JSONL record, as the transport's readers produce it.
JsonEntry = dict[str, Any]

# The most characters of one tool output that are kept. Graders already see an
# output this long only as a short excerpt, and it stays far below a bounded
# upload request even at four UTF-8 bytes per character.
TOOL_OUTPUT_CAP_CHARS = 100_000
# A capped output keeps this much of its end; the rest of the cap is its start.
_KEPT_END_CHARS = TOOL_OUTPUT_CAP_CHARS // 4
# The marker's longest form fits in this, so a capped output is never capped again.
_MARKER_SLACK_CHARS = 256
# Images are replaced only when an output embeds at most one per this many characters,
# which keeps the work proportional to the output's size (see the module docstring).
_MIN_CHARS_PER_IMAGE = 1_000

_COPILOT_OUTPUT_PATHS = (
    ("data", "result", "content"),
    ("data", "result", "detailedContent"),
    ("data", "error", "message"),
)


def elide_text(text: str) -> str:
    """``text`` capped when it is longer than the cap; otherwise ``text`` itself.

    Images embedded in the text go first, each replaced by a short marker, the
    way graders drop them before judging a text's length (both recognize images
    by `watcher_transcript_transport.images`), unless there are too many of them
    (`_few_enough_images`). Only when the text is still too long is its middle
    replaced by a marker, keeping its start and end. Either way the result is
    never longer than the cap plus its markers, so capping it again leaves it as
    it is.
    """
    if len(text) <= TOOL_OUTPUT_CAP_CHARS + _MARKER_SLACK_CHARS:
        return text
    if _few_enough_images([text]):
        text = replace_images(text, _image_marker)
        if len(text) <= TOOL_OUTPUT_CAP_CHARS + _MARKER_SLACK_CHARS:
            return text
    head_end = TOOL_OUTPUT_CAP_CHARS - _KEPT_END_CHARS
    tail_start = len(text) - _KEPT_END_CHARS
    marker = _removed_marker(tail_start - head_end, [text])
    return f"{text[:head_end]}\n\n{marker}\n\n{text[tail_start:]}"


def _few_enough_images(texts: list[str]) -> bool:
    """Whether ``texts`` together embed at most one image per `_MIN_CHARS_PER_IMAGE` characters.

    Counting stops one past that limit (`count_images`), so the check costs at
    most a scan of the text.
    """
    limit = sum(len(text) for text in texts) // _MIN_CHARS_PER_IMAGE
    found = 0
    for text in texts:
        found += count_images(text, limit - found)
        if found > limit:
            return False
    return True


def _removed_marker(removed: int, texts: list[str]) -> str:
    """The marker in place of ``removed`` characters cut from ``texts``, naming the SHA-256 of them joined by newlines."""
    digest = hashlib.sha256("\n".join(texts).encode("utf-8", "surrogatepass")).hexdigest()
    return f"[Watcher removed {removed} characters from the middle of this tool output; sha256 {digest}]"


def _image_marker(payload: str, mime: str) -> str:
    """The short marker an embedded image is replaced with, naming its type, size and the SHA-256 of its text."""
    digest = hashlib.sha256(payload.encode("ascii", "replace")).hexdigest()
    return f"[Watcher removed an embedded {mime} image of {len(payload)} characters; sha256 {digest}]"


def _elide_output(value: Any) -> Any:
    """A tool output with its text capped: a string, or a list of content blocks whose text is capped as one text.

    See `_cut_text_blocks` for a list. Anything else, an image block's data
    included, is left as it is. Returns ``value`` itself when nothing changed.
    """
    if isinstance(value, str):
        return elide_text(value)
    if not isinstance(value, list):
        return value
    return _cut_text_blocks(value)


def _is_text_block(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("text"), str)


def _cut_text_blocks(blocks: list[Any]) -> list[Any]:
    """``blocks`` with their text blocks capped as one text, or ``blocks`` itself when they are within the cap.

    A tool output split into blocks is one output, so its blocks' text is read
    in order as one text and capped the way `elide_text` caps one: images
    embedded in it go first, unless there are too many of them
    (`_few_enough_images`), and if it is still too long its first
    ``TOOL_OUTPUT_CAP_CHARS - _KEPT_END_CHARS`` and last ``_KEPT_END_CHARS``
    characters are kept, around a marker naming how much was removed and the
    SHA-256 of the blocks' text joined by newlines. A block holding the whole
    removed middle is cut in place, so a single block comes out exactly as
    `elide_text` would cut its text. Otherwise a block straddling either point
    is cut there, text blocks wholly between them are dropped, and one text
    block holds the marker. Other blocks keep their places. The result's text
    is within the cap plus the marker, so capping it again leaves it as it is.
    """
    if (
        sum(len(block["text"]) for block in blocks if _is_text_block(block))
        <= TOOL_OUTPUT_CAP_CHARS + _MARKER_SLACK_CHARS
    ):
        return blocks
    if _few_enough_images([block["text"] for block in blocks if _is_text_block(block)]):
        blocks = [
            {**block, "text": text}
            if _is_text_block(block) and (text := replace_images(block["text"], _image_marker)) is not block["text"]
            else block
            for block in blocks
        ]
    texts = [block["text"] for block in blocks if _is_text_block(block)]
    total = sum(len(text) for text in texts)
    if total <= TOOL_OUTPUT_CAP_CHARS + _MARKER_SLACK_CHARS:
        return blocks
    head_end = TOOL_OUTPUT_CAP_CHARS - _KEPT_END_CHARS
    tail_start = total - _KEPT_END_CHARS
    marker = _removed_marker(tail_start - head_end, texts)
    cut: list[Any] = []
    placed = False
    offset = 0
    for block in blocks:
        if not _is_text_block(block):
            cut.append(block)
            continue
        text = block["text"]
        start, offset = offset, offset + len(text)
        if offset <= head_end or start >= tail_start:
            cut.append(block)
            continue
        head = text[: max(head_end - start, 0)]
        tail = text[tail_start - start :] if offset > tail_start else ""
        if start < head_end and offset > tail_start:
            cut.append({**block, "text": f"{head}\n\n{marker}\n\n{tail}"})
            continue
        if head:
            cut.append({**block, "text": head})
        if not placed:
            cut.append({"type": block.get("type", "text"), "text": marker})
            placed = True
        if tail:
            cut.append({**block, "text": tail})
    return cut


# Fields of Claude Code's ``toolUseResult`` record under which an image's encoded bytes sit. Tools
# may put text under the same names, so only a value that is itself encoded bytes is exempt.
_IMAGE_FIELDS = frozenset({"base64", "data", "image_url", "source"})


def _elide_record_strings(value: Any, hot: set[int], in_image_field: bool = False) -> Any:
    """``value`` with every string in it capped except image data, rebuilt only where something changed.

    For Claude Code's ``toolUseResult``, a copy of the output the server never
    hashes, whose shape varies by tool, and for a tool search's definitions. A
    list's text blocks are capped together as one text, as in the output itself
    (`_cut_text_blocks`). A string at or below one of `_IMAGE_FIELDS` is left
    whole only when it is image data (`is_image_payload`: a data URI, or base64
    with an image signature); text, or other base64, there is capped like any
    other. Only the lists and dictionaries in ``hot`` (`_survey`) are read: any
    other is returned as it is, however large.
    """
    if isinstance(value, str):
        return value if in_image_field and is_image_payload(value) else elide_text(value)
    if id(value) not in hot:
        return value
    if isinstance(value, list):
        items = [item if _is_text_block(item) else _elide_record_strings(item, hot, in_image_field) for item in value]
        items = _cut_text_blocks(items)
        changed = len(items) != len(value) or any(new is not old for new, old in zip(items, value, strict=True))
        return items if changed else value
    assert isinstance(value, dict)
    fields = {
        key: _elide_record_strings(item, hot, in_image_field or key in _IMAGE_FIELDS) for key, item in value.items()
    }
    return fields if any(fields[key] is not value[key] for key in value) else value


# The most text a ``toolUseResult`` record may still hold once each of its strings is capped:
# room for several capped outputs, far more than any one tool's record carries.
_RECORD_TEXT_BUDGET_CHARS = 4 * TOOL_OUTPUT_CAP_CHARS
# A field of an over-budget record holding at most this much text is kept, capped: an ID, a
# status, a type, usage counts, a file path. Only larger fields give way to markers.
_RECORD_KEPT_FIELD_CHARS = TOOL_OUTPUT_CAP_CHARS // 10


# Lists and dictionaries nested deeper than this, counting the record or definition itself as level
# one, are not walked. Each walk recurses once per level, and a limit set by the data rather than by
# the caller's stack gives the same result in every process that caps it. Real tool records and
# definitions nest a few levels deep. A caller whose own stack is already too close to the
# interpreter's recursion limit to walk this far gets the same fixed marker rather than an error.
_MAX_DEPTH = 128


class _TooDeep(Exception):
    """A list or dictionary sits deeper than `_MAX_DEPTH` levels."""


# Text counts of a record's lists and dictionaries, by object identity and whether they sit under an image field.
_TextCounts = dict[tuple[int, bool], int]

# The JSON values that hold no text: numbers, booleans and null.
_NON_TEXT_SCALARS = frozenset({int, float, bool, type(None)})


def _survey(
    value: list[Any] | dict[str, Any],
    hot: set[int],
    counts: _TextCounts,
    in_image_field: bool = False,
    depth: int = 1,
) -> int:
    """The characters of text in ``value``, image data aside, noting what capping its strings would change.

    Adds to ``hot`` each list and dictionary that `_elide_record_strings` must
    read: one holding a string over the cap that is not image data, a list
    whose text blocks are over it together, or one holding such a list or
    dictionary. Records in ``counts`` the text of each one holding more than
    `_RECORD_KEPT_FIELD_CHARS`, the only totals that shrinking the record, or
    checking its budget once capped, may need again: capping returns each part
    it did not change as it was. This one pass reads each string once, so a
    large record with nothing to cap costs a single walk, and capping one
    rebuilds only the parts that change.

    Raises `_TooDeep` when a list or dictionary sits deeper than `_MAX_DEPTH`.
    """
    if depth > _MAX_DEPTH:
        raise _TooDeep
    over = TOOL_OUTPUT_CAP_CHARS + _MARKER_SLACK_CHARS
    is_list = isinstance(value, list)
    if is_list and value and not in_image_field and not isinstance(value[0], (list, dict)):
        # A list of scalars only is read without a step per item. The first item is checked first so
        # that the many lists of containers in other records pay almost nothing for this.
        kinds = set(map(type, value))
        if kinds <= _NON_TEXT_SCALARS:
            return 0
        if kinds == {str}:
            # Such as file names or a patch's lines: no image data and no text blocks.
            lengths = list(map(len, value))
            total = sum(lengths)
            if max(lengths) > over:
                hot.add(id(value))
            if total > _RECORD_KEPT_FIELD_CHARS:
                counts[(id(value), in_image_field)] = total
            return total
    total = blocks = 0
    found = False
    for key, child in enumerate(value) if is_list else value.items():
        if isinstance(child, str):
            # Image data is neither text nor capped. A list's indexes are integers, never a field name.
            if (in_image_field or key in _IMAGE_FIELDS) and is_image_payload(child):
                continue
            total += len(child)
            if len(child) > over:
                found = True
        elif isinstance(child, (list, dict)):
            total += _survey(child, hot, counts, in_image_field or key in _IMAGE_FIELDS, depth + 1)
            if id(child) in hot:
                found = True
            if is_list and isinstance(child, dict) and isinstance(text := child.get("text"), str):
                blocks += len(text)
    if found or blocks > over:
        hot.add(id(value))
    if total > _RECORD_KEPT_FIELD_CHARS:
        counts[(id(value), in_image_field)] = total
    return total


def _record_text_chars(value: Any, *, in_image_field: bool = False, counts: _TextCounts | None = None) -> int:
    """The characters of every string in ``value``, not counting image data left whole.

    ``counts`` holds totals `_survey` already found for this record, which are
    read rather than counted again.
    """
    if isinstance(value, str):
        return 0 if in_image_field and is_image_payload(value) else len(value)
    if not isinstance(value, (list, dict)):
        return 0
    if counts is not None and (id(value), in_image_field) in counts:
        return counts[(id(value), in_image_field)]
    # Loops rather than sums over generators, so each level costs one frame on every interpreter.
    total = 0
    if isinstance(value, list):
        for item in value:
            total += _record_text_chars(item, in_image_field=in_image_field, counts=counts)
        return total
    for field, item in value.items():
        total += _record_text_chars(item, in_image_field=in_image_field or field in _IMAGE_FIELDS, counts=counts)
    return total


def _written(value: Any) -> str:
    """``value`` as compact JSON, the form each marker's SHA-256 is taken over."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _removed_record_marker(
    value: Any, what: str, in_image_field: bool = False, counts: _TextCounts | None = None
) -> str:
    """The marker in place of ``value``: how much text it held, image data aside, and the SHA-256 of it as written.

    ``in_image_field`` says ``value`` sits at or below one of `_IMAGE_FIELDS`, so bare image data in it is not text.
    ``counts`` is `_survey`'s, for a record already surveyed.
    """
    digest = hashlib.sha256(_written(value).encode("utf-8", "surrogatepass")).hexdigest()
    held = _record_text_chars(value, in_image_field=in_image_field, counts=counts)
    return f"[Watcher removed {what}, {held} characters of text; sha256 {digest}]"


def _shrink_record_fields(value: Any, hot: set[int], counts: _TextCounts, in_image_field: bool = False) -> Any:
    """``value``, a record over the budget, with each small field kept capped and each large one replaced.

    A field holding at most `_RECORD_KEPT_FIELD_CHARS` of text, image data
    aside, is kept as `_elide_record_strings` caps it, so short metadata
    survives wherever it sits in the record. A larger field that is itself a
    record is shrunk the same way; any other larger field becomes a marker.
    ``hot`` and ``counts`` are `_survey`'s for the record, so each level reads
    the totals already found rather than counting its fields again.
    """
    if not isinstance(value, dict):
        return _removed_record_marker(value, "this field", in_image_field, counts)
    fields: dict[str, Any] = {}
    for key, item in value.items():
        image_field = in_image_field or key in _IMAGE_FIELDS
        if _record_text_chars(item, in_image_field=image_field, counts=counts) <= _RECORD_KEPT_FIELD_CHARS:
            fields[key] = _elide_record_strings(item, hot, image_field)
        else:
            fields[key] = _shrink_record_fields(item, hot, counts, image_field)
    return fields


def _elide_record(record: Any) -> Any:
    """Claude Code's ``toolUseResult`` record capped string by string, its large fields replaced if that is not enough.

    Capping each string (`_elide_record_strings`) bounds one long output, not
    a record made of many strings: a list of strings each just under the cap,
    many fields, or a patch of many short lines. When the capped record still
    holds more than `_RECORD_TEXT_BUDGET_CHARS` of text, image data aside, its
    large fields are replaced by markers and its small ones kept
    (`_shrink_record_fields`): the client reads short fields of this record (a
    subagent's ``agentId``, a rejection message), and the server reads none of
    it. A record that has no fields, or is still over the budget, is replaced
    whole by one marker. Each marker names how much text it replaced and the
    SHA-256 of that text as written.

    A record nesting lists or dictionaries more than `_MAX_DEPTH` levels deep
    is replaced by a fixed marker without being walked or written out, so
    every process that caps it gets the same result, rather than failing the
    whole entry. So is any record when the caller's own stack is too close to
    the interpreter's recursion limit to walk it.
    """
    if not isinstance(record, (list, dict)):
        return elide_text(record) if isinstance(record, str) else record
    try:
        return _elide_shallow_record(record)
    except (_TooDeep, RecursionError):
        return _TOO_DEEP_RECORD_MARKER


def _elide_shallow_record(record: list[Any] | dict[str, Any]) -> Any:
    """`_elide_record` for a list or dictionary, raising `_TooDeep` on finding one nested past `_MAX_DEPTH`."""
    hot: set[int] = set()
    counts: _TextCounts = {}
    chars = _survey(record, hot, counts)
    if hot:
        capped = _elide_record_strings(record, hot)
        if _record_text_chars(capped, counts=counts) <= _RECORD_TEXT_BUDGET_CHARS:
            return capped
    elif chars <= _RECORD_TEXT_BUDGET_CHARS:
        return record
    if isinstance(record, dict):
        shrunk = _shrink_record_fields(record, hot, counts)
        if _record_text_chars(shrunk, counts=counts) <= _RECORD_TEXT_BUDGET_CHARS:
            return shrunk
    return _removed_record_marker(record, "this tool result's structured copy", counts=counts)


_TOO_DEEP_RECORD_MARKER = "[Watcher removed this tool result's structured copy, nested too deeply to read]"


def elide_entry(entry: JsonEntry) -> JsonEntry:
    """``entry`` with its tool outputs capped, or ``entry`` itself when none is over the cap.

    Recognizes each agent's tool-output fields by the entry's own shape:

    - Claude Code: the ``content`` of each ``tool_result`` block in
      ``message.content``, and the ``toolUseResult`` record copied beside it
      (`_elide_record`).
    - Codex: the ``output`` of any response item, which the server reads as a
      tool result wherever it is carried, and the ``tools`` a
      ``tool_search_output`` found (`_elide_codex_item`); also where a
      compaction's ``replacement_history`` replays them.
    - GitHub Copilot CLI: ``data.result.content`` of a
      ``tool.execution_complete`` event, and ``data.error.message`` of a
      failed one, which the server stores as the call's output; also
      ``data.result.detailedContent``, a fuller copy the server never reads,
      so it cannot carry a large output past the cap into a request.

    Only text is capped (see `_elide_output`); other fields, a tool call's own
    arguments included, are left as they are.
    """
    kind = entry.get("type")
    if kind == "tool.execution_complete":
        for path in _COPILOT_OUTPUT_PATHS:
            entry = _with_path(entry, path)
        return entry
    if kind == "response_item":
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            return entry
        capped = _elide_codex_item(payload)
        return entry if capped is payload else {**entry, "payload": capped}
    if kind == "compacted":
        return _with_replayed_outputs(entry)
    updated = entry
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        blocks = [
            {**block, "content": _elide_output(block["content"])}
            if isinstance(block, dict) and block.get("type") == "tool_result" and "content" in block
            else block
            for block in content
        ]
        if any(
            isinstance(new, dict) and new is not old and new["content"] is not old["content"]
            for new, old in zip(blocks, content, strict=True)
        ):
            assert isinstance(message, dict)
            updated = {**updated, "message": {**message, "content": blocks}}
    if "toolUseResult" in entry:
        result = _elide_record(entry["toolUseResult"])
        if result is not entry["toolUseResult"]:
            updated = {**updated, "toolUseResult": result}
    return updated


def _elide_codex_item(item: JsonEntry) -> JsonEntry:
    """A Codex response item with its tool result capped, or ``item`` itself when nothing changed.

    The server's Codex parser reads a carried ``output`` as the call's result,
    for the output types it knows and for any type it does not, so every
    ``output`` is capped (`_elide_output`). A ``tool_search_output`` carries its
    result as ``tools``, the tool definitions it found, which the server stores
    as JSON text; that list is capped as one output (`_cut_tool_definitions`).
    """
    if item.get("type") != "tool_search_output":
        return _with_path(item, ("output",))
    tools = item.get("tools")
    if not isinstance(tools, list):
        return item
    capped = _cut_tool_definitions(tools)
    return item if capped is tools else {**item, "tools": capped}


def _indentation_chars(value: Any, level: int) -> int:
    """The characters indenting ``value``, nested ``level`` levels deep, adds to its compact JSON (`_written`).

    The server stores a tool search's definitions as
    ``json.dumps(tools, indent=2, ensure_ascii=False)``. Against compact JSON,
    that puts each member of
    a non-empty list or dictionary at level ``L`` on a line of its own, indented
    ``2 * (L + 1)`` spaces, its closing bracket on a line indented ``2 * L``, and
    a space after each key's colon. These are counted rather than written out
    because indentation grows with depth: many short items deep down would be
    stored as many times their size.

    Walks with one iterator per level, so neither depth nor width costs it
    recursion or more than `_MAX_DEPTH` iterators. Raises `_TooDeep` on finding
    a list or dictionary more than `_MAX_DEPTH` levels deep, counting a
    definition as level one.
    """
    if not isinstance(value, (list, dict)):
        return 0
    chars = _opened_chars(value, level)
    pending: list[Iterator[Any]] = [iter(value.values() if isinstance(value, dict) else value)]
    while pending:
        for child in pending[-1]:
            if isinstance(child, (list, dict)):
                depth = level + len(pending)
                if depth > _MAX_DEPTH:
                    raise _TooDeep
                chars += _opened_chars(child, depth)
                pending.append(iter(child.values() if isinstance(child, dict) else child))
                break
        else:
            pending.pop()
    return chars


def _opened_chars(container: list[Any] | dict[str, Any], level: int) -> int:
    """The newlines, indentation and key spaces ``indent=2`` writes for ``container``'s own members at ``level``."""
    members = len(container)
    if not members:
        return 0
    return members * (2 * level + 3) + 2 * level + 1 + (members if isinstance(container, dict) else 0)


def _capped_tool(tool: Any) -> tuple[Any, int]:
    """``tool``, one found definition, with its strings capped, and the characters it then adds as stored.

    A definition's share of the stored list is its rendering one level in and
    the four characters around it: a newline, its indent, and the comma or
    newline after it. That share is exact up to the cap. Past it only the fact
    matters, since such a definition is never kept, so one with nothing to cap
    and more text than the cap reports its text, and one whose compact JSON is
    longer than the cap reports that, rather than being measured as stored.

    A definition nesting lists or dictionaries more than `_MAX_DEPTH` levels
    deep raises `_TooDeep`.
    """
    over = TOOL_OUTPUT_CAP_CHARS + _MARKER_SLACK_CHARS
    hot: set[int] = set()
    chars = _survey(tool, hot, {}) if isinstance(tool, (list, dict)) else 0
    if not hot and chars > over:
        return tool, chars
    capped = _elide_record_strings(tool, hot)
    written = len(_written(capped))
    if written > over:
        return capped, written
    return capped, written + _indentation_chars(capped, 1) + 4


_TOO_DEEP_TOOLS_MARKER = "[Watcher removed this tool search's definitions, nested too deeply to read]"


def _cut_tool_definitions(tools: list[Any]) -> list[Any]:
    """``tools``, a tool search's found definitions, capped as one tool output, or ``tools`` itself when within the cap.

    The list's length is the text the server stores for it (`_indentation_chars`).
    Each definition's strings are capped first, one definition at a time
    (`_capped_tool`). If the list still stores more than `TOOL_OUTPUT_CAP_CHARS`,
    whole definitions are kept from its start while they fit in the first
    ``TOOL_OUTPUT_CAP_CHARS - _KEPT_END_CHARS`` characters and from its end
    within the last ``_KEPT_END_CHARS``, and the definitions between are
    replaced by one marker item naming how many were removed, and the length
    and SHA-256 of them as compact JSON (`_written`).

    Definitions are measured from the start only until the list is known to be
    over the cap, and from the end only while they fit, so a search that found
    very many definitions costs the few it keeps plus one depth check and one
    compact encoding of the rest; no indented text is built.
    A search with any definition nesting lists or dictionaries more than
    `_MAX_DEPTH` levels deep is replaced whole by one fixed marker item,
    without encoding it, so every process that caps it gets the same result.
    So is any search when the caller's own stack is too close to the
    interpreter's recursion limit to read it.
    """
    try:
        return _cut_shallow_tool_definitions(tools)
    except (_TooDeep, RecursionError):
        return [_TOO_DEEP_TOOLS_MARKER]


def _cut_shallow_tool_definitions(tools: list[Any]) -> list[Any]:
    """`_cut_tool_definitions` for definitions within `_MAX_DEPTH`, raising `_TooDeep` on finding one that is not."""
    measured: dict[int, tuple[Any, int]] = {}

    def size(index: int) -> int:
        if index not in measured:
            measured[index] = _capped_tool(tools[index])
        return measured[index][1]

    stored, end = 2, 0
    while end < len(tools) and stored <= TOOL_OUTPUT_CAP_CHARS + _MARKER_SLACK_CHARS:
        stored += size(end)
        end += 1
    if stored <= TOOL_OUTPUT_CAP_CHARS + _MARKER_SLACK_CHARS:
        capped = [measured[index][0] for index in range(len(tools))]
        return tools if all(new is old for new, old in zip(capped, tools, strict=True)) else capped
    # The measured start alone is over the cap, so neither walk can run off the list.
    head, kept = 0, 0
    while kept + size(head) <= TOOL_OUTPUT_CAP_CHARS - _KEPT_END_CHARS:
        kept += size(head)
        head += 1
    tail, kept = len(tools), 0
    while kept + size(tail - 1) <= _KEPT_END_CHARS:
        tail -= 1
        kept += size(tail)
    # Depth is checked before anything is encoded; the definitions measured were surveyed, which checks it.
    _indentation_chars([tools[index] for index in range(head, tail) if index not in measured], 0)
    written = _written(tools[head:tail])
    digest = hashlib.sha256(written.encode("utf-8", "surrogatepass")).hexdigest()
    marker = (
        f"[Watcher removed {tail - head} tool definitions from the middle of this tool search result,"
        f" {len(written)} characters of JSON; sha256 {digest}]"
    )
    return [
        *(measured[index][0] for index in range(head)),
        marker,
        *(measured[index][0] for index in range(tail, len(tools))),
    ]


def _with_replayed_outputs(entry: JsonEntry) -> JsonEntry:
    """A Codex compaction with the tool outputs its ``replacement_history`` replays capped."""
    payload = entry.get("payload")
    history = payload.get("replacement_history") if isinstance(payload, dict) else None
    if not isinstance(history, list):
        return entry
    items = [_elide_codex_item(item) if isinstance(item, dict) else item for item in history]
    if all(new is old for new, old in zip(items, history, strict=True)):
        return entry
    assert isinstance(payload, dict)
    return {**entry, "payload": {**payload, "replacement_history": items}}


def _with_path(entry: JsonEntry, path: tuple[str, ...]) -> JsonEntry:
    """``entry`` with the output under the nested ``path`` capped, copying only the dictionaries on that path."""
    parents: list[dict[str, Any]] = [entry]
    for key in path[:-1]:
        child = parents[-1].get(key)
        if not isinstance(child, dict):
            return entry
        parents.append(child)
    leaf = path[-1]
    if leaf not in parents[-1]:
        return entry
    value = _elide_output(parents[-1][leaf])
    if value is parents[-1][leaf]:
        return entry
    for parent, key in zip(reversed(parents), reversed(path), strict=True):
        value = {**parent, key: value}
    return value
