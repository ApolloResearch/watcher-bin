"""Observe a completed Cline session using its public SDK history reader."""

import asyncio
import json
import os
import sys
from contextlib import suppress

import typer

from watcher_cline_bridge.conversion import normalize_messages
from watcher_cline_bridge.monitoring import observe
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


PREFIX = "cline:"
HISTORY_READ_TIMEOUT_SECONDS = 25


def convert(records: list[dict]) -> list[dict]:
    """Normalize canonical Cline history without losing structured tool results.

    Cline can store arbitrary tool output objects inside a result's content array.
    Encode those results as JSON text to retain their values and native IDs.
    Other blocks support text, visible thinking and identified function calls.
    """
    history = []
    for row in records:
        blocks = []
        for block in row["content"]:
            if block["type"] == "tool_result":
                content = block["content"]
                blocks.append(
                    {
                        **block,
                        "content": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False),
                    }
                )
            else:
                blocks.append(block)
        history.append({"role": row["role"], "content": blocks})
    return normalize_messages(history)


async def send(client: AsyncWatcherClient, session_id: str, messages: list[dict], *, record_only: bool = False) -> None:
    """Observe completed tools, or only upload the transcript after monitored dispatch.

    Set record_only for a synchronous run so its earlier applied decisions remain
    authoritative. Upload success alone does not prove durable storage.
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
    """Read the public native history at TaskComplete, including the initial user prompt.

    Root-session completion supplies sessionContext.rootSessionId. The native SDK
    owns its persistence format; this adapter does not read its database or files.
    Subagent callbacks are rejected because they require separate session mapping.
    Timeout or task cancellation kills and reaps the history-reader child before
    propagating the original exception.
    """
    session_id = payload["sessionContext"]["rootSessionId"]
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("A native session ID is required")
    if payload["hookName"] != "agent_end" or payload.get("parent_agent_id"):
        raise ValueError("Only root-session completion is supported")
    process = await asyncio.create_subprocess_exec(
        os.environ.get("WATCHER_HISTORY_READER", "watcher-cline-history"),
        session_id,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(HISTORY_READ_TIMEOUT_SECONDS):
            output, _ = await process.communicate()
    except (TimeoutError, asyncio.CancelledError):
        with suppress(ProcessLookupError):
            process.kill()
        # Drain the pipe as well as reaping: an unread full buffer can delay wait().
        await process.communicate()
        raise
    if process.returncode:
        raise ValueError("The native public history reader failed")
    messages = convert(json.loads(output))
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        await send(client, session_id, messages, record_only=record_only)


def main() -> None:
    """Keep completion observational and emit static diagnostics on delivery failure."""
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
