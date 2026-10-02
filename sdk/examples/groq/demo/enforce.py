"""Run a buffered native conversation whose application tool waits for Watcher approval."""

import asyncio
import os
import sys
from uuid import uuid4

from watcher_groq.integration import make_client
from watcher_groq.monitoring import Monitor, run_turn

from watcher_sdk import AsyncWatcherClient


async def weather(*, city: str) -> dict:
    """Return an explicit demonstration value after authorization; no weather service is queried."""
    return {"city": city, "weather": "demonstration value"}


async def main() -> None:
    """Use the configured native provider and record the full tool conversation."""
    session_id = str(uuid4())
    history = [{"role": "user", "content": "Call weather for Paris, then summarize."}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "weather",
                "description": "Return demonstration weather",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
            },
        }
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
                messages=history,
                tools=tools,
                functions={"weather": weather},
            )
            if history[-1]["role"] == "assistant" and not history[-1].get("tool_calls"):
                break
        else:
            raise RuntimeError("Model did not finish within the example step budget")
    sys.stdout.write(f"Recorded conversation {session_id}; verify its tool results and final answer in Analyzer.\n")


if __name__ == "__main__":
    asyncio.run(main())
