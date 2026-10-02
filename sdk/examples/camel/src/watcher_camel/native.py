"""Hold CAMEL model output before ChatAgent schedules its native tools."""

import json
from copy import deepcopy

from camel.models import BaseModelBackend
from openai.types.chat import ChatCompletion

from watcher_camel.monitoring import ToolBlocked


class MonitoredModel(BaseModelBackend):
    """Wrap a backend for ChatAgent.astep with complete, non-streaming responses.

    All calls in the model's next response must pass Watcher before CAMEL sees
    that response. Native ChatAgent dispatch, tool validation and retained memory
    remain in charge. Pass one Monitor per conversation; do not share this wrapper
    between concurrent conversations. Provider-executed tools are outside this
    boundary. Synchronous calls and streaming model configurations are rejected.
    """

    def __init__(self, backend, monitor):
        if backend.model_config_dict.get("stream"):
            raise ValueError("MonitoredModel requires a non-streaming backend")
        self.backend = backend
        self.monitor = monitor
        super().__init__(backend.model_type, model_config_dict=deepcopy(backend.model_config_dict))

    @property
    def token_counter(self):
        return self.backend.token_counter

    def _run(self, messages, response_format=None, tools=None):
        raise RuntimeError("MonitoredModel requires ChatAgent.astep")

    async def _arun(self, messages, response_format=None, tools=None):
        """Gate original response IDs and arguments before native dispatch begins."""
        history = deepcopy(messages)
        response = await self.backend.arun(messages, response_format=response_format, tools=tools)
        if not isinstance(response, ChatCompletion) or len(response.choices) != 1:
            raise ToolBlocked("One complete non-streaming model response is required")
        choice = response.choices[0]
        message = choice.message
        allowed_reasons = {"tool_calls"} if message.tool_calls else {"stop", "length", "content_filter"}
        if choice.finish_reason not in allowed_reasons:
            raise ToolBlocked("Incomplete executable or unsupported model response")
        if message.function_call is not None:
            raise ToolBlocked("Legacy function calls are unsupported")
        history.append(message.model_dump(exclude_none=True))
        for call in message.tool_calls or []:
            if call.type != "function":
                raise ToolBlocked("Only client function tools are supported")
            await self.monitor.before(history, call.id, call.function.name, json.loads(call.function.arguments))
        return response
