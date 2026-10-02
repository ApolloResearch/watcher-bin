"""Run a native Anthropic tool loop with synchronous enforcement or observation.

The application owns the file-writing tool. The public SDK checks the proposed
batch before dispatch; the next model call records tool results and final text.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Literal
from uuid import uuid4

from anthropic import AsyncAnthropic
from anthropic.types import Message
from watcher_anthropic import complete

from watcher_sdk import AsyncWatcherClient


async def run_demo(
    provider: AsyncAnthropic,
    watcher: AsyncWatcherClient,
    output_file: Path,
    *,
    session_id: str,
    model: str,
    enforcement: Literal["enforce", "observe"] = "enforce",
) -> Message:
    """Append allowed notes, then record their results and the final Messages answer.

    The caller supplies an existing parent directory and owns both clients. Model
    input cannot select another output path. A denied or incomplete batch raises
    before opening the file. Once tools execute, later recording failure cannot
    undo their effects; do not blindly retry this entire conversation.
    """
    history: list[dict[str, object]] = [
        {"role": "user", "content": "Use append_note to write a short greeting, then summarize it."}
    ]
    tools = [
        {
            "name": "append_note",
            "description": "Append a note to the example's file.",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
        }
    ]
    request = {"model": model, "max_tokens": 512, "messages": history, "tools": tools}
    response = await complete(provider, watcher, request, session_id, enforcement=enforcement)
    history.append({"role": "assistant", "content": [item.model_dump(mode="json") for item in response.content]})
    results = []
    for call in response.content:
        if call.type != "tool_use":
            continue
        arguments = call.input
        if call.name != "append_note" or not isinstance(arguments, dict) or set(arguments) != {"text"}:
            raise ValueError("Expected append_note with one text argument")
        if not isinstance(arguments["text"], str):
            raise ValueError("append_note text must be a string")
        with output_file.open("a") as destination:
            destination.write(arguments["text"] + "\n")
        results.append({"type": "tool_result", "tool_use_id": call.id, "content": "Note appended."})
    if results:
        history.append({"role": "user", "content": results})
    final = await complete(provider, watcher, request, session_id, enforcement=enforcement)
    if any(item.type == "tool_use" for item in final.content):
        raise ValueError("This bounded demonstration expects a final answer after one tool batch")
    return final


async def main(enforcement: Literal["enforce", "observe"] | None = None) -> None:
    """Use explicit service credentials and retain the demonstration's output file."""
    mode = enforcement if enforcement is not None else os.environ.get("WATCHER_EXAMPLE_MODE", "enforce")
    if mode not in ("enforce", "observe"):
        raise ValueError("WATCHER_EXAMPLE_MODE must be enforce or observe")
    output_file = Path(tempfile.mkdtemp(prefix="watcher-anthropic-example-")) / "notes.txt"
    session_id = str(uuid4())
    async with (
        AsyncAnthropic() as provider,
        AsyncWatcherClient(os.environ["WATCHER_API_URL"], api_key=os.environ["WATCHER_API_KEY"]) as watcher,
    ):
        result = await run_demo(
            provider,
            watcher,
            output_file,
            session_id=session_id,
            model=os.environ["ANTHROPIC_MODEL"],
            enforcement="enforce" if mode == "enforce" else "observe",
        )
    sys.stdout.write(
        f"Watcher external identity: {session_id}\nTool output: {output_file}\n{result.model_dump_json(indent=2)}\n"
    )


if __name__ == "__main__":
    asyncio.run(main())
