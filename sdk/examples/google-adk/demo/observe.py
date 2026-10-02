"""Credential-free native model/tool fixture; main records it to a real Watcher."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types
from watcher_google_adk.adapter import observe
from watcher_google_adk.native import ConversationHistory

from watcher_sdk import AsyncWatcherClient


class DeterministicModel(BaseLlm):
    """ADK's native model interface returns calls then an answer without network."""

    async def generate_content_async(self, llm_request, stream=False):
        if any(part.function_response for content in llm_request.contents for part in content.parts or []):
            content = types.Content(role="model", parts=[types.Part(text="4 and 6")])
        else:
            content = types.Content(
                role="model",
                parts=[
                    types.Part(function_call=types.FunctionCall(id="double-2", name="double", args={"value": 2})),
                    types.Part(function_call=types.FunctionCall(id="double-3", name="double", args={"value": 3})),
                ],
            )
        yield LlmResponse(content=content)


async def run_conversation():
    """Run the real in-memory runner, tool dispatcher and session event persistence."""

    def double(value: int) -> str:
        """Return twice the supplied integer."""
        return str(value * 2)

    context = ConversationHistory()
    agent = LlmAgent(
        name="example",
        model=DeterministicModel(model="deterministic"),
        tools=[double],
        before_model_callback=context.before_model_callback,
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
    return context.messages(session)


async def main():
    """Send the deterministic native run to the configured real Watcher server."""
    messages = await run_conversation()
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        outcomes = await observe(client, str(uuid4()), messages)
        json.dump([outcome.to_dict() for outcome in outcomes], sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
