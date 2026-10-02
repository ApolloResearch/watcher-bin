"""Application-owned Agents SDK FunctionTool dispatch with native ToolContext."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from agents import Agent, RunConfig, Runner, function_tool
from watcher_openai_agents.adapter import messages_for_watcher
from watcher_openai_agents.monitoring import Monitor
from watcher_openai_agents.native import WatcherHooks, execute_tool

from demo.observe import DeterministicModel
from watcher_sdk import AsyncWatcherClient


async def run_dispatch_conversation(monitor, effect=lambda value: str(value * 2)):
    """Run public native model/tool APIs in an explicit application-owned loop."""

    @function_tool(failure_error_function=None)
    def double(value: int) -> str:
        """Double an integer."""
        return effect(value)

    model = DeterministicModel()
    history = [{"role": "user", "content": "Double 2 and 3"}]
    response = await model.get_response(None, history, None, [double], None, [], None)
    history.extend(item.model_dump(exclude_none=True) for item in response.output)
    results = await asyncio.gather(*(execute_tool(monitor, history, double, call) for call in response.output))
    history.extend(results)
    response = await model.get_response(None, history, None, [double], None, [], None)
    history.extend(item.model_dump(exclude_none=True) for item in response.output)
    await monitor.record(history)
    return history


async def run_conversation(monitor, effect=lambda value: str(value * 2)):
    """Run native Runner with parallel tools; the lifecycle hook gates their bodies."""

    @function_tool(failure_error_function=None)
    def double(value: int) -> str:
        """Double an integer."""
        return effect(value)

    hooks = WatcherHooks(monitor)
    agent = Agent(name="example", model=DeterministicModel(), tools=[double])
    await Runner.run(agent, "Double 2 and 3", hooks=hooks, run_config=RunConfig(tracing_disabled=True))
    await monitor.record(hooks.history)
    return hooks.history


async def main():
    """Execute the local arithmetic tools under the configured Watcher policy."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        monitor = Monitor(client, str(uuid4()), timeout=float(os.environ.get("WATCHER_TIMEOUT", "420")))
        messages = await run_conversation(monitor)
        json.dump(messages_for_watcher(messages), sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
