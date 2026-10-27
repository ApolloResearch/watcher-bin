"""Codex rollout boundaries shared by Watcher ingestion clients and the server.

A Codex rollout records each tool call as an opening item and a later
``*_output`` item. A transcript observed mid-turn can end between the two, and
such a tail cannot be stored on its own: the rest of the cycle arrives later
and would have to land on a different chain. These functions find the last
point where every open call was matched, and the ``call_id`` of the pending
call a Codex hook reports without one (`pending_call_id`).
"""

from __future__ import annotations

import json
import shlex
from enum import Enum
from typing import Any

from watcher_transcript_transport.upload import JsonEntry

__all__ = [
    "CALL_CLOSING_TYPES",
    "CALL_OPENING_TYPES",
    "CodexCallCycles",
    "codex_tool_name",
    "is_assistant_output_payload",
    "is_turn_aborted_event",
    "is_turn_aborted_marker_entry",
    "is_turn_started_event",
    "own_codex_entries",
    "pending_call_id",
    "scan_codex_call_cycles",
    "trim_incomplete_codex_tail",
]

CALL_OPENING_TYPES = frozenset({"function_call", "local_shell_call", "custom_tool_call"})
CALL_CLOSING_TYPES = frozenset({"function_call_output", "custom_tool_call_output"})

# Codex writes its turn-start event as ``task_started`` and reads ``turn_started``
# as an alias, so both spellings can reach a rollout.
_TURN_STARTED_EVENT_TYPES = frozenset({"task_started", "turn_started"})


def is_turn_aborted_marker_entry(entry: JsonEntry) -> bool:
    """True when ``entry`` is Codex's ``<turn_aborted>`` notice (Ctrl-C marker).

    Codex emits this synthetic message after the user cancels a turn. It is
    the only model-visible record that the previous turn was aborted, and the
    server's Codex parser deliberately preserves it (unlike the AGENTS.md and
    ``<environment_context>`` wrappers, which it drops). The trim treats it as
    a turn boundary so an aborted partial tool call doesn't keep calls pending
    across the marker and the completed turns that follow. The marker's role
    depends on Codex configuration (``user`` by default, ``developer`` under
    multi-agent mode), so both are accepted.
    """
    if entry.get("type") != "response_item":
        return False
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        return False
    if payload.get("type") != "message" or payload.get("role") not in ("user", "developer"):
        return False
    content = payload.get("content")
    if not isinstance(content, list) or not content:
        return False
    first = content[0]
    if not isinstance(first, dict):
        return False
    text = first.get("text")
    if not isinstance(text, str):
        return False
    return text.startswith("<turn_aborted>") and "</turn_aborted>" in text


def is_turn_aborted_event(entry: JsonEntry) -> bool:
    """True when ``entry`` is Codex's ``turn_aborted`` event line.

    Unlike the ``<turn_aborted>`` message marker, which Codex only writes when
    configured to (``agents.interrupt_message``), this ``event_msg`` line is
    persisted to the rollout on every abort, so it is the reliable turn
    boundary for the trim when the marker is absent.
    """
    if entry.get("type") != "event_msg":
        return False
    payload = entry.get("payload")
    return isinstance(payload, dict) and payload.get("type") == "turn_aborted"


def is_turn_started_event(entry: JsonEntry) -> bool:
    """True when ``entry`` is the ``event_msg`` line that opens a new Codex turn.

    A turn starts only after the previous one has finished, so a call still
    pending at this line belonged to a turn that ended without recording its
    output. That happens when Codex exits or crashes mid-call: nothing writes
    a ``turn_aborted`` event, and resuming the thread goes straight to the next
    turn's start.
    """
    if entry.get("type") != "event_msg":
        return False
    payload = entry.get("payload")
    return isinstance(payload, dict) and payload.get("type") in _TURN_STARTED_EVENT_TYPES


def is_assistant_output_payload(payload: dict[str, Any]) -> bool:
    """Whether ``payload`` is a shape the model produces during its own turn (shape only, not content)."""
    payload_type = payload.get("type", "")
    if payload_type == "reasoning":
        return True
    return payload_type == "message" and payload.get("role") == "assistant"


# Response items the parser emits as messages of their own, ending any
# assistant message it was building.
_MESSAGE_ENDING_TYPES = frozenset({"tool_search_output", "agent_message", "compaction", "compaction_summary"})
# Response items the parser always folds into that message, whatever else they carry.
_JOINING_TYPES = frozenset({"reasoning", "tool_search_call"})


class _MessageEffect(Enum):
    """What one response item does to the assistant message the parser is building."""

    JOINS = "joins"
    ENDS = "ends"
    PASSES = "passes"


def _message_effect(payload: dict[str, Any]) -> _MessageEffect:
    """Whether the parser folds ``payload`` into the assistant message it is building, ends it, or skips it.

    Mirrors the server's Codex parser: the model's text and reasoning, its
    call openings and items such as web searches that carry no output join
    it; a user or system message, a call's output and the other items the
    parser emits on their own end it; an empty message and Codex's injected
    AGENTS.md and environment blocks are dropped without ending it. An item
    of a type the parser has no handler for ends it only when its output is
    text or a list, the only outputs the parser reads (a null or any other
    value counts as none), so a scan of the raw file and one of its parsed,
    null-free entries agree.
    """
    payload_type = payload.get("type", "")
    if payload_type == "message":
        text = _message_text(payload.get("content"))
        role = payload.get("role")
        if not text.strip() or (role == "user" and _is_codex_scaffolding(text)):
            return _MessageEffect.PASSES
        return _MessageEffect.JOINS if role == "assistant" else _MessageEffect.ENDS
    if payload_type in _JOINING_TYPES:
        return _MessageEffect.JOINS
    if payload_type in CALL_CLOSING_TYPES or payload_type in _MESSAGE_ENDING_TYPES:
        return _MessageEffect.ENDS
    return _MessageEffect.ENDS if isinstance(payload.get("output"), (str, list)) else _MessageEffect.JOINS


def _message_text(content: Any) -> str:
    """A message's text as the parser reads it: its text items, with an image counting as text."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") in ("input_text", "output_text", "text") and isinstance(item.get("text"), str):
            parts.append(item["text"])
        elif item.get("type") == "input_image" and item.get("image_url"):
            parts.append("[image]")
    return "".join(parts)


def _is_codex_scaffolding(text: str) -> bool:
    """Whether a user message is the AGENTS.md wrapper or environment block Codex injects, which the parser drops."""
    return (text.startswith("# AGENTS.md instructions for ") and "<INSTRUCTIONS>" in text) or (
        text.startswith("<environment_context>") and "</environment_context>" in text
    )


def trim_incomplete_codex_tail(
    entries: list[JsonEntry],
    *,
    allow_trailing_assistant_output: bool,
) -> list[JsonEntry]:
    """Trim trailing entries whose tool calls don't have a matching ``*_output`` yet.

    A reader may observe the rollout while Codex is mid-turn and see new tool
    calls without their outputs, so this trims back to the last point where
    every open call was matched and each batch ends at a clean turn boundary.

    An abort counts as a turn boundary too: any pending call before it was
    cancelled by the user and will never get a matching ``*_output``, so the
    pending set closes there and completed turns that follow are kept. Aborts
    are recognized both by the ``<turn_aborted>`` message marker and by the
    always-persisted ``turn_aborted`` event line, because Codex can be
    configured not to write the marker, which would otherwise leave the
    aborted call pending forever and permanently trim every later turn.

    The start of the next turn closes the pending set the same way. A Codex
    process that exits or crashes mid-call records neither the output nor an
    abort, so without this boundary one interrupted call would hold back
    everything the resumed thread does until some later abort cleared it.

    The openings of calls still pending at an abort or a turn start are
    dropped from the result, not retained: downstream an output-less opening
    reads as a completed call the interruption never evidenced.

    ``allow_trailing_assistant_output`` should be true where trailing
    assistant messages or reasoning are completed output (a turn's end), and
    false mid-turn, where that output may still be being written.
    """
    if not entries:
        return entries

    cycles = scan_codex_call_cycles(entries, allow_trailing_assistant_output=allow_trailing_assistant_output)
    if cycles.complete_until >= len(entries) and not cycles.interrupted_openings:
        return entries

    return [entry for i, entry in enumerate(entries[: cycles.complete_until]) if i not in cycles.interrupted_openings]


class CodexCallCycles:  # noqa: B903
    """Where a rollout's call cycles stand: see `scan_codex_call_cycles`.

    ``complete_until`` is the index just past the last point where no call was
    pending. ``interrupted_openings`` holds the indices of the openings a turn
    boundary (abort or turn start) closed while they were still pending.
    """

    __slots__ = ("complete_until", "interrupted_openings")

    complete_until: int
    interrupted_openings: set[int]

    def __init__(self, complete_until: int, interrupted_openings: set[int]) -> None:
        self.complete_until = complete_until
        self.interrupted_openings = interrupted_openings


def scan_codex_call_cycles(
    entries: list[JsonEntry],
    *,
    allow_trailing_assistant_output: bool,
) -> CodexCallCycles:
    """Pair call openings with their outputs across the rollout, for `trim_incomplete_codex_tail`.

    The trim's docstring covers what counts as a boundary and why.
    """
    pending_opening_idx: dict[str, int] = {}
    interrupted_opening_idxs: set[int] = set()
    last_complete_idx = 0
    # Mid-turn only: items since the last cut that the parser folds into the
    # assistant message it is building (text, reasoning, a web search), which a
    # call that follows joins. Nothing short of an item that ends that message
    # may move the cut past them, or the stored part would end in a message the
    # finished turn writes differently.
    assistant_pending = False

    for i, entry in enumerate(entries):
        if is_turn_aborted_marker_entry(entry) or is_turn_aborted_event(entry) or is_turn_started_event(entry):
            interrupted_opening_idxs.update(pending_opening_idx.values())
            pending_opening_idx.clear()
            assistant_pending = False
            last_complete_idx = i + 1
            continue

        payload = entry.get("payload") if entry.get("type") == "response_item" else None
        if not isinstance(payload, dict):
            if not pending_opening_idx and not assistant_pending:
                last_complete_idx = i + 1
            continue

        payload_type = payload.get("type", "")
        call_id = payload.get("call_id", "") or ""

        if payload_type in CALL_OPENING_TYPES:
            if call_id:
                pending_opening_idx[call_id] = i
        elif payload_type in CALL_CLOSING_TYPES:
            if call_id:
                pending_opening_idx.pop(call_id, None)
            if not pending_opening_idx:
                assistant_pending = False
                last_complete_idx = i + 1
        elif not pending_opening_idx:
            effect = _message_effect(payload)
            if allow_trailing_assistant_output or effect is _MessageEffect.ENDS:
                assistant_pending = False
                last_complete_idx = i + 1
            elif effect is _MessageEffect.JOINS:
                assistant_pending = True
            elif not assistant_pending:
                last_complete_idx = i + 1

    return CodexCallCycles(last_complete_idx, interrupted_opening_idxs)


# Codex's function-call shell tools and the argument holding their command.
_SHELL_COMMAND_KEYS = {
    "exec_command": "cmd",
    "shell": "command",
    "shell_command": "command",
    "container.exec": "command",
}
# Exactly the shell spellings Xylon's policy translation unwraps, so an ID
# chosen here names a call the server matches to the same report.
_SCRIPT_SHELLS = frozenset(
    {f"{prefix}{shell}" for prefix in ("", "/bin/", "/usr/bin/") for shell in ("bash", "sh", "zsh")}
)
_SCRIPT_FLAGS = frozenset({"-c", "-lc"})
_PATCH_TOOL = "apply_patch"
# Codex's hooks name a tool of its default `collaboration` group by the group
# and the tool run together; the rollout records the bare name. Only the pairs
# Xylon's policy translation treats as one tool, so an ID chosen here names a
# call the server matches to the same report.
_GROUPED_HOOK_NAMES = {
    "collaborationspawn_agent": "spawn_agent",
    "collaborationsend_message": "send_message",
}


def codex_tool_name(name: str, namespace: str | None) -> str:
    """Fold a native tool namespace into the identity Codex reports to its hooks.

    A missing/empty namespace, default ``functions`` tools and legacy
    ``multi_agent_v1.spawn_agent`` keep their bare name. An MCP namespace
    ``mcp__server`` becomes ``mcp__server__tool``; other
    groups concatenate namespace and name (``collaborationwait_agent``).
    Shell aliases such as Bash are policy translations, not namespace rules.
    Use this for both rollout and gateway records so grading sees the same
    tool identity as the corresponding hook without conflating MCP tools.
    """
    if not namespace or namespace == "functions":
        return name
    if namespace.startswith("mcp__"):
        return f"{namespace.rstrip('_')}__{name.lstrip('_')}"
    if namespace == "multi_agent_v1" and name == "spawn_agent":
        return name
    return namespace + name


def own_codex_entries(entries: list[JsonEntry]) -> list[JsonEntry]:
    """Select records eligible for this thread's tool matching, preserving native order.

    The first metadata record supplies subagent_history_start_ordinal. Earlier
    numbered records are inherited context; keep that first metadata record so
    repeated selection retains the boundary. Without a boundary, return the
    original list. Use this for call matching and reconciliation only: uploads
    and grading context must retain the inherited prefix. Do not renumber entries
    or use filtered-list indexes as native ordinals.
    """
    meta = next((entry for entry in entries if entry.get("type") == "session_meta"), None)
    payload = meta.get("payload") if meta is not None else None
    boundary = payload.get("subagent_history_start_ordinal") if isinstance(payload, dict) else None
    if not isinstance(boundary, int):
        return entries
    return [
        entry
        for entry in entries
        if entry is meta or not isinstance(entry.get("ordinal"), int) or entry["ordinal"] >= boundary
    ]


def pending_call_id(entries: list[JsonEntry], tool_name: str, tool_input: Any) -> str | None:
    """The ``call_id`` of the one pending call in the current turn that a Codex hook reports, or ``None``.

    Codex's permission hook reports a call without its ID, and in another
    shape than the rollout records it: a shell call as ``Bash`` with only its
    command, a patch under another key. A pending call is one opened in the
    current turn (after the last user message or turn start) that has no
    output and was not interrupted. It matches when it is the same call as
    the report: the same shell command, the same patch text, or, for any
    other tool, the same name and arguments. ``None`` when no pending call
    matches, or several distinct ones do, since guessing could judge another
    call. Copied parent calls before the subagent's native history boundary
    cannot match, even when their arguments are identical to the child's.
    """
    entries = own_codex_entries(entries)
    cycles = scan_codex_call_cycles(entries, allow_trailing_assistant_output=True)
    answered: set[str] = set()
    turn: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if is_turn_started_event(entry):
            turn = []
            continue
        payload = entry.get("payload") if entry.get("type") == "response_item" else None
        if not isinstance(payload, dict):
            continue
        if payload.get("type") in CALL_CLOSING_TYPES and payload.get("call_id"):
            answered.add(payload["call_id"])
        elif (
            payload.get("type") == "message"
            and payload.get("role") == "user"
            and _message_effect(payload) is (_MessageEffect.ENDS)
        ):
            turn = []
        elif (
            payload.get("type") in CALL_OPENING_TYPES
            and payload.get("call_id")
            and index not in cycles.interrupted_openings
        ):
            turn.append(payload)
    matches = {
        payload["call_id"]
        for payload in turn
        if payload["call_id"] not in answered and _reports_call(payload, tool_name, tool_input)
    }
    return next(iter(matches)) if len(matches) == 1 else None


def _reports_call(payload: dict[str, Any], tool_name: str, tool_input: Any) -> bool:
    """Match a hook report to a native call without discarding namespace identity.

    Native shell calls match Bash by command, and apply_patch by patch text.
    Other calls require their qualified name and identical JSON arguments.
    Namespace-free spawn/send records also accept the existing collaboration
    policy aliases. Explicit MCP/group namespaces never use shell/patch aliases,
    even when their bare tool name looks like a built-in. Malformed identity or
    arguments cannot match. This does not check whether the call is pending.
    """
    name = payload.get("name")
    namespace = payload.get("namespace")
    if payload.get("type") == "local_shell_call":
        name, namespace = "local_shell", None
    if not isinstance(name, str) or (namespace is not None and not isinstance(namespace, str)):
        return False
    recorded_name = codex_tool_name(name, namespace)
    reported = tool_input if isinstance(tool_input, dict) else {}
    recorded_command = _shell_command(payload) if not namespace or namespace == "functions" else None
    if recorded_command is not None:
        return tool_name == "Bash" and recorded_command == reported.get("command")
    if recorded_name == _PATCH_TOOL:
        patch = _patch_text(payload.get("input") if payload.get("type") == "custom_tool_call" else payload)
        return tool_name == _PATCH_TOOL and patch is not None and patch == _patch_text(tool_input)
    arguments = payload.get("arguments", payload.get("input"))
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return False
    # Compared as JSON, as the server compares them, so a boolean never equals a number.
    names_match = recorded_name == tool_name or (
        not namespace and recorded_name == _GROUPED_HOOK_NAMES.get(tool_name, tool_name)
    )
    return names_match and json.dumps(arguments, sort_keys=True) == json.dumps(tool_input, sort_keys=True)


def _shell_command(payload: dict[str, Any]) -> str | None:
    """The command text a recorded shell call runs, as Codex's hook reports it; ``None`` for other calls."""
    if payload.get("type") == "local_shell_call":
        action = payload.get("action")
        argv = action.get("command") if isinstance(action, dict) else None
        return _argv_text(argv)
    key = _SHELL_COMMAND_KEYS.get(payload.get("name", ""))
    if key is None or payload.get("type") != "function_call":
        return None
    arguments = payload.get("arguments") or {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return None
    command = arguments.get(key) if isinstance(arguments, dict) else None
    return command if isinstance(command, str) else _argv_text(command)


def _argv_text(argv: Any) -> str | None:
    """An argv as one command: a shell's ``-c`` script itself, any other argv quoted and joined."""
    if not isinstance(argv, list) or not argv or not all(isinstance(part, str) for part in argv):
        return None
    if len(argv) == 3 and argv[0] in _SCRIPT_SHELLS and argv[1] in _SCRIPT_FLAGS:
        return argv[2]
    return shlex.join(argv)


def _patch_text(value: Any) -> str | None:
    """A patch's text, whichever key carries it (``input``, ``raw`` or ``command``) or as bare text."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return value
    if isinstance(value, dict):
        for key in ("input", "raw", "command"):
            if isinstance(value.get(key), str):
                return value[key]
        arguments = value.get("arguments")
        return _patch_text(arguments) if isinstance(arguments, str) else None
    return value if isinstance(value, str) else None
