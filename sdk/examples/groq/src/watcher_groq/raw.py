"""Inventory deliverable calls and apply Watcher's decisions to original wire exchanges.

Only function calls are released. Transcript conversion is performed by Watcher;
this local inventory prevents an omitted or mismatched judgment releasing a tool.
"""

import json
from copy import deepcopy


class Withheld(PermissionError):
    """The complete native response must not reach a tool executor."""


def decode(value):
    """Reject ambiguous argument JSON before it can reach application dispatch."""

    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = item
        return result

    def invalid(value):
        raise ValueError("Non-finite JSON number")

    return json.loads(value, object_pairs_hook=pairs, parse_constant=invalid)


def inventory(response: dict, api: str) -> dict[tuple, dict]:
    """Bind original native IDs and executable locations to complete function calls.

    Unsupported output types, incomplete executable responses, ambiguous IDs and
    non-object arguments fail before delivery. Buffered text-only truncations are
    submitted unchanged; they cannot authorize a client function call.
    """
    if api == "messages":
        complete = response.get("stop_reason") in {"end_turn", "tool_use", "stop_sequence"}
        if not complete and response.get("stop_reason") not in {"max_tokens", "refusal"}:
            raise ValueError("Unsupported Messages finish reason")
        blocks = response["content"]
        calls = []
        for index, block in enumerate(blocks):
            if block["type"] == "tool_use":
                calls.append((("content", index), block["id"], block["name"], block["input"]))
            elif block["type"] not in {"text", "thinking", "redacted_thinking"}:
                raise ValueError("Unsupported response block")
    elif api == "responses":
        complete = response.get("status") == "completed"
        if not complete and response.get("status") != "incomplete":
            raise ValueError("Unsupported Responses status")
        calls = []
        for index, item in enumerate(response["output"]):
            if item["type"] == "function_call":
                if item.get("status", "completed") != "completed":
                    raise ValueError("Incomplete function call")
                calls.append((("output", index), item["call_id"], item["name"], decode(item["arguments"])))
            elif item["type"] not in {"message", "reasoning"}:
                raise ValueError("Only client function tools are supported")
    elif api == "chat_completions":
        choices = response.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("One complete response choice is required")
        choice = choices[0]
        message = choice["message"]
        complete = choice.get("finish_reason") in {"stop", "tool_calls"}
        if choice.get("index") != 0 or (
            not complete and choice.get("finish_reason") not in {"length", "content_filter"}
        ):
            raise ValueError("Unsupported Chat Completions finish reason")
        if message.get("role") != "assistant" or message.get("function_call") or message.get("audio"):
            raise ValueError("Unsupported response content")
        calls = []
        for index, call in enumerate(message.get("tool_calls") or []):
            if call["type"] != "function":
                raise ValueError("Only function tools are supported")
            calls.append(
                (
                    ("choices", 0, "message", "tool_calls", index),
                    call["id"],
                    call["function"]["name"],
                    decode(call["function"]["arguments"]),
                )
            )
    else:
        raise ValueError("Unsupported provider API")
    if calls and not complete:
        raise ValueError("Incomplete executable response")
    result, identifiers = {}, set()
    for path, identifier, name, arguments in calls:
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError("Missing or duplicate native tool identity")
        if not isinstance(name, str) or not name or not isinstance(arguments, dict):
            raise ValueError("A function name and argument object are required")
        json.dumps(arguments, allow_nan=False)
        identifiers.add(identifier)
        result[path] = {"tool_use_id": identifier, "tool_name": name, "tool_input": deepcopy(arguments)}
    return result


def releasable(value: dict) -> bool:
    """Apply the effective policy, including an explicit grading-failure fallback."""
    decision, mode, source = value.get("decision"), value.get("enforcement_mode"), value.get("decision_source")
    failure = value.get("grading_error")
    if source == "grading_error":
        if (
            not isinstance(failure, dict)
            or failure.get("code")
            not in {"timeout", "at_capacity", "allowance_exhausted", "grader_failed", "no_result"}
            or not isinstance(failure.get("message"), str)
        ):
            return False
    elif failure is not None:
        return False
    if mode == "paused":
        return decision == "deferred" and source == "bypass" and value.get("judged_decision") is None
    if source not in {"threshold", "rule", "triage", "policy_gateway", "grading_error"}:
        return False
    if mode == "observe":
        return decision == "deferred" and value.get("judged_decision") in {"allow", "deny", "escalate"}
    return mode == "enforce" and decision == "allow" and value.get("judged_decision") == "allow"


async def evaluate(
    watcher, *, request, response, url, user_agent, provider, api, session_id, enforcement="server", timeout=None
):
    """Withhold the complete response unless every delivered call has permission.

    Each decision must name a unique native ID from this response; order is immaterial.
    Server policy is inherited. Explicit posture overrides may be admin-locked.
    Escalations remain withheld; this helper has no human approval interface.
    Successful submission schedules ingestion, not proof of durable storage.
    """
    if not session_id.strip() or enforcement not in {"server", "enforce", "observe", "paused"}:
        raise ValueError("A session ID and a supported enforcement setting are required")
    expected = {call["tool_use_id"] for call in inventory(response, api).values()}
    outcomes = await watcher.pre_tool_use_hook(
        request_body=request,
        response_body=response,
        url=url,
        provider=provider,
        user_agent=user_agent,
        external_ids={"other": session_id},
        timeout=timeout,
        settings_overrides=None if enforcement == "server" else {"enforcement": {"mode": enforcement}},
    )
    if not isinstance(outcomes, list):
        raise RuntimeError("Watcher returned an unexpected response")
    released = set()
    for outcome in outcomes:
        serialize = getattr(outcome, "to_dict", None)
        if not callable(serialize):
            raise RuntimeError("Watcher returned an invalid decision")
        value = serialize()
        identifier = value.get("tool_use_id")
        if not isinstance(identifier, str) or identifier not in expected or identifier in released:
            raise RuntimeError("Watcher returned an unknown or repeated native call ID")
        if enforcement != "server" and value.get("enforcement_mode") != enforcement:
            raise RuntimeError("Watcher did not apply the requested enforcement mode")
        if not releasable(value):
            raise Withheld("Watcher withheld the response; do not execute its tools")
        released.add(identifier)
    if released != expected:
        raise RuntimeError("Watcher omitted a delivered tool call")
    return outcomes


def validate_request(request: dict, api: str) -> None:
    """Limit generation to buffered, complete history and client-side functions."""
    if request.get("stream"):
        raise ValueError("This example requires a buffered response")
    if any(
        request.get(key) for key in ("previous_response_id", "conversation", "background", "functions", "function_call")
    ):
        raise ValueError("Complete stateless history and function tools are required")
    if request.get("n", 1) != 1:
        raise ValueError("Only one response choice is supported")
    if api != "messages" and any(tool.get("type") != "function" for tool in request.get("tools", [])):
        raise ValueError("Only client function tools are supported")
