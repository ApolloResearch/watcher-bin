"""Observe native Google Gen AI generate_content calls without automatic tool execution.

Pass complete Content history each turn. Provider IDs are preserved; missing call
IDs derive from history positions and results without IDs require a unique name.
Ambiguous results and unsupported parts are reported instead of guessed.
"""

import json
from copy import deepcopy
from typing import Any

from google import genai
from google.genai import types

from watcher_google_genai.observation import ObservationQueue


def make_client(api_key: str, base_url: str, http_client=None):
    """Return the native async client; automatic tool calling is disabled per request."""
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            base_url=base_url,
            api_version="v1beta",
            httpx_async_client=http_client,
        ),
    ).aio


def messages_from_contents(contents: list[types.Content]) -> list[dict]:
    """Map text, visible thoughts, calls, and results; reject unrepresentable parts.

    Stable fallback IDs require full, untrimmed history. A native result ID wins;
    without it, exactly one unresolved call of that name must exist.
    """
    messages = []
    pending = {}
    seen = set()
    for index, content in enumerate(contents):
        if content.role not in ("user", "model"):
            raise ValueError("Unsupported content role")
        message: dict[str, Any] = {"role": "assistant" if content.role == "model" else "user", "content": []}
        for part_index, part in enumerate(content.parts or []):
            if part.text is not None:
                message["content"].append(
                    {"type": "reasoning", "reasoning": part.text}
                    if part.thought
                    else {"type": "text", "text": part.text}
                )
            elif part.function_call is not None:
                call = part.function_call
                if content.role != "model" or not call.name or call.partial_args or call.will_continue:
                    raise ValueError("Incomplete function call")
                call_id = call.id or f"genai-{index}-{part_index}"
                if call_id in seen:
                    raise ValueError("Duplicate function call ID")
                seen.add(call_id)
                pending[call_id] = call.name
                message.setdefault("tool_calls", []).append(
                    {"id": call_id, "function": call.name, "arguments": deepcopy(call.args or {}), "type": "function"}
                )
            elif part.function_response is not None:
                result = part.function_response
                matches = [key for key, name in pending.items() if name == result.name]
                call_id = result.id or (matches[0] if len(matches) == 1 else None)
                if not call_id or pending.get(call_id) != result.name:
                    raise ValueError("Ambiguous or unmatched function response")
                if message["content"] or message.get("tool_calls"):
                    messages.append(message)
                    message = {"role": "user", "content": []}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(result.response, ensure_ascii=False),
                    }
                )
                del pending[call_id]
            else:
                raise ValueError("Unsupported content part")
        if message["content"] or message.get("tool_calls"):
            messages.append(message)
    return messages


class Observation(ObservationQueue):
    """Map native messages and queue bounded, ordered observe-mode monitoring."""

    def record(self, contents: list[types.Content], response: types.GenerateContentResponse):
        try:
            if not response.candidates or len(response.candidates) != 1:
                raise ValueError("One complete candidate is required")
            candidate = response.candidates[0]
            if candidate.finish_reason != types.FinishReason.STOP or candidate.content is None:
                raise ValueError("Incomplete response")
            messages = messages_from_contents([*contents, candidate.content])
            generated = messages_from_contents([candidate.content])
            # IDs without provider values depend on the complete history position.
            count = len(generated[-1].get("tool_calls", [])) if generated else 0
            calls = messages[-1].get("tool_calls", []) if count else []
            inputs = [
                {"tool_use_id": call["id"], "tool_name": call["function"], "tool_input": call["arguments"]}
                for call in calls
            ]
        except ValueError as error:
            self.fail(type(error).__name__)
            return
        self.enqueue(messages, inputs)


async def complete(client, observation: Observation, *, model: str, contents: list[types.Content], tools=None):
    """Generate one buffered native turn, preserving the caller's Content objects.

    Only declarations, not Python callables, should be supplied as tools. The
    caller executes tools and supplies FunctionResponse parts on the next turn.
    """
    history = deepcopy(contents)
    response = await client.models.generate_content(
        model=model,
        contents=history,
        config=types.GenerateContentConfig(
            tools=tools, automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        ),
    )
    observation.record(history, response)
    return response
