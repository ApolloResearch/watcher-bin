"""Monitor AssistantAgent's public stream before its native tool scheduler resumes."""

import json
from contextlib import aclosing

from autogen_agentchat.base import TaskResult
from autogen_agentchat.messages import ToolCallRequestEvent


async def run_monitored(agent, monitor, *, task, history=()):
    """Run an AssistantAgent turn, holding each pending batch before native dispatch.

    Supply the complete prior emitted history when reusing an agent. The agent's
    run_stream must be consumed here alone: background prefetch defeats the gate.
    On refusal the stream closes before any tools in that batch are scheduled.
    Earlier successful batches are not rolled back. Register a separate monitor
    for each conversation. Agent system instructions must be included in history
    as an AutoGen SystemMessage when the agent is configured with them.

    Returns prior history plus this turn's actual TaskResult messages, and submits
    that full history to Watcher. Supports AssistantAgent's text/function events;
    unsupported events fail before a pending batch is released.
    """
    prior = list(history)
    pending = list(prior)
    async with aclosing(agent.run_stream(task=task)) as stream:
        async for event in stream:
            if isinstance(event, TaskResult):
                completed = prior + event.messages
                await monitor.record(completed)
                return completed
            pending.append(event)
            if isinstance(event, ToolCallRequestEvent):
                for call in event.content:
                    await monitor.before(pending, call.id, call.name, json.loads(call.arguments))
    raise RuntimeError("AutoGen ended without a TaskResult")
