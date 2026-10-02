"""Convert the example's supported native text/function blocks to Inspect messages.

This module handles captured native histories, not provider request/response
exchanges. Unknown content is rejected. The caller reconstructs its own native
branch/event ordering before conversion and supplies complete retained history.
"""

import json
from copy import deepcopy
from typing import Any


def text_parts(value: Any) -> list[dict[str, Any]]:
    """Copy text-only native result content, including an explicitly empty result."""
    if value is None:
        return []
    if isinstance(value, str):
        return [{"type": "text", "text": value}]
    if not isinstance(value, list):
        raise ValueError("Unsupported native text content")
    result = []
    for part in value:
        if not isinstance(part, dict) or part.get("type") != "text" or not isinstance(part.get("text"), str):
            raise ValueError("Unsupported native tool result content")
        result.append({"type": "text", "text": part["text"]})
    return result


def normalize_messages(history: list[dict]) -> list[dict]:
    """Preserve native text, visible thinking, function IDs and linked tool errors.

    Supported roles are system/user/assistant. Native tool_result blocks become
    tool-role messages in delivery order. Each must match one earlier unanswered
    tool_use ID; names and arguments come from that original request. Text around
    result blocks remains in order. Neither source blocks nor arguments are
    mutated, and no assistant reply or tool result is fabricated. String text
    uses the same content-block representation as native text lists so session
    exports and live completion snapshots preserve identical history prefixes.
    """
    output: list[dict[str, Any]] = []
    calls: dict[str, str] = {}
    answered: set[str] = set()
    for row in history:
        role = row["role"]
        if role not in {"system", "user", "assistant"}:
            raise ValueError("Unsupported native message role")
        content = row["content"]
        if isinstance(content, str):
            output.append({"role": role, "content": [{"type": "text", "text": content}]})
            continue
        if not isinstance(content, list):
            raise ValueError("Unsupported native message content")
        current: dict[str, Any] = {"role": role, "content": []}
        had_result = False
        for part in content:
            kind = part["type"]
            if kind == "text" and isinstance(part.get("text"), str):
                current["content"].append({"type": "text", "text": part["text"]})
            elif kind == "thinking" and isinstance(part.get("thinking"), str):
                current["content"].append({"type": "reasoning", "reasoning": part["thinking"]})
            elif kind == "tool_use":
                identity, name, arguments = part["id"], part["name"], part["input"]
                if role != "assistant" or not isinstance(identity, str) or not identity or identity in calls:
                    raise ValueError("Native tool IDs must be unique assistant requests")
                if not isinstance(name, str) or not name or not isinstance(arguments, dict):
                    raise ValueError("Native tool names and object arguments are required")
                json.dumps(arguments, allow_nan=False)
                calls[identity] = name
                current.setdefault("tool_calls", []).append(
                    {"id": identity, "type": "function", "function": name, "arguments": deepcopy(arguments)}
                )
            elif kind == "tool_result":
                identity = part["tool_use_id"]
                if role != "user" or identity not in calls or identity in answered:
                    raise ValueError("Native results must match one unanswered tool call")
                if current["content"] or current.get("tool_calls"):
                    output.append(current)
                    current = {"role": role, "content": []}
                result: dict[str, Any] = {
                    "role": "tool",
                    "tool_call_id": identity,
                    "function": calls[identity],
                    "content": text_parts(part.get("content")),
                }
                if part.get("is_error"):
                    result["error"] = {"type": "unknown", "message": "Tool reported an error"}
                output.append(result)
                answered.add(identity)
                had_result = True
            else:
                raise ValueError("Unsupported native message block")
        if current["content"] or current.get("tool_calls") or not had_result:
            output.append(current)
    return output
