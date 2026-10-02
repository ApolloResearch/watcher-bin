"""Native completion hook to public Watcher SDK; see README for supported transcript shapes."""

import asyncio
import json
import os
import sys
from pathlib import Path

from openhands.sdk import LLM, Agent, LLMConvertibleEvent
from openhands.sdk.conversation import LocalConversation
from pydantic import SecretStr

from watcher_openhands.conversion import normalize_chat
from watcher_openhands.monitoring import observe
from watcher_sdk import AsyncWatcherClient

PREFIX = "openhands:"


def convert(records: list[dict]) -> list[dict]:
    """Convert the harness's Chat Completions message snapshot without adding a turn.

    Multimodal resource attachments and compaction require harness-specific replay;
    reject them instead of silently losing their context.
    """
    if any(row.get("images") or row.get("resources") or row.get("context_boundary") for row in records):
        raise ValueError("Attachments and compaction are not supported")
    return normalize_chat(records)


class Recorder:
    """Collect the native SDK's LLM-convertible events with no network I/O in callbacks."""

    def __init__(self):
        self.messages = []

    def __call__(self, event):
        if isinstance(event, LLMConvertibleEvent):
            self.messages.append(
                event.to_llm_message().to_chat_dict(
                    cache_enabled=False,
                    vision_enabled=True,
                    function_calling_enabled=True,
                    force_string_serializer=False,
                    send_reasoning_content=True,
                )
            )


async def run_openhands(prompt: str, cwd: str, model: str, client: AsyncWatcherClient) -> None:
    """Run an OpenHands conversation with its normal policy, observing after completion."""
    recorder = Recorder()
    llm = LLM(model=model, api_key=SecretStr(os.environ["LLM_API_KEY"]))
    conversation = LocalConversation(
        agent=Agent(llm=llm, tools=[]),
        workspace=cwd,
        callbacks=[recorder],
        profile_store_dir=Path(cwd) / ".openhands-profiles",
    )
    try:
        conversation.send_message(prompt)
        await asyncio.to_thread(conversation.run)
    finally:
        await send(client, str(conversation.id), convert(recorder.messages))


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
