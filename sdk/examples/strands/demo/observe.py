"""Credential-free native model/tool fixture; main records it to a real Watcher."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from strands import Agent, tool
from strands.models import Model
from watcher_strands.adapter import observe
from watcher_strands.native import agent_history

from watcher_sdk import AsyncWatcherClient


class DeterministicModel(Model):
    """Stream native provider events so Strands assembles and executes two calls."""

    def update_config(self, **model_config):
        pass

    def get_config(self):
        return {}

    async def structured_output(self, *args, **kwargs):
        raise NotImplementedError("Tool fixture only")
        yield

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        has_results = any("toolResult" in block for message in messages for block in message["content"])
        yield {"messageStart": {"role": "assistant"}}
        if has_results:
            yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "4 and 6"}}}
            yield {"contentBlockStop": {"contentBlockIndex": 0}}
        else:
            for index, value in enumerate([2, 3]):
                yield {
                    "contentBlockStart": {
                        "contentBlockIndex": index,
                        "start": {"toolUse": {"toolUseId": f"double-{value}", "name": "double"}},
                    }
                }
                yield {
                    "contentBlockDelta": {
                        "contentBlockIndex": index,
                        "delta": {"toolUse": {"input": json.dumps({"value": value})}},
                    }
                }
                yield {"contentBlockStop": {"contentBlockIndex": index}}
        yield {"messageStop": {"stopReason": "end_turn" if has_results else "tool_use"}}
        yield {
            "metadata": {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}, "metrics": {"latencyMs": 0}}
        }


async def run_conversation(*, system_prompt: str | None = None):
    """Run native tools without a provider and retain the configured system prompt in the returned history."""

    @tool
    def double(value: int) -> str:
        """Return twice the supplied integer."""
        return str(value * 2)

    agent = Agent(model=DeterministicModel(), tools=[double], callback_handler=None, system_prompt=system_prompt)
    await agent.invoke_async("Double 2 and 3")
    return agent_history(agent)


async def main():
    """Send the deterministic native run to the configured real Watcher server."""
    messages = await run_conversation()
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        outcomes = await observe(client, str(uuid4()), messages)
        json.dump([outcome.to_dict() for outcome in outcomes], sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
