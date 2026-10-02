"""Convert bounded Cohere V2 text/function conversations for the public hook.

Cohere's native response format is not accepted by the raw-provider hook. These
helpers preserve text blocks, native tool IDs and exact JSON argument types;
unsupported content fails explicitly rather than disappearing from review.
"""

import json
from copy import deepcopy
from typing import Any

from pydantic import BaseModel


class Exchange(BaseModel):
    """The complete converted history and only its new response tool proposals."""

    messages: list[dict]
    inputs: list[dict]


def _object(pairs: list[tuple[str, Any]]) -> dict:
    """Reject duplicate argument keys so monitoring and application parsing agree."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate tool argument key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError("Non-finite tool argument")


def _text_content(value: Any) -> str | list[dict]:
    """Keep supported native text-block boundaries without coercing other content."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if not isinstance(value, list) or any(
        not isinstance(block, dict) or block.get("type") != "text" or not isinstance(block.get("text"), str)
        for block in value
    ):
        raise ValueError("Only Cohere text content is supported")
    return [{"type": "text", "text": block["text"]} for block in value]


def messages_from_history(history: list[dict]) -> list[dict]:
    """Convert complete ordered history, rejecting repeated IDs or unmatched results.

    Keep this full history when continuing the conversation. Tool plans are
    included as assistant text; media, citations and document content are outside
    this bounded example and must be handled before extending its scope.
    """
    messages, pending, seen = [], set(), set()
    for native in history:
        role = native.get("role")
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("Unsupported Cohere role")
        if any(native.get(key) for key in ("citations", "documents", "images", "audio")):
            raise ValueError("Unsupported Cohere content")
        content = _text_content(native.get("content"))
        plan = native.get("tool_plan")
        if plan is not None:
            if role != "assistant" or not isinstance(plan, str):
                raise ValueError("Unsupported tool plan")
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) and content else content or []
            content = [{"type": "text", "text": plan}, *blocks]
        message = {"role": role, "content": content}
        calls = native.get("tool_calls")
        if calls:
            if role != "assistant" or not isinstance(calls, list):
                raise ValueError("Unexpected tool proposals")
            converted = []
            for call in calls:
                if not isinstance(call, dict):
                    raise ValueError("Invalid native tool proposal")
                identifier = call.get("id")
                function = call.get("function")
                if not isinstance(identifier, str) or not identifier or identifier in seen:
                    raise ValueError("Missing or repeated native tool ID")
                if call.get("type") != "function" or not isinstance(function, dict):
                    raise ValueError("Unsupported native tool")
                name, arguments = function.get("name"), function.get("arguments")
                if not isinstance(name, str) or not name or not isinstance(arguments, str):
                    raise ValueError("Invalid native function call")
                try:
                    parsed = json.loads(arguments, object_pairs_hook=_object, parse_constant=_invalid_constant)
                except json.JSONDecodeError as error:
                    raise ValueError("Malformed tool arguments") from error
                if not isinstance(parsed, dict):
                    raise ValueError("Tool arguments must be an object")
                converted.append({"id": identifier, "function": name, "arguments": parsed, "type": "function"})
                pending.add(identifier)
                seen.add(identifier)
            message["tool_calls"] = converted
        if role == "tool":
            identifier = native.get("tool_call_id")
            if not isinstance(identifier, str) or identifier not in pending:
                raise ValueError("Tool result has no matching pending proposal")
            pending.remove(identifier)
            message["tool_call_id"] = identifier
        messages.append(message)
    return messages


def convert_exchange(request: dict, response: dict) -> Exchange:
    """Convert a complete native Cohere reply and the request history preceding it."""
    if response.get("finish_reason") not in {"COMPLETE", "TOOL_CALL"}:
        raise ValueError("Incomplete Cohere response")
    native = response.get("message")
    if not isinstance(native, dict):
        raise ValueError("Missing native assistant message")
    native = {"role": "assistant", **native}
    history = request.get("messages")
    if not isinstance(history, list) or not history:
        raise ValueError("Full native conversation history is required")
    messages = messages_from_history([*deepcopy(history), native])
    if messages[-1]["role"] != "assistant":
        raise ValueError("Response must contain an assistant message")
    calls = messages[-1].get("tool_calls", [])
    if bool(calls) != (response["finish_reason"] == "TOOL_CALL"):
        raise ValueError("Cohere finish reason does not match its tool proposals")
    return Exchange(
        messages=messages,
        inputs=[
            {"tool_name": call["function"], "tool_input": call["arguments"], "tool_use_id": call["id"]}
            for call in calls
        ],
    )
