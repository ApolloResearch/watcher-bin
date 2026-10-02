"""Native completion hook to public Watcher SDK; see README for supported transcript shapes."""

import asyncio
import json
import os
import sys
from pathlib import Path

import typer

from watcher_qwen_code.conversion import normalize_messages
from watcher_qwen_code.monitoring import observe
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


PREFIX = "qwen-code:"


def convert(records: list[dict]) -> list[dict]:
    """Read Qwen native JSONL parts with explicit function-call/result identifiers.

    Branches, compaction and missing IDs are rejected; name-based result matching
    would falsely link parallel calls to the same tool. Preserve all visible text.
    """
    history = []
    for row in records:
        if row.get("forkedFrom") or row.get("subtype") in {"chat_compression", "rewind", "branch_checkpoint"}:
            raise ValueError("Branched histories require branch-aware replay")
        if row["type"] not in {"user", "assistant", "tool_result"}:
            continue
        blocks = []
        for part in row["message"]["parts"]:
            if "text" in part:
                blocks.append({"type": "text", "text": part["text"]})
            elif "functionCall" in part:
                call = part["functionCall"]
                blocks.append({"type": "tool_use", "id": call["id"], "name": call["name"], "input": call["args"]})
            elif "functionResponse" in part:
                result = part["functionResponse"]
                blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": result["id"],
                        "content": json.dumps(result["response"], ensure_ascii=False),
                    }
                )
            else:
                raise ValueError("Unsupported Qwen content")
        history.append({"role": "assistant" if row["type"] == "assistant" else "user", "content": blocks})
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
    """Read the native full transcript on each completion hook, without local cursors."""
    path = payload["transcript_path"]
    if not isinstance(path, str) or not path:
        raise ValueError("The native hook did not supply a transcript path")
    records = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    messages = convert(records)
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
