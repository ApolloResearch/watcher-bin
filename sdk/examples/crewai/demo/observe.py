"""Credential-free native model/tool fixture; main records it to a real Watcher."""

import os

os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_TELEMETRY_DISABLED"] = "true"
os.environ["CREWAI_TESTING"] = "true"
os.environ["CREWAI_TRACING_ENABLED"] = "false"

import asyncio
import json
import sys
from uuid import uuid4

from crewai import Agent, Crew, Task
from crewai.llms.base_llm import BaseLLM
from crewai.tools import tool
from watcher_crewai.adapter import ObservedLLM, WatcherTrace, observe

from watcher_sdk import AsyncWatcherClient


class DeterministicModel(BaseLLM):
    """CrewAI's custom LLM interface produces parseable native ReAct actions."""

    def __init__(self):
        super().__init__(model="deterministic")
        self.turn = 0

    def call(self, messages, *args, **kwargs):
        self.turn += 1
        if self.turn == 1:
            return 'Thought: Double two\nAction: double\nAction Input: {"value": 2}'
        if self.turn == 2:
            return 'Thought: Double three\nAction: double\nAction Input: {"value": 3}'
        return "Thought: Finished\nFinal Answer: 4 and 6"


async def run_conversation(model=None, *, trace=None, executions=None):
    """Run a real Crew task with a supplied BaseLLM or deterministic local model.

    Optional trace and execution lists let a contained fixture independently
    compare callback capture with actual tool invocations. No Watcher I/O occurs
    here; publish the returned history after completion.
    """

    @tool("double")
    def double(value: int) -> str:
        """Return twice the supplied integer."""
        result = str(value * 2)
        if executions is not None:
            executions.append({"tool": "double", "arguments": {"value": value}, "result": result})
        return result

    trace = trace if trace is not None else WatcherTrace("Double 2 and 3")
    agent = Agent(
        role="calculator",
        goal="Double numbers",
        backstory="A deterministic arithmetic helper",
        llm=ObservedLLM(model if model is not None else DeterministicModel(), trace),
        tools=[double],
        step_callback=trace.on_step,
        verbose=False,
        allow_delegation=False,
    )
    task = Task(description="Double 2 and 3", expected_output="4 and 6", agent=agent)
    result = await asyncio.to_thread(Crew(agents=[agent], tasks=[task], verbose=False, tracing=False).kickoff)
    trace.finish(result.raw)
    return trace.messages


async def main():
    """Send the deterministic native run to the configured real Watcher server."""
    messages = await run_conversation()
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        outcomes = await observe(client, str(uuid4()), messages)
        json.dump([outcome.to_dict() for outcome in outcomes], sys.stdout, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
