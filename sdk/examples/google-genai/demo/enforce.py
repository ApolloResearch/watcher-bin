"""Run a buffered native conversation whose application tool waits for Watcher approval."""

import asyncio
import os
import sys
from uuid import uuid4

from google.genai import types
from watcher_google_genai.integration import make_client
from watcher_google_genai.monitoring import Monitor, run_turn

from watcher_sdk import AsyncWatcherClient


async def weather(*, city: str) -> dict:
    """Return an explicit demonstration value after authorization; no weather service is queried."""
    return {"city": city, "weather": "demonstration value"}


async def main() -> None:
    """Use the configured native provider and record the full tool conversation."""
    session_id = str(uuid4())
    history = [types.Content(role="user", parts=[types.Part(text="Call weather for Paris, then summarize.")])]
    tools = [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="weather",
                    description="Return demonstration weather",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={"city": types.Schema(type=types.Type.STRING)},
                        required=["city"],
                    ),
                )
            ]
        )
    ]
    async with (
        make_client(os.environ["PROVIDER_API_KEY"], os.environ["PROVIDER_BASE_URL"]) as provider,
        AsyncWatcherClient(os.environ["WATCHER_BASE_URL"], api_key=os.environ["WATCHER_API_KEY"]) as watcher,
    ):
        monitor = Monitor(watcher, session_id, timeout=float(os.environ.get("WATCHER_TIMEOUT", "420")))
        for _ in range(4):
            history = await run_turn(
                provider,
                monitor,
                model=os.environ["PROVIDER_MODEL"],
                contents=history,
                tools=tools,
                functions={"weather": weather},
            )
            if history[-1].role == "model" and not any(part.function_call for part in history[-1].parts):
                break
        else:
            raise RuntimeError("Model did not finish within the example step budget")
    sys.stdout.write(f"Submitted conversation {session_id}; verify its tool results and final answer in Analyzer.\n")


if __name__ == "__main__":
    asyncio.run(main())
