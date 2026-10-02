"""Native completion hook to public Watcher SDK; see README for supported transcript shapes."""

import asyncio
import json
import os
import sys

import typer

from watcher_opencode_bridge.conversion import normalize_messages
from watcher_opencode_bridge.monitoring import observe
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


PREFIX = "opencode:"


def convert(records: list[dict], *, allow_pending: bool = False) -> list[dict]:
    """Convert session.messages() records with completed tool parts to Inspect.

    Tool results live inside their tool part, so result ordering follows upstream
    part order, not wall-clock completion order. Pending/running parts are refused unless allow_pending=True for a native
    pre-tool snapshot; then only the call is emitted, never a fabricated result.
    File attachments and compaction summaries require additional normalization.
    """
    history = []
    for row in records:
        role = row["info"]["role"]
        if role == "assistant" and row["info"].get("summary"):
            raise ValueError("Compacted histories require branch-aware replay")
        blocks, results = [], []
        for part in row["parts"]:
            kind = part["type"]
            if kind == "text":
                blocks.append({"type": "text", "text": part["text"]})
            elif kind == "reasoning":
                blocks.append({"type": "thinking", "thinking": part["text"]})
            elif kind == "tool":
                state = part["state"]
                if state["status"] not in (
                    {"completed", "error", "pending", "running"} if allow_pending else {"completed", "error"}
                ) or state.get("attachments"):
                    raise ValueError("Tool is incomplete or has unsupported attachments")
                blocks.append({"type": "tool_use", "id": part["callID"], "name": part["tool"], "input": state["input"]})
                if state["status"] in {"pending", "running"} and allow_pending:
                    continue
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": part["callID"],
                        "content": state["error"] if state["status"] == "error" else state["output"],
                        "is_error": state["status"] == "error",
                    }
                )
            elif kind not in {"step-start", "step-finish"}:
                raise ValueError("Unsupported OpenCode part")
        if blocks:
            history.append({"role": role, "content": blocks})
        if results:
            history.append({"role": "user", "content": results})
    return normalize_messages(history)


async def send(client: AsyncWatcherClient, session_id: str, messages: list[dict], *, record_only: bool = False) -> None:
    """Observe captured tools against their historical context, then record the final tail.

    Set record_only after synchronous monitoring to submit the final transcript
    without retrospective grades overwriting earlier applied decisions. An upload
    response alone does not establish durable storage.

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
    """Consume the native plugin's snapshot; stdout remains the hook control channel."""
    messages = convert(payload["messages"])
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        await send(client, payload["session_id"], messages, record_only=record_only)


def main() -> None:
    """Consume native hook stdin. Observation failures never block the coding agent.

    Emit only a neutral hook response and a static diagnostic: transcript content,
    paths, credentials and server error bodies are never copied to stderr.
    """
    record_only = record_mode()
    if record_only is not None and type(record_only) is not bool:
        return
    try:
        if record_only is None:
            raise ValueError("Unsupported bridge argument")
        asyncio.run(run_hook(json.load(sys.stdin), record_only=record_only))
    except Exception:
        sys.stderr.write("Watcher observation failed; transcript was not confirmed recorded.\n")
    sys.stdout.write("{}\n")


if __name__ == "__main__":
    main()
