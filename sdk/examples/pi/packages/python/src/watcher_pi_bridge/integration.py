"""Native completion hook to public Watcher SDK; see README for supported transcript shapes."""

import asyncio
import json
import os
import sys
from copy import deepcopy

import typer

from watcher_pi_bridge.monitoring import observe
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


PREFIX = "pi:"


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
    """Convert the current Pi branch directly to Inspect text/function messages.

    Preserve tool IDs, native names, visible thinking and linked error results.
    Provider namespace metadata does not change Pi's dispatch or hook tool name.
    Each result must match one earlier unanswered call, including its native name.
    Custom messages, images and compacted histories need a separate converter.
    Source records are copied and never modified; retain the complete branch.
    """
    messages, calls, answered = [], {}, set()
    for row in records:
        role = row["role"]
        if role == "toolResult":
            call_id = row["toolCallId"]
            if row.get("toolName") != calls.get(call_id):
                raise ValueError("Native result name does not match its call")
            messages.append(tool_result(call_id, row["content"], row["isError"], calls, answered))
            continue
        if role not in {"assistant", "user"}:
            raise ValueError("Unsupported Pi message role")
        content = row["content"]
        if isinstance(content, str):
            messages.append({"role": role, "content": content})
            continue
        message = {"role": role, "content": []}
        for block in content:
            kind = block["type"]
            if kind == "toolCall":
                if role != "assistant":
                    raise ValueError("Native tool calls require an assistant message")
                name = block["name"]
                call = register_call({"id": block["id"], "function": name, "arguments": block["arguments"]}, calls)
                message.setdefault("tool_calls", []).append(call)
            elif kind == "text":
                message["content"].extend(text_parts([block]))
            elif kind == "thinking" and isinstance(block.get("thinking"), str):
                message["content"].append({"type": "reasoning", "reasoning": block["thinking"]})
            else:
                raise ValueError("Unsupported Pi content")
        messages.append(message)
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
    """Consume the native plugin's snapshot; stdout remains the hook control channel."""
    messages = convert(payload["messages"])
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        if record_only:
            outcomes = await client.pre_tool_use_hook(
                [], messages=messages, external_ids={"other": PREFIX + payload["session_id"]}, timeout=10
            )
            if outcomes != []:
                raise ValueError("Transcript-only submission returned unexpected outcomes")
        else:
            await send(client, payload["session_id"], messages)


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
