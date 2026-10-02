"""FunctionAgent extension that holds pending output before native scheduling."""

from copy import deepcopy

from llama_index.core.agent.workflow import FunctionAgent
from pydantic import PrivateAttr


class MonitoredFunctionAgent(FunctionAgent):
    """Run LlamaIndex's workflow with Watcher gating each complete model output.

    Pass monitor= alongside ordinary FunctionAgent arguments and use agent.run.
    The public take_step extension runs before the workflow emits ToolCall
    events, so no tool in a refused response can execute. Calls retain the model's
    original identities and arguments. One instance belongs to one conversation.
    Use non-streaming model responses; retained text/function histories are the
    supported transcript format. Call monitor.record(memory.get_all()) after a
    successful run to submit native tool results and the final answer.
    """

    _monitor = PrivateAttr()

    def __init__(self, *, monitor, **kwargs):
        if kwargs.get("streaming", False):
            raise ValueError("MonitoredFunctionAgent requires streaming=False")
        super().__init__(streaming=False, **{key: value for key, value in kwargs.items() if key != "streaming"})
        self._monitor = monitor

    async def take_step(self, ctx, llm_input, tools, memory):
        """Await all decisions before returning output to the workflow scheduler."""
        scratchpad = deepcopy(await ctx.store.get(self.scratchpad_key, default=[]))
        history = [*deepcopy(llm_input), *scratchpad]
        output = await super().take_step(ctx, llm_input, tools, memory)
        history.append(output.response)
        for call in output.tool_calls:
            await self._monitor.before(history, call.tool_id, call.tool_name, call.tool_kwargs)
        return output
