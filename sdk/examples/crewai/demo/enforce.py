"""CrewAI registered tool wrapper; run only in the supplied network-none container."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from crewai import Agent, Crew, Task
from crewai.tools import tool
from watcher_crewai.adapter import ObservedLLM, messages_for_watcher
from watcher_crewai.monitoring import Monitor
from watcher_crewai.native import MonitoredTrace

from demo.observe import DeterministicModel
from watcher_sdk import AsyncWatcherClient


async def run_conversation(monitor, effect=lambda value: str(value * 2)):
    """Run a real Crew task; tool bodies wait for Watcher on a separate active loop."""
    trace = MonitoredTrace(monitor, asyncio.get_running_loop(), "Double 2 and 3")

    @tool("double")
    def double(value: int) -> str:
        """Double an integer."""
        return trace.invoke("double", {"value": value}, effect)

    agent = Agent(
        role="calculator",
        goal="Double numbers",
        backstory="An arithmetic helper",
        llm=ObservedLLM(DeterministicModel(), trace),
        tools=[double],
        step_callback=trace.on_step,
        verbose=False,
        allow_delegation=False,
        max_iter=5,
    )
    task = Task(description="Double 2 and 3", expected_output="4 and 6", agent=agent)
    result = await asyncio.to_thread(Crew(agents=[agent], tasks=[task], verbose=False, tracing=False).kickoff)
    trace.finish(result.raw)
    await monitor.record(trace.messages)
    return trace.messages


async def main():
    """Execute the local arithmetic tools under the configured Watcher policy."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        monitor = Monitor(client, str(uuid4()), timeout=float(os.environ.get("WATCHER_TIMEOUT", "420")))
        messages = await run_conversation(monitor)
        json.dump(messages_for_watcher(messages), sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
