"""Reusable smolagents execution boundary for synchronous Watcher monitoring.

Use these adapters with one Monitor per conversation. The runnable clients in
demo/enforce.py show native registration and final transcript recording.
"""

from copy import deepcopy

from smolagents import Model
from smolagents.memory import ActionStep, TaskStep, ToolCall

from watcher_smolagents.adapter import messages_for_watcher, model_context


class CapturedModel(Model):
    """Wrap a public Model.generate to retain the current step's real context.

    Use with buffered ToolCallingAgent generation. The tool stream carries call
    IDs before execution, while model_input_messages appears only at step end.
    Capturing this boundary lets the pending prefix match the completed observer.
    """

    def __init__(self, inner):
        super().__init__()
        self.inner = inner
        self.context = []

    def generate(self, messages, **kwargs):
        response = self.inner.generate(messages, **kwargs)
        self.context = model_context(deepcopy(messages)) + model_context([deepcopy(response)])
        return response


async def consume(monitor, agent, model, prompt):
    """Await each yielded ToolCall before requesting the next stream event.

    smolagents 1.22 yields every call before starting its tool thread pool.
    Closing the generator on rejection prevents any unstarted call in the batch.
    Do not prefetch or concurrently consume this iterator. State-variable argument
    substitution is outside this example: keep agent.state empty.
    """
    if agent.state:
        raise ValueError("State-variable argument substitution requires a separate adapter")
    events = [TaskStep(task=prompt)]
    completed = 1
    stream = agent.run(prompt, stream=True)
    try:
        for event in stream:
            events.append(event)
            if isinstance(event, ToolCall):
                if agent.state:
                    raise ValueError("State-variable argument substitution requires a separate adapter")
                prefix = messages_for_watcher(events[:completed]) + deepcopy(model.context)
                prefix.extend(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{"id": call.id, "function": call.name, "arguments": call.arguments}],
                    }
                    for call in events[completed:]
                    if isinstance(call, ToolCall)
                )
                await monitor.before_transcript(prefix, event.id, event.name, event.arguments)
            elif isinstance(event, ActionStep):
                completed = len(events)
    finally:
        try:
            stream.close()
        except RuntimeError as error:
            if str(error) != "generator ignored GeneratorExit":
                raise
            # smolagents yields its final ActionStep from a finally block. Closing
            # again terminates that suspended cleanup without resuming tool dispatch.
            stream.close()
    await monitor.record(events)
    return events
