"""Observe native Ollama chat requests with adapter-owned stable tool identities.

Ollama messages identify results by tool name, not call ID. Full history provides
stable call positions; same-name parallel calls cannot be paired without ambiguity
and are rejected. The original provider response is still returned.
"""

from copy import deepcopy
from typing import Any

from ollama import AsyncClient, ChatResponse, Message

from watcher_ollama.observation import ObservationQueue


def make_client(base_url: str, transport=None) -> AsyncClient:
    """Use Ollama's documented HTTPX keyword forwarding for isolated transports."""
    return AsyncClient(host=base_url, transport=transport)


def messages_from_native(history: list[Message]) -> list[dict]:
    """Map buffered text/thought/tool messages; require unique outstanding result names."""
    messages = []
    pending = {}
    for index, message in enumerate(history):
        if message.images or message.role not in ("user", "system", "assistant", "tool"):
            raise ValueError("Unsupported message")
        mapped: dict[str, Any] = {"role": message.role, "content": message.content or ""}
        if message.thinking:
            mapped["content"] = [
                {"type": "reasoning", "reasoning": message.thinking},
                {"type": "text", "text": message.content or ""},
            ]
        if message.tool_calls:
            if message.role != "assistant":
                raise ValueError("Calls require assistant role")
            mapped["tool_calls"] = []
            for call_index, call in enumerate(message.tool_calls):
                if not call.function.name or call.function.name in pending.values():
                    raise ValueError("Parallel calls with the same name are ambiguous")
                call_id = f"ollama-{index}-{call_index}"
                pending[call_id] = call.function.name
                mapped["tool_calls"].append(
                    {
                        "id": call_id,
                        "function": call.function.name,
                        "arguments": deepcopy(dict(call.function.arguments)),
                        "type": "function",
                    }
                )
        if message.role == "tool":
            matches = [key for key, name in pending.items() if name == message.tool_name]
            if len(matches) != 1:
                raise ValueError("Unmatched tool result")
            mapped["tool_call_id"] = matches[0]
            del pending[matches[0]]
        messages.append(mapped)
    return messages


class Observation(ObservationQueue):
    """Map native messages and queue bounded, ordered observe-mode monitoring."""

    def record(self, history: list[Message], response: ChatResponse):
        try:
            if not response.done or response.done_reason not in (None, "stop"):
                raise ValueError("Incomplete response")
            messages = messages_from_native([*history, response.message])
            inputs = [
                {"tool_use_id": call["id"], "tool_name": call["function"], "tool_input": call["arguments"]}
                for call in messages[-1].get("tool_calls", [])
            ]
        except ValueError as error:
            self.fail(type(error).__name__)
            return
        self.enqueue(messages, inputs)


async def complete(client: AsyncClient, observation: Observation, *, model: str, messages: list[Message], tools=None):
    """Call native buffered chat and queue a detached snapshot including its response."""
    history = deepcopy(messages)
    response = await client.chat(model=model, messages=history, tools=tools, stream=False)
    observation.record(history, response)
    return response
