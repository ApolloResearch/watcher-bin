"""Native completion hook to public Watcher SDK; see README for supported transcript shapes."""

import asyncio
import json
import os
import sys
from contextlib import suppress
from copy import deepcopy

import typer

from watcher_goose.monitoring import observe
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


PREFIX = "goose:"


def text_parts(content):
    """Copy native text blocks and reject content this example cannot preserve."""
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if not isinstance(content, list):
        raise ValueError("Expected native text content")
    parts = []
    for block in content:
        if block.get("type") != "text" or not isinstance(block.get("text"), str):
            raise ValueError("Only native text tool results are supported")
        parts.append({"type": "text", "text": block["text"]})
    return parts


def register_call(call, calls):
    """Require one nonempty native ID, name and JSON object for each pending call."""
    if not isinstance(call["id"], str) or not call["id"] or call["id"] in calls:
        raise ValueError("Native tool IDs must be nonempty and unique")
    if not isinstance(call["function"], str) or not call["function"] or not isinstance(call["arguments"], dict):
        raise ValueError("Native tool names and object arguments are required")
    json.dumps(call["arguments"], allow_nan=False)
    calls[call["id"]] = call["function"]
    return deepcopy(call)


def tool_result(call_id, content, failed, calls, answered):
    """Retain the native result under its original call identity, including errors."""
    if call_id not in calls or call_id in answered:
        raise ValueError("A result must match one unanswered native tool call")
    answered.add(call_id)
    result = {"role": "tool", "content": text_parts(content), "tool_call_id": call_id, "function": calls[call_id]}
    if failed:
        result["error"] = {"type": "unknown", "message": "The native tool reported an error"}
    return result


def convert(records: list[dict]) -> list[dict]:
    """Convert the linear Goose session export directly to Inspect chat messages.

    Preserve native MCP call IDs, names, JSON arguments, text and error results.
    Results may arrive in any order, but each must answer one earlier call exactly
    once. Unsupported attachments/provider content fail visibly. Source records
    are copied and never modified; retain full native history across snapshots.
    """
    messages, calls, answered = [], {}, set()
    for row in records:
        role = row["role"]
        if role not in {"user", "assistant"}:
            raise ValueError("Unsupported Goose role")
        current = {"role": role, "content": []}
        had_result = False
        for part in row["content"]:
            kind = part["type"]
            if kind == "text":
                current["content"].extend(text_parts([part]))
            elif kind == "toolRequest":
                if role != "assistant" or part["toolCall"]["status"] != "success":
                    raise ValueError("Expected a decoded native assistant tool request")
                value = part["toolCall"]["value"]
                call = register_call(
                    {"id": part["id"], "function": value["name"], "arguments": value.get("arguments", {})}, calls
                )
                current.setdefault("tool_calls", []).append(call)
            elif kind == "toolResponse":
                if role != "user":
                    raise ValueError("Native tool responses require a user-role export entry")
                if current["content"] or current.get("tool_calls"):
                    messages.append(current)
                    current = {"role": role, "content": []}
                result = part["toolResult"]
                if result["status"] not in {"success", "error"}:
                    raise ValueError("Unsupported native tool response status")
                failed = result["status"] == "error"
                content = result["error"] if failed else result["value"]["content"]
                if failed and isinstance(content, dict):
                    content = json.dumps(content, ensure_ascii=False, allow_nan=False)
                failed = failed or result.get("value", {}).get("isError", False)
                messages.append(tool_result(part["id"], content, failed, calls, answered))
                had_result = True
            else:
                raise ValueError("Unsupported Goose content")
        if current["content"] or current.get("tool_calls") or not had_result:
            messages.append(current)
    return messages


async def send(client: AsyncWatcherClient, session_id: str, messages: list[dict]) -> None:
    """Observe captured tools against their historical context, then record the final tail.

    Native execution has already occurred. No Watcher result changes tool output or
    permissions. Failures propagate to the observation-only native boundary.
    """
    if not session_id:
        raise ValueError("A native session ID is required")
    await observe(client, PREFIX + session_id, messages)


async def run_hook(payload: dict, *, record_only: bool = False) -> None:
    """Export the completed Stop transcript through Goose's session command.

    A ten-second deadline bounds the export. If it expires or the hook task is
    cancelled, kill and reap the child before propagating the interruption.
    """
    session_id = payload["session_id"]
    process = await asyncio.create_subprocess_exec(
        "goose",
        "session",
        "export",
        "--session-id",
        session_id,
        "--format",
        "json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(10):
            output, _ = await process.communicate()
    except (TimeoutError, asyncio.CancelledError):
        with suppress(ProcessLookupError):
            process.kill()
        await process.communicate()
        raise
    if process.returncode:
        raise ValueError("Native session export failed")
    exported = json.loads(output)
    messages = convert(exported["conversation"])
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        if record_only:
            outcomes = await client.pre_tool_use_hook(
                [], messages=messages, external_ids={"other": PREFIX + session_id}, timeout=10
            )
            if outcomes != []:
                raise ValueError("Transcript-only submission returned unexpected outcomes")
        else:
            await send(client, session_id, messages)


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
