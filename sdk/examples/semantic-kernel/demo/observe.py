"""ChatCompletionAgent with an in-process model transport and real native tools."""

import asyncio
import json
import os
import sys
from uuid import uuid4

import httpx2 as httpx
from openai import AsyncOpenAI
from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent, ChatHistoryAgentThread
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.filters import FilterTypes
from semantic_kernel.functions import kernel_function
from watcher_semantic_kernel.adapter import observe
from watcher_semantic_kernel.native import WatcherFilter

from watcher_sdk import AsyncWatcherClient


async def run_native(monitor=None, effect=lambda value: str(value * 2)):
    """Run the real agent and connector loop; only HTTP model responses are fixtures."""

    class Arithmetic:
        @kernel_function(name="double", description="Double an integer")
        def double(self, value: int) -> str:
            return effect(value)

    requests = []

    async def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"double-{value}",
                        "type": "function",
                        "function": {"name": "math-double", "arguments": json.dumps({"value": value})},
                    }
                    for value in [2, 3]
                ],
            }
            reason = "tool_calls"
        elif len(requests) == 2:
            results = {
                message["tool_call_id"]: message["content"] for message in body["messages"] if message["role"] == "tool"
            }
            assert results == {"double-2": "4", "double-3": "6"}, results
            message = {"role": "assistant", "content": "4 and 6"}
            reason = "stop"
        else:
            raise AssertionError("Unexpected fixture model retry")
        return httpx.Response(
            200,
            json={
                "id": f"fixture-{len(requests)}",
                "object": "chat.completion",
                "created": 0,
                "model": "fixture",
                "choices": [{"index": 0, "message": message, "finish_reason": reason}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            },
        )

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport,
        AsyncOpenAI(
            api_key="fixture-only", base_url="http://model.invalid/v1", http_client=transport, max_retries=0
        ) as model,
    ):
        kernel = Kernel()
        kernel.add_service(OpenAIChatCompletion(ai_model_id="fixture", async_client=model))
        kernel.add_plugin(Arithmetic(), plugin_name="math")
        if monitor is not None:
            kernel.add_filter(FilterTypes.AUTO_FUNCTION_INVOCATION, WatcherFilter(monitor))
        agent = ChatCompletionAgent(kernel=kernel, name="example")
        thread = ChatHistoryAgentThread()
        async for _response in agent.invoke(messages="Double 2 and 3", thread=thread):
            pass
        messages = [message async for message in thread.get_messages()]
    if monitor is not None:
        await monitor.record(messages)
    return messages


async def run_conversation():
    """Return the completed native history for post-run observation."""
    return await run_native()


async def main():
    """Send native history to Watcher without preventing already completed tools."""
    messages = await run_conversation()
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        outcomes = await observe(client, str(uuid4()), messages)
        json.dump([outcome.to_dict() for outcome in outcomes], sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
