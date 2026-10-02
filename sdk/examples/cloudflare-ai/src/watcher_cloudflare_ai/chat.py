"""Convert complete textual Chat exports to Watcher transcript messages."""

import json
from typing import Any, cast


class UnsupportedExchange(ValueError):
    """An exchange cannot be represented faithfully by this example."""


def _object(pairs: list[tuple[str, Any]]) -> dict:
    """Reject duplicate JSON keys instead of grading an ambiguous argument object."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise UnsupportedExchange("Duplicate JSON key")
        result[key] = value
    return result


def decode_json(value: str | bytes) -> Any:
    """Decode strict JSON while preserving integer, float, boolean and null types."""

    def invalid_constant(value: str) -> None:
        raise UnsupportedExchange("Non-finite JSON number")

    return json.loads(value, object_pairs_hook=_object, parse_constant=invalid_constant)


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise UnsupportedExchange(f"Missing or invalid {label}")
    return value


def _message(message: Any) -> dict:
    """Convert the supported textual Chat message shape without changing call IDs."""
    if not isinstance(message, dict):
        raise UnsupportedExchange("Message must be an object")
    role = message.get("role")
    if role not in ("system", "developer", "user", "assistant", "tool"):
        raise UnsupportedExchange("Unsupported message role")
    for field in ("function_call", "audio", "reasoning", "reasoning_content", "reasoning_details"):
        if message.get(field) is not None:
            raise UnsupportedExchange("Unsupported non-text message field")
    content = message.get("content")
    if content is None:
        content = ""
    if not isinstance(content, str):
        raise UnsupportedExchange("Only text message content is supported")
    converted = {"role": "system" if role == "developer" else role, "content": content}
    refusal = message.get("refusal")
    if refusal is not None:
        if role != "assistant" or not isinstance(refusal, str):
            raise UnsupportedExchange("Unsupported refusal")
        converted["content"] += ("\n" if content else "") + refusal
    if role == "tool":
        converted["tool_call_id"] = _string(message.get("tool_call_id"), "tool result ID")
    calls = message.get("tool_calls")
    if calls is not None:
        if role != "assistant" or not isinstance(calls, list):
            raise UnsupportedExchange("Invalid tool calls")
        converted["tool_calls"] = []
        for call in calls:
            if not isinstance(call, dict) or call.get("type") != "function":
                raise UnsupportedExchange("Only client function tools are supported")
            function = call.get("function")
            if not isinstance(function, dict) or not isinstance(function.get("arguments"), str):
                raise UnsupportedExchange("Function arguments must be a JSON string")
            arguments = decode_json(function["arguments"])
            if not isinstance(arguments, dict):
                raise UnsupportedExchange("Function arguments must be a JSON object")
            converted["tool_calls"].append(
                {
                    "id": _string(call.get("id"), "tool call ID"),
                    "type": "function",
                    "function": _string(function.get("name"), "function name"),
                    "arguments": arguments,
                }
            )
    return converted


def validate_request(request: Any, *, allow_stream: bool = False) -> list[dict]:
    """Validate a complete request before model invocation; return Inspect messages.

    Parallel alternatives, server-maintained history and executable tool formats
    outside Chat function calls are rejected. Streams require a native gateway
    plugin that reconstructs the complete body before calling evaluate().
    """
    if not isinstance(request, dict):
        raise UnsupportedExchange("Request must be an object")
    _string(request.get("model"), "model")
    if type(request.get("stream", False)) is not bool:
        raise UnsupportedExchange("stream must be a boolean")
    if request.get("stream") and not allow_stream:
        raise UnsupportedExchange("Streaming is unavailable on this gateway route")
    if type(request.get("n", 1)) is not int or request.get("n", 1) != 1:
        raise UnsupportedExchange("Exactly one completion choice is required")
    for key in ("functions", "function_call", "previous_response_id", "conversation", "audio"):
        if request.get(key) is not None:
            raise UnsupportedExchange(f"Unsupported request option: {key}")
    tools = request.get("tools", [])
    if not isinstance(tools, list) or any(not isinstance(t, dict) or t.get("type") != "function" for t in tools):
        raise UnsupportedExchange("Only client function tools are supported")
    raw_messages = request.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise UnsupportedExchange("A complete messages list is required")
    messages = [_message(message) for message in raw_messages]
    _validate_ids(messages)
    return messages


def _validate_ids(messages: list[dict]) -> None:
    """Reject duplicate call IDs and unmatched results within the supplied history."""
    pending = set()
    seen = set()
    for message in messages:
        for call in message.get("tool_calls", []):
            if call["id"] in seen:
                raise UnsupportedExchange("Duplicate tool call ID")
            seen.add(call["id"])
            pending.add(call["id"])
        if message["role"] == "tool":
            identifier = message["tool_call_id"]
            if identifier not in pending:
                raise UnsupportedExchange("Tool result has no matching pending call")
            pending.remove(identifier)


def exchange_messages(request: object, response: object) -> list[dict]:
    """Convert a complete textual Chat exchange, including history and tool results.

    A completed export may originate from a streaming request, but its response
    must be a complete Chat JSON object. Raw SSE, partial responses, multiple
    alternatives and unsupported content fail before any Watcher submission.
    """
    messages = validate_request(request, allow_stream=True)
    if not isinstance(response, dict):
        raise UnsupportedExchange("Response must be an object")
    choices = cast(dict[str, object], response).get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise UnsupportedExchange("Exactly one response choice is required")
    choice = cast(dict[str, object], choices[0])
    if type(choice.get("index")) is not int or choice["index"] != 0:
        raise UnsupportedExchange("Unexpected response choice index")
    message = _message(choice.get("message"))
    if message["role"] != "assistant":
        raise UnsupportedExchange("Response must contain an assistant message")
    if choice.get("finish_reason") != ("tool_calls" if message.get("tool_calls") else "stop"):
        raise UnsupportedExchange("Response is incomplete")
    messages.append(message)
    _validate_ids(messages)
    return messages
