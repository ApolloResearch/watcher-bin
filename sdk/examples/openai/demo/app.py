"""Run a small native OpenAI tool loop with enforce or observe monitoring.

The example appends a model-supplied note to one application-selected file. Enforce
waits for a matching Watcher decision before opening that file; observe requests
the server's non-enforcing posture. Both modes retain results and the final answer.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Literal
from uuid import uuid4

from openai import AsyncOpenAI
from openai.types.responses import Response
from watcher_openai import complete

from watcher_sdk import AsyncWatcherClient


async def run_demo(
    provider: AsyncOpenAI,
    watcher: AsyncWatcherClient,
    output_file: Path,
    *,
    session_id: str,
    model: str,
    enforcement: Literal["enforce", "observe"] = "enforce",
) -> Response:
    """Execute one Responses tool batch, then record its results and final answer.

    The caller supplies an existing parent directory and owns both clients. The
    only supported tool appends text to ``output_file``; model arguments cannot
    choose another path. A refused or incomplete batch raises before any file
    action. A failure recording the final answer does not undo completed writes:
    do not retry this whole function after an uncertain result.
    """
    history: list[dict[str, object]] = [
        {"role": "user", "content": "Use append_note to write a short greeting, then summarize it."}
    ]
    tools = [
        {
            "type": "function",
            "name": "append_note",
            "description": "Append a note to the example's file.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
        }
    ]
    request = {"model": model, "input": history, "tools": tools}
    response = await complete(provider, watcher, request, session_id, enforcement=enforcement)
    if not isinstance(response, Response):
        raise TypeError("This demonstration uses the Responses API")
    history.extend(item.model_dump(mode="json", exclude_none=True) for item in response.output)
    for call in response.output:
        if call.type != "function_call":
            continue
        arguments = json.loads(call.arguments)
        if call.name != "append_note" or set(arguments) != {"text"} or not isinstance(arguments["text"], str):
            raise ValueError("Expected append_note with one text argument")
        with output_file.open("a") as destination:
            destination.write(arguments["text"] + "\n")
        history.append({"type": "function_call_output", "call_id": call.call_id, "output": "Note appended."})
    final = await complete(provider, watcher, request, session_id, enforcement=enforcement)
    if not isinstance(final, Response) or any(item.type == "function_call" for item in final.output):
        raise ValueError("This bounded demonstration expects a final answer after one tool batch")
    return final


async def main(enforcement: Literal["enforce", "observe"] | None = None) -> None:
    """Run against explicitly configured provider and Watcher services."""
    mode = enforcement if enforcement is not None else os.environ.get("WATCHER_EXAMPLE_MODE", "enforce")
    if mode not in ("enforce", "observe"):
        raise ValueError("WATCHER_EXAMPLE_MODE must be enforce or observe")
    output_file = Path(tempfile.mkdtemp(prefix="watcher-openai-example-")) / "notes.txt"
    session_id = str(uuid4())
    async with (
        AsyncOpenAI() as provider,
        AsyncWatcherClient(os.environ["WATCHER_API_URL"], api_key=os.environ["WATCHER_API_KEY"]) as watcher,
    ):
        result = await run_demo(
            provider,
            watcher,
            output_file,
            session_id=session_id,
            model=os.environ["OPENAI_MODEL"],
            enforcement="enforce" if mode == "enforce" else "observe",
        )
    sys.stdout.write(
        f"Watcher external identity: {session_id}\nTool output: {output_file}\n{result.model_dump_json(indent=2)}\n"
    )


if __name__ == "__main__":
    asyncio.run(main())
