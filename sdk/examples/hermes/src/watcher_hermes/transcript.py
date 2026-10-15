"""Read a Hermes session from its own store and convert it to Inspect chat messages.

Hermes persists every message of a session to SQLite (``state.db`` under the
profile's ``HERMES_HOME``) as the turn runs: the assistant message that proposes
a tool call is written before the ``pre_tool_call`` hook fires. The supported
reader of that store is ``hermes sessions export``, which prints one JSON line
per session with its ``messages`` in insertion order. Both the gate and the
recorder read the session this way, so the two send Watcher the same prefix and
its hash chain extends one conversation instead of forking it.

Hermes messages are OpenAI chat messages plus storage bookkeeping. Conversion
keeps the role, text, reasoning, tool calls (with arguments decoded from their
JSON string) and tool results, and drops the bookkeeping. Only ``active`` rows
are kept: that is the conversation the model currently sees. Rewinds and
context compaction retire rows and insert replacements, so after either one the
history no longer extends what Watcher stored and Watcher records a new branch.

A single call through Hermes's ``tool_call`` bridge (deferred and MCP tools) is
converted to the underlying tool and arguments, which is what Hermes passes to
``pre_tool_call`` and what runs; Hermes splits multi-tool local batches into
such single calls before storing them. Connector calls (``connectors__``) stay
as stored: Hermes judges them per entry under the wrapper's call ID, which the
gate cannot match, so it refuses them.
"""

import asyncio
import json
import shutil
from contextlib import suppress
from copy import deepcopy
from typing import Any

PREFIX = "hermes:"
"""Prefix of the Watcher external ID that names a Hermes session (``hermes:<session id>``)."""

EXPORT_TIMEOUT_SECONDS = 20.0

BRIDGE_TOOL = "tool_call"
"""Hermes's tool-search bridge, which wraps a deferred tool's name and arguments."""
CONNECTOR_PREFIX = "connectors__"
"""Name prefix of Hermes connector tools, which keep their bridge wrapper at the hook."""


def external_ids(session_id: str) -> dict[str, str]:
    """Return the Watcher external IDs that name one Hermes session."""
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("A Hermes session ID is required")
    return {"other": PREFIX + session_id}


def _text(content: Any) -> str:
    """Flatten Hermes message content (a string or OpenAI content parts) to text.

    Non-text parts such as images are replaced by a short placeholder so the
    grader knows something was attached without receiving the bytes.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        raise ValueError("Unsupported Hermes message content")
    parts = []
    for part in content:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, dict) and part.get("type") in {"text", "input_text", "output_text"}:
            parts.append(str(part.get("text") or ""))
        elif isinstance(part, dict):
            parts.append(f"[{part.get('type', 'attachment')} omitted]")
        else:
            raise ValueError("Unsupported Hermes message content part")
    return "\n".join(parts)


def decode_arguments(arguments: Any) -> dict[str, Any]:
    """Decode an OpenAI tool-call ``arguments`` value into the object Watcher grades.

    Hermes stores arguments as the model's JSON string. A value that is not a
    JSON object is kept under ``_raw_arguments`` rather than dropped, so the
    grader still sees what the model asked for.
    """
    if isinstance(arguments, dict):
        return deepcopy(arguments)
    if arguments in (None, ""):
        return {}
    if isinstance(arguments, str):
        try:
            decoded = json.loads(arguments)
        except json.JSONDecodeError:
            return {"_raw_arguments": arguments}
        return decoded if isinstance(decoded, dict) else {"_raw_arguments": arguments}
    raise ValueError("Unsupported Hermes tool-call arguments")


def unwrap_bridge(name: str, arguments: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return the tool a single-entry ``tool_call`` bridge runs, or the call unchanged.

    Mirrors Hermes's reading of the bridge (``normalize_tool_call_entries``):
    ``{"calls": [{"name", "arguments"}]}``, or the older ``{"name", "arguments"}``
    when ``calls`` is absent or null; ``calls`` may be a JSON string or a single
    object, and missing, null or blank entry arguments mean ``{}``. Hermes hooks
    see the underlying tool for these. Connector tools (``connectors__``) keep
    the wrapper because Hermes passes the wrapper itself to the outer hook.
    Batches, connector calls and malformed entries are returned as stored, so
    one bad historical row never stops the rest of the session converting.
    """
    if name != BRIDGE_TOOL:
        return name, arguments
    entries = arguments.get("calls")
    if entries is None:
        entries = [arguments] if "name" in arguments else None
    if isinstance(entries, str):
        try:
            entries = json.loads(entries)
        except json.JSONDecodeError:
            return name, arguments
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
        return name, arguments
    inner, inner_arguments = entries[0].get("name"), entries[0].get("arguments")
    if not isinstance(inner, str) or not inner.strip() or inner.strip().startswith(CONNECTOR_PREFIX):
        return name, arguments
    if inner_arguments is None or (isinstance(inner_arguments, str) and not inner_arguments.strip()):
        return inner.strip(), {}
    if not isinstance(inner_arguments, (str, dict)):
        return name, arguments
    return inner.strip(), decode_arguments(inner_arguments)


def _tool_call(call: Any) -> dict[str, Any]:
    if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
        raise ValueError("Unsupported Hermes tool call")
    call_id, name = call.get("id") or call.get("call_id"), call["function"].get("name")
    if not isinstance(call_id, str) or not call_id or not isinstance(name, str) or not name:
        raise ValueError("Hermes tool calls need an ID and a name")
    name, arguments = unwrap_bridge(name, decode_arguments(call["function"].get("arguments")))
    return {"id": call_id, "function": name, "arguments": arguments}


def _is_live(row: dict[str, Any]) -> bool:
    """Keep the rows the model currently sees; in-memory histories carry no flag and are all live."""
    return "active" not in row or bool(row.get("active"))


def convert(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Hermes session messages to Inspect chat messages.

    Accepts the ``messages`` of ``hermes sessions export`` or a hook's
    ``conversation_history``. System rows are dropped: Hermes keeps its system
    prompt outside the message list. Tool results keep their native
    ``tool_call_id``, and a result whose call is not in the history is
    rejected, since Watcher could not attach it to a call. Source rows are not
    modified.
    """
    messages: list[dict[str, Any]] = []
    calls: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Unsupported Hermes message")
        if not _is_live(row):
            continue
        role = row.get("role")
        if role == "system":
            continue
        if role == "user":
            messages.append({"role": "user", "content": _text(row.get("content"))})
        elif role == "assistant":
            content: list[dict[str, Any]] = []
            reasoning = row.get("reasoning") or row.get("reasoning_content")
            if isinstance(reasoning, str) and reasoning:
                content.append({"type": "reasoning", "reasoning": reasoning})
            text = _text(row.get("content"))
            if text:
                content.append({"type": "text", "text": text})
            message: dict[str, Any] = {"role": "assistant", "content": content}
            tool_calls = [_tool_call(call) for call in row.get("tool_calls") or []]
            if tool_calls:
                for call in tool_calls:
                    calls[call["id"]] = call["function"]
                message["tool_calls"] = tool_calls
            messages.append(message)
        elif role == "tool":
            call_id = row.get("tool_call_id")
            if not isinstance(call_id, str) or call_id not in calls:
                raise ValueError("A Hermes tool result must answer an earlier tool call")
            messages.append(
                {
                    "role": "tool",
                    "content": _text(row.get("content")),
                    "tool_call_id": call_id,
                    "function": calls[call_id],
                }
            )
        else:
            raise ValueError("Unsupported Hermes message role")
    return messages


def with_pending_call(messages: list[dict[str, Any]], call: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the history, checking it holds the pending call exactly once and unanswered.

    Hermes stores the proposing assistant message before the gate runs, so a
    missing call means the export is not the conversation that produced it:
    for example a background review agent, which shares its parent's session
    ID but keeps its own history only in memory. Grading such a call against
    the parent's history would judge it without its real context, so it is
    refused. So is a stored call whose name or arguments differ from the
    pending one, or one that already has a result. The input list is not
    modified.
    """
    found = [c for m in messages for c in m.get("tool_calls", []) if c["id"] == call["id"]]
    if any(m.get("tool_call_id") == call["id"] for m in messages):
        raise ValueError("This tool call already has a result")
    if not found:
        raise ValueError("The session history does not contain the call Hermes is about to run")
    canonical = json.dumps(call["arguments"], sort_keys=True, allow_nan=False)
    stored = found[0]
    if (
        len(found) != 1
        or stored["function"] != call["function"]
        or json.dumps(stored["arguments"], sort_keys=True, allow_nan=False) != canonical
    ):
        raise ValueError("The stored tool call does not match the call Hermes is about to run")
    return deepcopy(messages)


def hermes_command(hermes_bin: str | None) -> str:
    """Resolve the ``hermes`` executable that reads this profile's store."""
    resolved = hermes_bin or shutil.which("hermes")
    if not resolved:
        raise FileNotFoundError("The hermes command was not found; pass --hermes-bin")
    return resolved


async def export_session(session_id: str, *, hermes_bin: str | None = None) -> list[dict[str, Any]]:
    """Return a session's stored messages via ``hermes sessions export``.

    The child inherits this process's environment, so it reads the store of the
    profile (``HERMES_HOME``) that fired the hook. A deadline bounds the export;
    on expiry or cancellation the child is killed and reaped before the error
    propagates. Exporting reads the store without changing it.
    """
    process = await asyncio.create_subprocess_exec(
        hermes_command(hermes_bin),
        "sessions",
        "export",
        "-",
        "--session-id",
        session_id,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(EXPORT_TIMEOUT_SECONDS):
            output, _ = await process.communicate()
    except (TimeoutError, asyncio.CancelledError):
        with suppress(ProcessLookupError):
            process.kill()
        await process.communicate()
        raise
    if process.returncode:
        raise ValueError("hermes sessions export failed")
    sessions = [json.loads(line) for line in output.decode().splitlines() if line.strip()]
    matching = [s for s in sessions if isinstance(s, dict) and s.get("id") == session_id]
    if len(matching) != 1 or not isinstance(matching[0].get("messages"), list):
        raise ValueError("hermes sessions export did not return this session")
    return matching[0]["messages"]
