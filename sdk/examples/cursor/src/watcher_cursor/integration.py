"""Native completion hook to public Watcher SDK; see README for supported transcript shapes."""

import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

import typer

from watcher_cursor.conversion import normalize_messages
from watcher_cursor.monitoring import observe
from watcher_sdk import AsyncWatcherClient

app = typer.Typer(
    invoke_without_command=True, no_args_is_help=False, add_completion=False, pretty_exceptions_enable=False
)


@app.callback()
def options(
    record_only: bool = typer.Option(False, "--record-only", help="Record the final transcript without regrading."),
) -> bool:
    """Parse the native completion hook's optional recording mode."""
    return record_only


@app.command("help", hidden=True)
def help_command(ctx: typer.Context) -> None:
    """Show hook options without reading a native event from stdin."""
    parent = ctx.parent
    typer.echo((parent if parent is not None else ctx).get_help())
    raise typer.Exit()


def record_mode() -> bool | None | int:
    """Parse options without exposing invalid arguments in native hook diagnostics.

    Return a boolean for a valid callback invocation, None for invalid arguments,
    or an exit code after an explicit help request. The hook owns the neutral
    response on invalid arguments; Typer must not echo their contents.
    """
    try:
        return app(standalone_mode=False)
    except Exception:
        return None


PREFIX = "cursor:"

EVENT_FIELD = "hook_event_name"
SESSION_FIELD = "conversation_id"
PROMPT_EVENT = "beforeSubmitPrompt"
CALL_EVENT = "preToolUse"
RESULT_EVENTS = {"postToolUse", "postToolUseFailure"}
FINAL_EVENT = "afterAgentResponse"
FLUSH_EVENT = "stop"


def prompt_text(row):
    return row["prompt"]


def final_text(row):
    return row["text"]


def native_call(row):
    return {"type": "tool_use", "id": row["tool_use_id"], "name": row["tool_name"], "input": row["tool_input"]}


def native_result(row):
    failed = row[EVENT_FIELD] == "postToolUseFailure"
    return {
        "type": "tool_result",
        "tool_use_id": row["tool_use_id"],
        "is_error": failed,
        "content": row["error_message"] if failed else row["tool_output"],
    }


def convert(records: list[dict]) -> list[dict]:
    """Project native hook deliveries into the observed portion of a conversation.

    This is not the model's complete prompt: hooks omit system instructions and
    some intermediate assistant text. Tool identities are native; no name-based
    linkage or invented IDs. Repeated identical tool deliveries are deduplicated.
    Conflicting reuse of an ID fails rather than silently overwriting history.
    """
    history, calls, results = [], {}, {}
    for row in records:
        event = row[EVENT_FIELD]
        if event == PROMPT_EVENT:
            history.append({"role": "user", "content": prompt_text(row)})
        elif event == CALL_EVENT:
            call = native_call(row)
            if call["id"] in calls:
                if calls[call["id"]] != call:
                    raise ValueError("Conflicting native tool ID")
                continue
            calls[call["id"]] = call
            history.append({"role": "assistant", "content": [call]})
        elif event in RESULT_EVENTS:
            result = native_result(row)
            identity = result["tool_use_id"]
            if identity not in calls:
                raise ValueError("Result arrived without its native call")
            if identity in results:
                if results[identity] != result:
                    raise ValueError("Conflicting native tool result")
                continue
            results[identity] = result
            history.append({"role": "user", "content": [result]})
        elif event == FINAL_EVENT:
            text = final_text(row)
            if text:
                history.append({"role": "assistant", "content": text})
    return normalize_messages(history)


async def send(client: AsyncWatcherClient, session_id: str, messages: list[dict], *, record_only: bool = False) -> None:
    """Observe captured tools against their historical context, then record the final tail.

    Set record_only after synchronous monitoring to preserve earlier decisions.
    Native execution has already occurred. No Watcher result changes tool output or
    permissions. Failures propagate to the observation-only native boundary.
    """
    if not session_id:
        raise ValueError("A native session ID is required")
    if record_only:
        outcomes = await client.pre_tool_use_hook(
            input=[], messages=messages, external_ids={"other": PREFIX + session_id}, timeout=10
        )
        if outcomes != []:
            raise ValueError("Transcript-only submission returned unexpected outcomes")
        return
    await observe(client, PREFIX + session_id, messages)


async def run_hook(payload: dict, *, record_only: bool = False) -> None:
    """Journal this native event transactionally; flush only at a completed response.

    WATCHER_STATE_DIR must name an application-owned private directory. SQLite
    serializes concurrent hook writers. Native detached delivery can still reorder
    callbacks: unmatched results remain a visible failure, never guessed linkage.
    Restart/resume requires retaining this journal. No delivery is deleted here.
    """
    session_id = payload[SESSION_FIELD]
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("A native session ID is required")
    state = Path(os.environ["WATCHER_STATE_DIR"])
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with sqlite3.connect(state / "native-events.sqlite3", timeout=5) as database:
        database.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, session TEXT, payload TEXT)")
        database.execute("INSERT INTO events (session,payload) VALUES (?,?)", (session_id, json.dumps(payload)))
        records = [
            json.loads(row[0])
            for row in database.execute("SELECT payload FROM events WHERE session=? ORDER BY seq", (session_id,))
        ]
    if payload[EVENT_FIELD] != FLUSH_EVENT:
        return
    messages = convert(records)
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        await send(client, session_id, messages, record_only=record_only)


def main() -> None:
    """Consume native hook stdin. Observation failures never block the coding agent.

    Emit only a neutral hook response and a static diagnostic: transcript content,
    paths, credentials and server error bodies are never copied to stderr.
    """
    record_only = record_mode()
    if record_only is not None and type(record_only) is not bool:
        return
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Expected a native hook object")
    except (ValueError, TypeError):
        sys.stderr.write("Watcher observation failed; transcript was not confirmed recorded.\n")
        raise SystemExit(1) from None
    event = payload.get(EVENT_FIELD)
    response = {"permission": "allow"} if event == CALL_EVENT else {"continue": True} if event == PROMPT_EVENT else {}
    try:
        if record_only is None:
            raise ValueError("Unsupported bridge argument")
        asyncio.run(run_hook(payload, record_only=record_only))
    except Exception:
        sys.stderr.write("Watcher observation failed; transcript was not confirmed recorded.\n")
    sys.stdout.write(json.dumps(response) + "\n")


if __name__ == "__main__":
    main()
