"""GitHub Copilot CLI event-log boundaries shared by Watcher ingestion clients and the server.

Copilot writes each session to ``events.jsonl``, one JSON event per line. Each
event has a ``type`` and a ``data`` object, and a subagent's events also carry
an ``agentId``. Watcher uploads the log one conversation at a time, and the
server turns the events into messages. This module holds what both sides must
agree on. `read_events` turns lines into events. `stored_events` picks and
shrinks one conversation's events before upload, dropping only what is
redundant or must not travel. `complete_until` says where an
upload may end, `delta_entries` and `delta_needs_full_upload` build appends, and
`snapshot` fingerprints the cursor. Which events become which messages is up to
the server, which reads some events through the same rules: `closes_open_calls`
(with `starts_new_process`), `is_refusal` and `skill_content_id`.

`stored_events` is causal: what it keeps for an event depends only on that
event and the ones before it. It is also idempotent: running it on its own
output changes nothing. So a cursor taken on an earlier read still names a
prefix of a later read, and the server can rerun it on whatever a client sent.

`policy_call` maps Copilot's tools to the Claude Code names Watcher's
deterministic policy uses. Stored calls, transcripts and grader input keep
Copilot's own names and arguments.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Any, NoReturn

from watcher_transcript_transport.upload import JsonEntry, TranscriptSnapshot

__all__ = [
    "MAX_EVENT_BYTES",
    "UNREADABLE_EVENT",
    "closes_open_calls",
    "complete_until",
    "delta_entries",
    "delta_needs_full_upload",
    "is_refusal",
    "policy_call",
    "read_events",
    "skill_content_id",
    "snapshot",
    "starts_new_process",
    "stored_events",
    "wire_safe",
]

# read_events puts an event of this type in place of a line it cannot read.
# Claude Code and Codex uploads skip such lines. The server rebuilds a Copilot
# conversation from its events, so it marks the gap instead of presenting the
# rest as the complete conversation.
UNREADABLE_EVENT = "github_copilot_cli.unreadable_event"
# Tool results are stored whole. A line longer than this becomes an
# `UNREADABLE_EVENT`, so one huge event (Copilot's view tool returns whole files)
# never stops the rest of the session uploading. Uploads go in chunks of about
# 8 MiB (`upload.chunk_ends`) that keep a larger event whole, and the hook
# endpoint accepts requests up to 64 MiB by default.
MAX_EVENT_BYTES = 16 * 1024 * 1024

# Events every conversation keeps: they name the session and mark where a process
# ends or a new one resumes it.
_SESSION_EVENTS = frozenset({"session.start", "session.shutdown", "session.resume"})
# Streaming events whose content Copilot also records in a complete event.
_STREAMING_EVENTS = frozenset({"tool.execution_partial_result", "tool.execution_progress"})
# Telemetry about each model call. A model.* event can repeat the whole request,
# instruction files Copilot injects included, which the conversation's own events
# already carry, so it is dropped like the streaming events.
_TELEMETRY_PREFIX = "model."
# Encrypted reasoning has nothing readable in it. The keys inside each
# ``reasoningBlocks`` block hold copies of the message fields' bytes.
_OPAQUE_REASONING_KEYS = frozenset({"encryptedContent", "reasoningOpaque"})
_OPAQUE_BLOCK_KEYS = frozenset({"signature", "encrypted_content"})
# Events after which nothing pending can still complete: the process ending, or a
# line that could not be read (see `complete_until`). A resume also does when it
# starts a new process (`starts_new_process`).
_CLOSES_EVERYTHING = frozenset({"session.shutdown", UNREADABLE_EVENT})
# Events after which no call still open can return (see `closes_open_calls`).
_ENDS_EVERY_CALL = _CLOSES_EVERYTHING | {"abort"}
# The flags a resume sets when it joins work another process is still running, or
# continues pending work and waits for its results.
_JOINING_FLAGS = ("alreadyInUse", "sessionWasActive", "continuePendingWork")
# Copilot's result types for a call a permission check refused before it ran.
_REFUSAL_CODES = frozenset({"denied", "rejected"})
# How Copilot's refusals begin: "Denied by preToolUse hook: …", "Denied by user via
# preToolUse hook prompt: …" and, when it cannot ask anyone, "Permission denied and
# could not request permission from user".
_REFUSAL_PREFIXES = ("Denied by ", "Permission denied and could not request permission")


def read_events(lines: Iterable[bytes], *, max_event_bytes: int = MAX_EVENT_BYTES) -> list[JsonEntry]:
    """Parse Copilot's log lines into events, one per complete line.

    The last line is skipped until it has its newline, since Copilot may still
    be writing it. Blank lines are skipped too. A complete line that is not an
    event becomes ``{"type": UNREADABLE_EVENT}`` in its place, so one bad line
    never stops recording. That covers broken JSON, a value that is not an
    object, a ``type`` that is not text, another field of the envelope every
    event shares with another type than Copilot writes (`_has_valid_envelope`),
    a line longer than ``max_event_bytes`` counting its newline, and valid JSON
    that `wire_safe` says no upload could carry.
    """
    events: list[JsonEntry] = []
    held: bytes | None = None
    for line in lines:
        if held is not None:
            events.extend(_events_in(held, max_event_bytes))
        held = line
    if held is not None and held.endswith(b"\n"):
        events.extend(_events_in(held, max_event_bytes))
    return events


def _events_in(line: bytes, max_event_bytes: int) -> Iterator[JsonEntry]:
    if not line.strip():
        return
    if len(line) > max_event_bytes:
        yield {"type": UNREADABLE_EVENT}
        return
    try:
        event = json.loads(line, parse_constant=_reject_constant, parse_float=_finite_float)
    except (ValueError, RecursionError):
        yield {"type": UNREADABLE_EVENT}
        return
    if not isinstance(event, dict) or not isinstance(event.get("type"), str) or not _has_valid_envelope(event):
        yield {"type": UNREADABLE_EVENT}
        return
    # Only a line with a surrogate escape can decode to a lone surrogate, and only a
    # line with more brackets than `_MAX_DEPTH` can nest past it, so the walk over
    # the event runs only then.
    nests_deep = line.count(b"[") + line.count(b"{") > _MAX_DEPTH
    if (nests_deep or _SURROGATE_ESCAPE.search(line)) and not wire_safe(event):
        yield {"type": UNREADABLE_EVENT}
        return
    yield event


def _reject_constant(name: str) -> NoReturn:
    raise ValueError(f"{name} is not JSON")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("A number too large to be finite is not JSON")
    return value


# A JSON escape of a UTF-16 surrogate code unit (U+D800 to U+DFFF). A valid pair
# decodes to one character; one left alone decodes to a lone surrogate.
_SURROGATE_ESCAPE = re.compile(rb"\\u[dD][89a-fA-F]")
_LONE_SURROGATE = re.compile("[\ud800-\udfff]")
# The deepest nesting of objects and arrays `wire_safe` accepts, counting the value
# itself as one level. The server's upload models refuse JSON nested past roughly
# 200 levels, request included, which would fail the whole upload; this leaves room
# for the request around an event and is far beyond anything Copilot writes.
_MAX_DEPTH = 128


def wire_safe(value: object) -> bool:
    """Whether a parsed JSON value can travel as JSON: UTF-8 strings, finite numbers and bounded nesting.

    Python's JSON parser accepts a lone UTF-16 surrogate escape and a number such
    as ``1e400`` that overflows to infinity, but no UTF-8 encoder can send the
    first (httpx, Postgres and Pydantic all refuse it) and standard JSON has no
    spelling for the second. It also accepts nesting about a thousand levels
    deep, past what the server's upload models accept, so objects and arrays
    nested more than `_MAX_DEPTH` levels fail too. `read_events` turns such a
    line into a placeholder, and the server applies the same test to what it
    receives.
    """
    stack: list[tuple[object, int]] = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, (dict, list)) and depth > _MAX_DEPTH:
            return False
        if isinstance(item, str):
            if _LONE_SURROGATE.search(item):
                return False
        elif isinstance(item, float):
            if not math.isfinite(item):
                return False
        elif isinstance(item, dict):
            for key, nested in item.items():
                if isinstance(key, str) and _LONE_SURROGATE.search(key):
                    return False
                stack.append((nested, depth + 1))
        elif isinstance(item, list):
            stack.extend((nested, depth + 1) for nested in item)
    return True


# The envelope fields Copilot writes as text on every event.
_ENVELOPE_TEXT_KEYS = ("id", "timestamp", "parentId")


def _has_valid_envelope(event: JsonEntry) -> bool:
    """Whether the fields every event shares have the types the server's upload model requires.

    ``id``, ``timestamp`` and ``parentId`` are text, ``agentId`` is non-empty
    text and ``data`` is an object, each when present and not null. A line with
    another envelope would fail the whole upload, so `read_events` replaces it.
    """
    owner = event.get("agentId")
    data = event.get("data")
    return (
        (owner is None or (isinstance(owner, str) and owner != ""))
        and (data is None or isinstance(data, dict))
        and all(event.get(key) is None or isinstance(event.get(key), str) for key in _ENVELOPE_TEXT_KEYS)
    )


def stored_events(events: Sequence[JsonEntry], agent_id: str | None) -> list[JsonEntry]:
    """Return one conversation's events, shrunk for upload.

    With ``agent_id`` ``None`` this is the parent conversation: events without
    an ``agentId`` (every ``UNREADABLE_EVENT`` placeholder among them) plus every
    ``subagent.*`` lifecycle event, which carries the subagent's ``agentId`` and
    tells the parent which call started it and when it finished. With an ID it
    is that subagent's events. Both keep ``session.start``, ``session.shutdown``
    and ``session.resume``.

    Inline base64 in attachments, binary tool results and ``session.binary_asset``
    events is replaced by Copilot's descriptor for those bytes (see
    `_descriptor`). Encrypted reasoning is dropped. Tool results are kept whole.
    Streaming events (``*_delta``, ``tool.execution_partial_result``,
    ``tool.execution_progress``) and model-call telemetry (``model.*``) are
    dropped. Every other event passes through unchanged, whatever its type. The
    input is never modified.
    """
    return [_shrunk(event) for event in events if _belongs_to(event, agent_id) and not _is_redundant(event)]


def _belongs_to(event: JsonEntry, agent_id: str | None) -> bool:
    kind = event.get("type")
    if kind in _SESSION_EVENTS:
        return True
    owner = event.get("agentId")
    if agent_id is None:
        return owner is None or (isinstance(kind, str) and kind.startswith("subagent."))
    return owner == agent_id


def _is_redundant(event: JsonEntry) -> bool:
    """Whether an event only repeats what other events record: streaming output or model-call telemetry."""
    kind = event.get("type")
    return isinstance(kind, str) and (
        kind.endswith("_delta") or kind in _STREAMING_EVENTS or kind.startswith(_TELEMETRY_PREFIX)
    )


def _shrunk(event: JsonEntry) -> JsonEntry:
    kind = event.get("type")
    data = event.get("data")
    if not isinstance(data, dict):
        return event
    if kind == "assistant.message":
        shrunk = _without_opaque_reasoning(data)
    elif kind == "user.message":
        shrunk = _with_descriptors(data, "attachments")
    elif kind == "tool.execution_complete":
        shrunk = _with_binary_descriptors(data)
    elif kind == "session.binary_asset":
        shrunk = _descriptor(data)
    else:
        return event
    return {**event, "data": shrunk}


def _without_opaque_reasoning(data: JsonEntry) -> JsonEntry:
    shrunk = {key: value for key, value in data.items() if key not in _OPAQUE_REASONING_KEYS}
    reasoning = shrunk.get("reasoningBlocks")
    blocks = reasoning.get("blocks") if isinstance(reasoning, dict) else None
    if isinstance(reasoning, dict) and isinstance(blocks, list):
        shrunk["reasoningBlocks"] = {
            **reasoning,
            "blocks": [
                {key: value for key, value in block.items() if key not in _OPAQUE_BLOCK_KEYS}
                if isinstance(block, dict)
                else block
                for block in blocks
            ],
        }
    return shrunk


def _with_descriptors(data: JsonEntry, key: str) -> JsonEntry:
    items = data.get(key)
    if not isinstance(items, list):
        return data
    return {**data, key: [_descriptor(item) if isinstance(item, dict) else item for item in items]}


def _descriptor(item: JsonEntry) -> JsonEntry:
    """Copilot's descriptor for one attachment, binary result or asset, without its bytes.

    The descriptor names the file, type, size and content hash. Bytes are left
    out: the Analyzer shows them as raw base64, graders cannot read them, and
    they would count against Watcher's request size limit. Inline bytes get the
    identity Copilot gives persisted assets: ``assetId`` is ``sha256:`` plus the
    digest of the bytes, and ``byteLength`` their size. An item without ``data``
    is returned as it is, so a descriptor stays unchanged.
    """
    if "data" not in item:
        return item
    descriptor = {key: value for key, value in item.items() if key != "data"}
    inline = item["data"]
    if isinstance(inline, str):
        raw = _decode_inline(inline)
        if raw is None:
            # The bytes are never recorded, so undecodable data is marked rather than
            # refused; refusing would stop every later recording of this session.
            descriptor.setdefault("omittedReason", "undecodable")
        else:
            descriptor.setdefault("assetId", "sha256:" + hashlib.sha256(raw).hexdigest())
            descriptor.setdefault("byteLength", len(raw))
    return descriptor


def _decode_inline(value: str) -> bytes | None:
    """Decode base64 that may be line-wrapped or carry a ``data:`` URI prefix."""
    if value.startswith("data:") and "," in value:
        value = value.split(",", 1)[1]
    try:
        return base64.b64decode("".join(value.split()), validate=True)
    except (binascii.Error, ValueError):
        return None


def _with_binary_descriptors(data: JsonEntry) -> JsonEntry:
    result = data.get("result")
    if not isinstance(result, dict):
        return data
    return {**data, "result": _with_descriptors(result, "binaryResultsForLlm")}


def complete_until(stored: Sequence[JsonEntry]) -> int:
    """Return the index just past the last event an upload of this conversation may end at.

    ``stored`` is one conversation from `stored_events`. An upload may only end
    where nothing is pending, because the server needs both halves of each pair
    in one parse: a model tool call and its result, a user shell command and its
    output, and an invoked skill and its delivered content. Some events close
    pending items early, so the result cannot stall. An ``abort`` closes open
    calls and skills. So does a subagent's own end in its conversation, since
    its unanswered calls never return; the parent's calls stay open when one
    of its subagents ends. A ``session.shutdown``, or a ``session.resume`` that
    starts a new process, closes everything: nothing from a process can follow
    its shutdown, and Copilot never records a result for a call it interrupted,
    even after resuming. A resume that joins work still running elsewhere leaves
    its calls pending, since their results still arrive. So
    does an ``UNREADABLE_EVENT``: the lost line may have been the result that
    would have closed a call, and waiting for it would stop every later upload.
    If the real result turns up after all, `delta_needs_full_upload` sends the
    whole conversation. A skill also stops pending at the next reply, so a
    skill Copilot never delivers cannot hold back every later upload.

    The result stays 0 until the first reply, an ``assistant.message`` with text
    ``content``. Before that, Copilot's system instructions can still arrive
    ahead of the first prompt, which would reorder the start of the stored
    history. A later event never moves the result back.
    """
    replied = False
    # The agentId on this conversation's own replies: None for the parent.
    speaker: str | None = None
    calls: set[str] = set()
    commands: set[str] = set()
    skills: set[str] = set()
    complete = 0
    for index, event in enumerate(stored):
        kind = event.get("type")
        data = _data(event)
        if kind == "assistant.message":
            replied = replied or _is_reply(event)
            speaker = event.get("agentId")
            skills.clear()
            calls.update(_call_ids(data))
        elif kind == "tool.execution_complete":
            call_id = data.get("toolCallId")
            if isinstance(call_id, str):
                calls.discard(call_id)
                commands.discard(call_id)
        elif kind == "tool.user_requested":
            call_id = data.get("toolCallId")
            if isinstance(call_id, str):
                commands.add(call_id)
        elif kind == "skill.invoked" and isinstance(data.get("content"), str):
            skills.add(skill_content_id(data["content"]))
        elif kind == "skill.context_delivered_ref":
            content_id = data.get("contentId")
            if isinstance(content_id, str):
                skills.discard(content_id)
        elif closes_open_calls(event, speaker):
            calls.clear()
            skills.clear()
            # A user's own shell command outlives an abort or a subagent's end.
            if kind in _CLOSES_EVERYTHING or kind == "session.resume":
                commands.clear()
        if replied and not (calls or commands or skills):
            complete = index + 1
    return complete


def closes_open_calls(event: Mapping[str, Any], speaker: str | None) -> bool:
    """Whether ``event`` ends every call still open in one conversation's events, so none of them returns.

    ``speaker`` is the ``agentId`` on the conversation's own replies, ``None``
    for the parent. An ``abort``, a ``session.shutdown``, an ``UNREADABLE_EVENT``
    and a ``session.resume`` that starts a new process (`starts_new_process`)
    each do. So does a subagent's own ``subagent.completed`` or
    ``subagent.failed`` in its conversation; the parent's calls stay open when
    one of its subagents ends. `complete_until` stops waiting for a call here,
    and the server's converter gives the call its interrupted result here, so
    an upload ending at one of these events leaves nothing for a later one to close.
    """
    kind = event.get("type")
    if kind in _ENDS_EVERY_CALL:
        return True
    if kind in ("subagent.completed", "subagent.failed"):
        return speaker is not None and event.get("agentId") == speaker
    return kind == "session.resume" and starts_new_process(event)


def starts_new_process(event: Mapping[str, Any]) -> bool:
    """Whether a ``session.resume`` starts a new process: none of `_JOINING_FLAGS` is exactly true in its ``data``.

    The old process's open calls then never ran; a resume that joins work still
    running elsewhere leaves them to finish.
    """
    data = event.get("data")
    return not (isinstance(data, dict) and any(data.get(flag) is True for flag in _JOINING_FLAGS))


def is_refusal(code: object, message: str) -> bool:
    """Whether a failed result says a permission check stopped the call before it ran, rather than the tool failing.

    ``code`` and ``message`` are the result's ``error.code`` and
    ``error.message``. A text ``code`` decides: ``denied`` (a hook, policy or
    unattended fallback refused it) or ``rejected`` (refused at Copilot's own
    prompt). Logs without one fall back to the opening words Copilot gives its
    refusals.
    """
    if isinstance(code, str):
        return code in _REFUSAL_CODES
    return message.startswith(_REFUSAL_PREFIXES)


def delta_entries(stored: Sequence[JsonEntry], cursor: int) -> list[JsonEntry]:
    """Build an append's payload: ``stored[cursor:]`` led by the log's own ``session.start``.

    The server parses a delta on its own. The seed tells that parse which
    session it belongs to, without adding a message. Only the first
    ``session.start`` names the log's session, because a handoff can later
    replay another session's start. Everything for cursor 0, nothing when the
    cursor is at the end.
    """
    if cursor <= 0:
        return list(stored)
    suffix = list(stored[cursor:])
    start = next((event for event in stored[:cursor] if event.get("type") == "session.start"), None)
    if not suffix or start is None:
        return suffix
    return [start, *suffix]


def delta_needs_full_upload(stored: Sequence[JsonEntry], cursor: int) -> bool:
    """Return whether the delta after ``cursor`` depends on earlier events, so only a full upload parses the same.

    The server parses a delta as a conversation that has already replied and
    knows nothing earlier. That breaks when no reply comes before the cursor.
    It also breaks when the delta has a result for a call or user command opened
    before the cursor, including a call an abort already closed. Reusing an
    earlier call ID breaks it, and so does delivering a skill invoked only
    before the cursor. A skill delivered with no invocation at all parses the
    same either way. A cursor that `complete_until` would not stop at, such as
    an upload of a conversation whose process died inside a call, breaks it too:
    whatever later closes that call (a resume's interrupted result, or the real
    result) belongs to it. False for cursor 0 and for an empty delta.
    """
    if cursor <= 0 or cursor >= len(stored):
        return False
    if complete_until(stored[:cursor]) < cursor:
        return True
    earlier_calls: set[str] = set()
    earlier_skills: set[str] = set()
    replied = False
    for event in stored[:cursor]:
        kind = event.get("type")
        data = _data(event)
        if kind == "assistant.message":
            replied = replied or _is_reply(event)
            earlier_calls.update(_call_ids(data))
        elif kind == "tool.user_requested" and isinstance(data.get("toolCallId"), str):
            earlier_calls.add(data["toolCallId"])
        elif kind == "skill.invoked" and isinstance(data.get("content"), str):
            earlier_skills.add(skill_content_id(data["content"]))
    if not replied:
        return True
    delta_skills: set[str] = set()
    for event in stored[cursor:]:
        kind = event.get("type")
        data = _data(event)
        if kind == "assistant.message" and not earlier_calls.isdisjoint(_call_ids(data)):
            return True
        if kind == "tool.execution_complete" and data.get("toolCallId") in earlier_calls:
            return True
        if kind == "skill.invoked" and isinstance(data.get("content"), str):
            delta_skills.add(skill_content_id(data["content"]))
        elif kind == "skill.context_delivered_ref":
            content_id = data.get("contentId")
            if content_id in earlier_skills and content_id not in delta_skills:
                return True
    return False


def snapshot(stored: Sequence[JsonEntry]) -> TranscriptSnapshot:
    """Fingerprint each prefix of the stored events for the shared upload cursor.

    Each fingerprint covers every event up to it, as compact sorted-key JSON,
    length-prefixed the way `upload.parse_jsonl_snapshot` does for raw lines.
    A cursor therefore notices any change to the prefix it names.
    """
    digest = hashlib.sha256()
    prefix_hashes: list[str] = []
    for event in stored:
        encoded = json.dumps(event, separators=(",", ":"), sort_keys=True).encode()
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        prefix_hashes.append(digest.hexdigest())
    return TranscriptSnapshot(list(stored), prefix_hashes)


def _data(event: JsonEntry) -> JsonEntry:
    data = event.get("data")
    return data if isinstance(data, dict) else {}


def _is_reply(event: JsonEntry) -> bool:
    return event.get("type") == "assistant.message" and isinstance(_data(event).get("content"), str)


def _call_ids(data: JsonEntry) -> set[str]:
    requests = data.get("toolRequests")
    if not isinstance(requests, list):
        return set()
    return {
        request["toolCallId"]
        for request in requests
        if isinstance(request, dict) and isinstance(request.get("toolCallId"), str) and request["toolCallId"]
    }


def skill_content_id(content: str) -> str:
    """The ``contentId`` a later ``skill.context_delivered_ref`` uses for a ``skill.invoked`` event's ``content``."""
    # A lone surrogate cannot be encoded strictly; passing it through keeps a
    # crafted skill from stopping the scan or the server's parse.
    return "sha256:" + hashlib.sha256(content.encode("utf-8", "surrogatepass")).hexdigest()


# Watcher's built-in command rules and per-tool thresholds name Claude Code's tools
# (Bash, Read, Write, Edit and so on), so deterministic policy judges Copilot's
# tools under those names. A tool that does what a Claude Code tool does gets its
# name, and a file tool's ``path`` becomes ``file_path``. The client gate's local
# rules and the server's Copilot policy table share this one translation; stored
# calls keep Copilot's own names. Each value is the Claude Code name plus the
# native key that holds the file path, if any.
_POLICY_NAMES: dict[str, tuple[str, str | None]] = {
    "bash": ("Bash", None),
    # Copilot lists local_shell beside bash as a native shell and displays it the
    # same way, so it gets Bash too, or a command could miss Bash rules under this name.
    "local_shell": ("Bash", None),
    # The Windows shell gets Claude Code's own PowerShell tool rather than Bash:
    # Watcher's Bash allow rules assume POSIX shell syntax and never allow PowerShell.
    "powershell": ("PowerShell", None),
    "view": ("Read", "path"),
    "create": ("Write", "path"),
    "edit": ("Edit", "path"),
    "glob": ("Glob", None),
    "grep": ("Grep", None),
    "web_fetch": ("WebFetch", None),
    "web_search": ("WebSearch", None),
    "rg": ("Grep", None),
    "task": ("Agent", None),
    "skill": ("Skill", None),
    "ask_user": ("AskUserQuestion", None),
}

# Tools that type text into a running shell, and the shell tool that text is judged as.
_TYPED_SHELLS = {"write_bash": "Bash", "write_powershell": "PowerShell"}

# ``str_replace_editor`` reads, creates or edits a file depending on its
# ``command``, so each command gets the Claude Code tool that does the same thing.
# Any other command keeps the native name, so rules written for these tools never
# judge something they do not do.
_EDITOR_COMMANDS = {"view": "Read", "create": "Write", "str_replace": "Edit", "insert": "Edit"}

# The operations of Copilot's ``lsp`` tool that only read. Its ``rename`` edits
# files across the project, while Claude Code's LSP only reads and passes without
# grading by default, so ``rename`` and any operation not listed keep the native name.
_LSP_READS = frozenset(
    {
        "goToDefinition",
        "findReferences",
        "hover",
        "documentSymbol",
        "workspaceSymbol",
        "goToImplementation",
        "incomingCalls",
        "outgoingCalls",
    }
)


def policy_call(name: str, arguments: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Copilot's tool call as the Claude Code name and arguments Watcher's deterministic policy judges.

    Used only for command rules and per-tool thresholds; see ``_POLICY_NAMES``
    for the direct renames. ``arguments`` is never modified.

    ``write_bash`` and ``write_powershell`` type into a running shell; they become
    ``Bash`` and ``PowerShell`` with the typed text as ``command``, so shell rules
    see it, keeping their other fields. ``str_replace_editor`` is named after its
    ``command`` (see ``_EDITOR_COMMANDS``), with ``path`` as ``file_path``. ``lsp``
    becomes ``LSP`` only for an operation that reads (see ``_LSP_READS``), with
    ``file`` as ``filePath``, Claude Code's key for it. GPT's freeform
    ``apply_patch`` keeps its name, as Codex's does, so the built-in thresholds
    and rules keyed to ``apply_patch`` judge the whole patch. Non-text typed
    input, an editor command or ``lsp`` operation not listed, and MCP or other
    unmapped tools keep their names and arguments. A mapped file tool whose path
    is not text keeps its arguments under the Claude Code name.

    The keys this function derives always win over keys of the same name the model
    supplied. Rules read ``command`` and ``file_path``, so a model that added its
    own ``command`` to ``write_bash``, or a ``file_path`` to ``view``, could
    otherwise have a harmless value judged in place of what actually runs.
    """
    native = dict(arguments)
    typed_shell = _TYPED_SHELLS.get(name)
    if typed_shell is not None:
        typed = native.get("input")
        if not isinstance(typed, str):
            return name, native
        return typed_shell, {"command": typed} | {
            key: value for key, value in native.items() if key not in {"input", "command"}
        }
    if name == "str_replace_editor":
        command = native.get("command")
        editor_tool = _EDITOR_COMMANDS.get(command) if isinstance(command, str) else None
        if editor_tool is None:
            return name, native
        return editor_tool, _renamed_path(native, "path", "file_path")
    if name == "lsp":
        operation = native.get("operation")
        if not isinstance(operation, str) or operation not in _LSP_READS:
            return name, native
        return "LSP", _renamed_path(native, "file", "filePath")
    canonical, path_key = _POLICY_NAMES.get(name, (name, None))
    if path_key is not None:
        native = _renamed_path(native, path_key, "file_path")
    return canonical, native


def _renamed_path(arguments: dict[str, Any], native: str, canonical: str) -> dict[str, Any]:
    """``arguments`` with the path under ``native`` moved to ``canonical``, replacing any value already there.

    A path that is missing or not text leaves ``arguments`` unchanged.
    """
    path = arguments.get(native)
    if not isinstance(path, str):
        return arguments
    return {key: value for key, value in arguments.items() if key != native} | {canonical: path}
