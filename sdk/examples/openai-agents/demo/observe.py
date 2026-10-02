"""Credential-free native model/tool fixture; main records it to a real Watcher."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from agents import Agent, RunConfig, Runner, function_tool
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
from watcher_openai_agents.adapter import observe

from watcher_sdk import AsyncWatcherClient


class DeterministicModel(Model):
    """Native Agents model interface returning calls then a final answer."""

    async def get_response(
        self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing, **kwargs
    ):
        output: list
        if isinstance(input, list) and any(item.get("type") == "function_call_output" for item in input):
            output = [
                ResponseOutputMessage(
                    id="answer",
                    role="assistant",
                    status="completed",
                    content=[ResponseOutputText(type="output_text", text="4 and 6", annotations=[])],
                    type="message",
                )
            ]
        else:
            output = [
                ResponseFunctionToolCall(
                    id="item-2", call_id="double-2", name="double", arguments='{"value":2}', type="function_call"
                ),
                ResponseFunctionToolCall(
                    id="item-3", call_id="double-3", name="double", arguments='{"value":3}', type="function_call"
                ),
            ]
        return ModelResponse(output=output, usage=Usage(), response_id=None)

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError("This fixture uses buffered model responses")
        yield


async def run_conversation():
    """Use Runner's real tool dispatch and native result export."""

    @function_tool
    def double(value: int) -> str:
        """Return twice the supplied integer."""
        return str(value * 2)

    agent = Agent(name="example", model=DeterministicModel(), tools=[double])
    result = await Runner.run(agent, "Double 2 and 3", run_config=RunConfig(tracing_disabled=True))
    return result.to_input_list()


async def main():
    """Send the deterministic native run to the configured real Watcher server."""
    messages = await run_conversation()
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        outcomes = await observe(client, str(uuid4()), messages)
        json.dump([outcome.to_dict() for outcome in outcomes], sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
