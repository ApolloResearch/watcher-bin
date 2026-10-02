"""Native completion hook to public Watcher SDK; see README for supported transcript shapes."""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

from aider.coders import Coder

from watcher_aider.conversion import normalize_chat
from watcher_aider.observation import Capture, ObservedIO, ObservedModel, run_prompt, send_capture
from watcher_sdk import AsyncWatcherClient

PREFIX = "aider:"


def convert(records: list[dict]) -> list[dict]:
    """Convert the harness's Chat Completions message snapshot without adding a turn.

    Multimodal resource attachments and compaction require harness-specific replay;
    reject them instead of silently losing their context.
    """
    if any(row.get("images") or row.get("resources") or row.get("context_boundary") for row in records):
        raise ValueError("Attachments and compaction are not supported")
    return normalize_chat(records)


async def run_aider(
    prompt: str, cwd: str, model: str, client: AsyncWatcherClient, *, fnames: list[str] | None = None
) -> Capture:
    """Run a nonstreaming whole-file Coder and observe its actual IO writes afterward.

    Start in the disposable workspace and pass the files Aider may edit. Normal
    native permission decisions remain in place. Application-owned write IDs come
    from IO invocations; model responses are never parsed to invent operations.
    The returned capture supports inspection or replay with send_capture. For
    multiple turns or retention before submission, inject ObservedModel/ObservedIO
    into Coder.create and call run_prompt and send_capture separately.
    """
    if Path.cwd().resolve() != Path(cwd).resolve():
        raise ValueError("Start the process in the intended disposable Aider workspace")
    capture = Capture()
    coder = Coder.create(
        main_model=ObservedModel(model, capture),
        io=ObservedIO(capture, yes=False),
        fnames=fnames,
        edit_format="whole",
        stream=False,
        use_git=False,
    )
    session_id = str(uuid.uuid4())
    try:
        await asyncio.to_thread(run_prompt, coder, capture, prompt)
    finally:
        await send_capture(client, session_id, capture)
    return capture


async def send(client: AsyncWatcherClient, session_id: str, messages: list[dict]) -> None:
    """Record a full snapshot, including final text; wait for recording acknowledgement.

    This is transcript-only observation: no pending calls are graded or blocked.
    The caller owns retry policy. A timeout may follow successful server storage.
    """
    if not session_id:
        raise ValueError("A native session ID is required")
    await client.pre_tool_use_hook(
        input=[],
        messages=messages,
        external_ids={"other": PREFIX + session_id},
        timeout=10,
    )


async def run_hook(payload: dict) -> None:
    """Consume the native plugin's snapshot; stdout remains the hook control channel."""
    messages = convert(payload["messages"])
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        await send(client, payload["session_id"], messages)


def main() -> None:
    """Consume native hook stdin. Observation failures never block the coding agent.

    Emit only a neutral hook response and a static diagnostic: transcript content,
    paths, credentials and server error bodies are never copied to stderr.
    """
    try:
        asyncio.run(run_hook(json.load(sys.stdin)))
    except Exception:
        sys.stderr.write("Watcher observation failed; transcript was not confirmed recorded.\n")
    sys.stdout.write("{}\n")


if __name__ == "__main__":
    main()
