"""Convert retained native chat-message snapshots into Watcher's Inspect format.

Only visible text/reasoning and explicitly identified function calls/results are
supported. This is not an HTTP exchange parser; the caller owns native history
retention. Unsupported multimodal content and ambiguous identities fail visibly.
"""

import json
from copy import deepcopy
from typing import Any


def object_arguments(value: Any) -> dict[str, Any]:
    """Decode a tool argument object without losing duplicate keys or literal types."""

    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("Duplicate tool argument key")
            result[key] = item
        return result

    if isinstance(value, str):
        value = json.loads(value, object_pairs_hook=unique)
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("Tool arguments must be an object")
    json.dumps(value, allow_nan=False)
    return deepcopy(value)


def visible_content(value: Any) -> str | list[dict[str, Any]]:
    """Retain text content without flattening unknown attachments into text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        raise ValueError("Unsupported native content")
    result = []
    for part in value:
        if not isinstance(part, dict) or part.get("type") != "text" or not isinstance(part.get("text"), str):
            raise ValueError("Only text content blocks are supported")
        result.append({"type": "text", "text": part["text"]})
    return result


def normalize_chat(history: list[dict]) -> list[dict]:
    """Copy native chat snapshots while preserving ordered call/result identities.

    Developer instructions map to Inspect system messages. Parallel results may
    arrive in any order but must each match one prior unanswered call. Function
    arguments are decoded as JSON objects; missing IDs and legacy name-only
    function calls are rejected. No response or result is synthesized.
    """
    output: list[dict[str, Any]] = []
    calls: dict[str, str] = {}
    answered: set[str] = set()
    for row in history:
        role = "system" if row["role"] == "developer" else row["role"]
        if role not in {"system", "user", "assistant", "tool"} or row.get("function_call"):
            raise ValueError("Unsupported native role or name-only function call")
        content = visible_content(row.get("content"))
        reasoning = row.get("reasoning_content")
        if reasoning is not None:
            if role != "assistant" or not isinstance(reasoning, str):
                raise ValueError("Unsupported native reasoning content")
            parts = [{"type": "text", "text": content}] if isinstance(content, str) else content
            content = [{"type": "reasoning", "reasoning": reasoning}, *parts]
        message: dict[str, Any] = {"role": role, "content": content}
        native_calls = row.get("tool_calls") or []
        if native_calls:
            if role != "assistant":
                raise ValueError("Only assistant messages can request tools")
            for item in native_calls:
                identity, function = item["id"], item["function"]
                name = function["name"]
                if (
                    item.get("type", "function") != "function"
                    or not isinstance(identity, str)
                    or not identity
                    or identity in calls
                ):
                    raise ValueError("A unique native function-call ID is required")
                if not isinstance(name, str) or not name:
                    raise ValueError("A native function name is required")
                calls[identity] = name
                message.setdefault("tool_calls", []).append(
                    {"id": identity, "function": name, "arguments": object_arguments(function["arguments"])}
                )
        if role == "tool":
            identity = row["tool_call_id"]
            if (
                identity not in calls
                or identity in answered
                or (row.get("name") is not None and row["name"] != calls[identity])
            ):
                raise ValueError("Result identity does not match one unanswered call")
            message.update(tool_call_id=identity, function=calls[identity])
            if row.get("is_error"):
                message["error"] = {"type": "unknown", "message": "The native tool reported an error"}
            answered.add(identity)
        output.append(message)
    return output
