"""Google ADK before_tool_callback that awaits the public Watcher SDK."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from watcher_google_adk.adapter import messages_for_watcher
from watcher_google_adk.monitoring import Monitor
from watcher_google_adk.native import ConversationHistory, before_tool_callback

from demo.observe import DeterministicModel
from watcher_sdk import AsyncWatcherClient


async def run_conversation(monitor, effect=lambda value: str(value * 2)):
    """Run the real ADK session, callback and parallel tool dispatcher."""

    def double(value: int) -> str:
        """Double an integer."""
        return effect(value)

    context = ConversationHistory()
    agent = LlmAgent(
        name="example",
        model=DeterministicModel(model="deterministic"),
        tools=[double],
        before_model_callback=context.before_model_callback,
        before_tool_callback=before_tool_callback(monitor, context),
    )
    runner = InMemoryRunner(agent=agent, app_name="sdk-example")
    session = await runner.session_service.create_session(app_name="sdk-example", user_id="example-user")
    async for _event in runner.run_async(
        user_id="example-user",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="Double 2 and 3")]),
    ):
        pass
    session = await runner.session_service.get_session(
        app_name="sdk-example", user_id="example-user", session_id=session.id
    )
    assert session is not None
    history = context.messages(session)
    await monitor.record(history)
    return history


async def main():
    """Execute the local arithmetic tools under the configured Watcher policy."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        monitor = Monitor(client, str(uuid4()), timeout=float(os.environ.get("WATCHER_TIMEOUT", "420")))
        messages = await run_conversation(monitor)
        json.dump(messages_for_watcher(messages), sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
