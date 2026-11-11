"""Build truthful tool-denial continuations and generate through the configured Router.

The callback owns attempt limits, deadlines, grading and delivery. These helpers
retain provider history and distinguish calls withheld by Watcher from calls
already sent to the client. A released call has an unknown execution result;
inventing its success or cancellation would give the next generation false
context. Every generated alternative must pass the callback's tool gates.

The texts follow the wording that kept agents working in Watcher's denial
experiments. A denial's result says that working around the block is fine,
because Watcher checks every call; inviting a text-only explanation instead
ends the agent's turn, since harnesses only call the model again after tool
results. An escalation's result asks the model to stop and put the decision to
the user with labelled options. Client-visible notices say that Watcher, not
the model, wrote them: the next request carries them in the model's own turn.
"""

import json
from collections.abc import AsyncIterator
from copy import deepcopy
from typing import Any, Literal, overload

from litellm.litellm_core_utils.core_helpers import independent_snapshot
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

from watcher_litellm.copilot import current_request
from watcher_litellm.incremental import is_client_item
from watcher_litellm.streams import API, response_dict

_JSON_OBJECT = TypeAdapter(dict[str, JsonValue])
_ADDED_BY_WATCHER = "(added by Watcher, not written by the assistant)"
_CONTINUE = (
    "Continue the user's task another way; Watcher checks every call, "
    "so you do not need permission to try a different approach."
)
_STOP_AFTER_CAP = "Several different approaches have now been blocked, so stop: tell the user what was blocked and ask how to proceed."
_ASK_APPROVAL = (
    "The user can approve it: stop and ask the user whether to allow it, with labelled options, "
    "for example: A. allow this call, B. skip it, C. do something else."
)
_ASK_FIXED = (
    "Stop, tell the user, and ask how to proceed with labelled options, for example: "
    "A. skip it, B. do something else, C. ask an administrator to change the policy."
)
_HELD = "Watcher's policy holds {call} for a person's review, and it cannot be approved in this conversation."
_SIBLING = "did not run because Watcher refused another call in the same response."
_RELEASED_RESULT = (
    "Watcher approved this tool call and sent it to the client. "
    "Its execution result is not yet available. Do not repeat it."
)
# Router attempts need fresh logging state while retaining request routing,
# key/team ownership, provider credentials and parent tracing context.
_ATTEMPT_STATE = frozenset(
    {
        "litellm_logging_obj",
        "litellm_call_id",
        "deployment",
        "_litellm_client_requested_model",
        "_litellm_strip_stream_usage",
        "stream_options",
    }
)


class ToolCall(BaseModel):
    """A client-executable call with parsed function arguments or unchanged custom input."""

    model_config = ConfigDict(strict=True, allow_inf_nan=False)

    tool_use_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    tool_input: JsonValue


class ToolDenial(ToolCall):
    """A matched call and Watcher's public explanation, excluding internal grader prompts."""

    reason: str = Field(min_length=1)
    is_escalation: bool
    # Whether the user's answer can lead to approval of an escalation. Only
    # Watcher's graders read the conversation; a rule, a threshold or the
    # grading-failure policy decides again without it, so offering "allow"
    # there would escalate the same call in a loop.
    user_can_approve: bool = False


class _LocalShellAction(BaseModel):
    """Normalize native shell arguments like Watcher's CodexLocalShellAction.

    This standalone example cannot import product internals. Explicit nullable
    defaults keep operation identities stable when a provider omits a field on
    one attempt and emits null on another; unknown action fields remain intact.
    """

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    command: list[str] | None = None
    timeout_ms: int | None = None
    working_directory: str | None = None
    env: dict[str, str] | None = None
    user: str | None = None


def redundant_namespace(item: dict[str, Any]) -> bool:
    """Whether a Responses item's namespace only repeats the prefix of its tool name.

    Copilot names each MCP tool with its server as a prefix and also sends the
    server as the namespace, so the namespace adds nothing to the name.
    """
    namespace, name = item.get("namespace"), item.get("name")
    return isinstance(namespace, str) and isinstance(name, str) and name.startswith(namespace + "-")


def _responses_tool_name(item: dict[str, Any]) -> str:
    """Fold namespaces using the active native request's tool naming convention.

    Native Copilot server tools already start with ``<namespace>-``. Other
    calls use Codex's namespace spelling. The provider item is never changed.
    """
    name = item["name"]
    namespace = item.get("namespace")
    if not isinstance(name, str) or not name or (namespace is not None and not isinstance(namespace, str)):
        raise ValueError("Invalid Responses tool name or namespace")
    # Keep native Copilot names in sync with the Watcher server's Responses parser.
    if current_request.get() is not None and redundant_namespace(item):
        return name
    if not namespace or namespace == "functions":
        return name
    if namespace.startswith("mcp__"):
        return f"{namespace.rstrip('_')}__{name.lstrip('_')}"
    if namespace == "multi_agent_v1" and name == "spawn_agent":
        return name
    return namespace + name


def _arguments(raw: str) -> dict[str, JsonValue]:
    """Require complete JSON-object function arguments before constructing a continuation."""
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Function arguments must be a JSON object")
    return _JSON_OBJECT.validate_python(parsed)


def client_tool_details(api: API, response: dict[str, Any]) -> list[ToolCall]:
    """Inventory complete executable calls in provider order, rejecting ambiguous identities.

    Supports Messages tool-use blocks, Chat function/custom calls and its legacy
    function-call field, and Responses function/custom/local-shell/client-search
    items. Responses tool names follow Watcher's namespace folding, so equal
    bare names in different groups remain distinct operations. Provider-executed
    Responses items remain context. Unknown client call types, multiple Chat
    choices, malformed arguments and duplicate IDs raise ``ValueError``.
    Legacy Chat calls use the callback inventory's synthetic ID ``function_call``.
    """
    calls: list[ToolCall] = []
    try:
        if api == "messages":
            for block in response["content"]:
                if block["type"] == "tool_use":
                    if not isinstance(block["input"], dict):
                        raise ValueError("Messages tool input must be an object")
                    calls.append(ToolCall(tool_use_id=block["id"], tool_name=block["name"], tool_input=block["input"]))
        elif api == "chat_completions":
            if len(response["choices"]) != 1:
                raise ValueError("Replanning requires one Chat choice")
            message = response["choices"][0]["message"]
            if message.get("function_call") and message.get("tool_calls"):
                raise ValueError("Mixed legacy and modern Chat calls")
            for call in message.get("tool_calls") or []:
                if call["type"] == "function":
                    name, arguments = call["function"]["name"], _arguments(call["function"]["arguments"])
                elif call["type"] == "custom" and isinstance(call["custom"]["input"], str):
                    name, arguments = call["custom"]["name"], call["custom"]["input"]
                else:
                    raise ValueError("Unsupported Chat client call")
                calls.append(ToolCall(tool_use_id=call["id"], tool_name=name, tool_input=arguments))
            if legacy := message.get("function_call"):
                calls.append(
                    ToolCall(
                        tool_use_id="function_call",
                        tool_name=legacy["name"],
                        tool_input=_arguments(legacy["arguments"]),
                    )
                )
        else:
            for item in response["output"]:
                if not is_client_item(item):
                    continue
                kind = item["type"]
                if kind == "function_call":
                    name = _responses_tool_name(item)
                    arguments = _arguments(item["arguments"])
                elif kind == "custom_tool_call" and isinstance(item["input"], str):
                    name = _responses_tool_name(item)
                    arguments = item["input"]
                elif kind == "local_shell_call":
                    name = "local_shell"
                    arguments = _LocalShellAction.model_validate(item["action"]).model_dump(mode="json")
                elif kind == "tool_search_call":
                    if item.get("execution") != "client":
                        raise ValueError("Unsupported Responses tool search execution")
                    name = "tool_search"
                    raw = item["arguments"]
                    arguments = (
                        _JSON_OBJECT.validate_python(raw, strict=True) if isinstance(raw, dict) else _arguments(raw)
                    )
                else:
                    raise ValueError("Unsupported Responses client call")
                calls.append(ToolCall(tool_use_id=item["call_id"], tool_name=name, tool_input=arguments))
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Malformed client tool response") from exc
    if len({call.tool_use_id for call in calls}) != len(calls):
        raise ValueError("Duplicate client tool call ID")
    # JSON comparisons must distinguish true from 1, which Python equality does
    # not; rejecting non-finite values also prevents invalid evidence in notices.
    for call in calls:
        json.dumps(call.tool_input, allow_nan=False)
    return calls


def _call_text(call: ToolCall) -> str:
    """Name a call with its exact arguments, as a reader would recognize it in the transcript."""
    arguments = (
        call.tool_input
        if isinstance(call.tool_input, str)
        else json.dumps(call.tool_input, ensure_ascii=False, sort_keys=True, allow_nan=False)
    )
    return f"`{call.tool_name} {arguments}`"


def _reason(denial: ToolDenial) -> str:
    """Watcher's public explanation as one sentence, whether or not it ends with punctuation."""
    reason = denial.reason.strip()
    return reason if reason.endswith((".", "!", "?")) else reason + "."


def denial_notice(denials: list[ToolDenial], *, cancelled: list[ToolCall] | None = None) -> str:
    """Describe withheld calls to the user and to the model's later turns, one line per call.

    Each line names the call with its exact arguments and Watcher's public
    reason, and says Watcher added it, because the client's next request
    carries it inside the model's own turn. A model that sees unexplained text
    there tends to call it injected or its own mistake and disbelieve the
    denial. Escalations are marked ``WATCHER ESCALATION``, denials ``WATCHER
    NOTICE``. ``cancelled`` contains unevaluated siblings withheld because of
    another call's refusal; never include an already released call in that
    list. This helper emits no executable provider tool blocks.
    """
    lines = [
        f"WATCHER NOTICE {_ADDED_BY_WATCHER}: Watcher blocked {_call_text(denial)}. "
        f"Reason: {_reason(denial)} The call did not run."
        if not denial.is_escalation
        else f"WATCHER ESCALATION {_ADDED_BY_WATCHER}: {_call_text(denial)} needs the user's decision before it can run. "
        f"Reason: {_reason(denial)} The call did not run."
        if denial.user_can_approve
        else f"WATCHER ESCALATION {_ADDED_BY_WATCHER}: {_HELD.format(call=_call_text(denial))} "
        f"Reason: {_reason(denial)} The call did not run."
        for denial in denials
    ]
    lines += [f"WATCHER NOTICE {_ADDED_BY_WATCHER}: {_call_text(call)} {_SIBLING}" for call in cancelled or []]
    return "\n\n".join(lines)


def stop_notice(denials: list[ToolDenial]) -> str:
    """The fixed question to the user when the final generation's reply cannot stand alone.

    ``denials`` are the refusals that triggered the final generation, which
    was asked to stop and ask the user. This text follows its reply when the
    reply proposed tool calls anyway (withheld unevaluated), had no text or
    was cut off, and replaces it when the generation failed. It offers
    approval only when every escalation can be approved in the conversation;
    one "allow" answer cannot clear a call held by policy.
    """
    escalations = [denial for denial in denials if denial.is_escalation]
    if escalations and all(denial.user_can_approve for denial in escalations):
        return (
            f"WATCHER ESCALATION {_ADDED_BY_WATCHER}: Watcher withheld further tool calls so that the user can decide. "
            "Reply A to allow the escalated call (Watcher evaluates it again when the assistant proposes it), "
            "B to skip it, or C to do something else."
        )
    if escalations:
        return (
            f"WATCHER ESCALATION {_ADDED_BY_WATCHER}: Watcher withheld further tool calls. Watcher's policy holds the "
            "escalated call for a person's review, and it cannot be approved in this conversation. Reply A to skip "
            "it, B to do something else, or C to ask an administrator to change the policy."
        )
    return (
        f"WATCHER NOTICE {_ADDED_BY_WATCHER}: Watcher blocked three proposals in a row and withheld further tool "
        "calls. None of the blocked calls ran. How would you like to proceed?"
    )


def _tool_result(
    call_id: str,
    denials: dict[str, ToolDenial],
    released_ids: set[str],
    *,
    stop: bool,
    escalated: bool,
    approvable: bool,
) -> str:
    """Explain the call's actual delivery state without inventing a client execution result.

    A refused call's result tells the model what to do next: keep working by
    another approach, or, on the final generation, stop and ask the user. On
    that final generation an escalation alone carries the ask, so a denied
    sibling's result adds no instruction that could contradict it. Approval is
    offered only when ``approvable``, meaning every escalation in the proposal
    can be approved in the conversation, as in ``stop_notice``.
    """
    if call_id in released_ids:
        return _RELEASED_RESULT
    denial = denials.get(call_id)
    if denial is None:
        return f"This call {_SIBLING}"
    if denial.is_escalation and denial.user_can_approve:
        return (
            f"WATCHER ESCALATION: this call needs the user's decision before it can run. "
            f"Reason: {_reason(denial)} The call did not run. {_ASK_APPROVAL if approvable else _ASK_FIXED}"
        )
    if denial.is_escalation:
        return (
            f"WATCHER ESCALATION: {_HELD.format(call='this call')} "
            f"Reason: {_reason(denial)} The call did not run. {_ASK_FIXED}"
        )
    result = f"WATCHER NOTICE: Watcher blocked this call. Reason: {_reason(denial)} The call did not run."
    if not stop:
        return f"{result} {_CONTINUE}"
    return result if escalated else f"{result} {_STOP_AFTER_CAP}"


def _forbid_tool_calls(api: API, request: dict[str, Any]) -> None:
    """Set the API's no-call choice, in place, wherever the request offers tools.

    Requests without tools are left alone: there is nothing to call, and
    OpenAI rejects a tool choice without tools.
    """
    if request.get("tools"):
        request["tool_choice"] = {"type": "none"} if api == "messages" else "none"
    if api == "chat_completions" and request.get("functions"):
        request["function_call"] = "none"


def build_replan_request(
    api: API,
    request: dict[str, Any],
    response: dict[str, Any],
    denials: list[ToolDenial],
    *,
    released_ids: set[str],
    stop: bool = False,
) -> dict[str, Any]:
    """Append the original proposal and truthful results without mutating either input.

    ``response`` must include every call named by ``denials`` or ``released_ids``.
    Denials must match the actual call's name and arguments; duplicate, missing,
    mismatched or already released denials raise ``ValueError``. Released calls
    receive an explicit execution-unknown receipt, denied calls receive Watcher's
    explanation, and other calls receive cancellation results. None is executed
    by this helper. On a subsequent replacement, pass that replacement response
    and its already extended request; previously released receipts remain history.

    Without ``stop``, a denied call's result asks for another approach. With
    ``stop`` (the callback's final generation, after an escalation or the last
    allowed proposal), results ask the model to stop and put the decision or
    the blocked approaches to the user instead, and the request's tool choice
    becomes the API's no-call choice so the model answers in text.

    Existing history, system instructions, tools, tool-selection constraints
    (except with ``stop``), cache controls, signed thinking,
    encrypted reasoning and metadata are copied unchanged. Recovery must not enable tools excluded for this turn. Responses string
    input becomes an equivalent user message. Provider-run output stays context.
    Native shell receipts use the API's ``id`` result field. A client tool search has
    no textual result field: its incomplete result provides no tool definitions,
    and a separate user message explains that this is a gateway receipt, not a
    search result. Released searches remain explicitly execution-pending.
    """
    # 1. Match every synthetic result to an actual proposal before extending its
    # history; a mismatched ID must never describe a different operation as denied.
    calls = client_tool_details(api, response)
    pending = {call.tool_use_id: call for call in calls}
    by_id = {denial.tool_use_id: denial for denial in denials}
    escalated = any(denial.is_escalation for denial in denials)
    approvable = all(denial.user_can_approve for denial in denials if denial.is_escalation)

    def result_text(call_id: str) -> str:
        return _tool_result(call_id, by_id, released_ids, stop=stop, escalated=escalated, approvable=approvable)

    if not by_id or len(by_id) != len(denials) or not by_id.keys() <= pending.keys():
        raise ValueError("Invalid replan denial identities")
    if not released_ids <= pending.keys() or released_ids & by_id.keys():
        raise ValueError("Invalid replan released identities")
    for call_id, denial in by_id.items():
        proposed = pending[call_id]
        if denial.tool_name != proposed.tool_name or json.dumps(
            denial.tool_input, sort_keys=True, allow_nan=False
        ) != json.dumps(proposed.tool_input, sort_keys=True, allow_nan=False):
            raise ValueError("Invalid replan denial tool details")

    # 2. Preserve request controls: relaxing a forced choice could enable an
    # excluded provider-hosted tool, which executes before this callback sees it.
    # The final generation must answer in text and must not run a provider-hosted
    # tool either, which also executes before this callback sees it, so it gets
    # the no-call choice. That narrows every choice, at the cost of the prompt
    # cache for that one generation.
    result = deepcopy(request)
    if stop:
        _forbid_tool_calls(api, result)

    # 3. Represent the same delivery facts in each API's native tool-result shape.
    if api == "responses":
        previous = result["input"]
        history: list[dict[str, Any]] = (
            [{"role": "user", "content": previous}] if isinstance(previous, str) else previous
        )
        output = deepcopy(response["output"])
        history.extend(output)
        search_receipts: list[str] = []
        for item in output:
            if item["type"] in {"function_call", "custom_tool_call"}:
                history.append(
                    {
                        "type": item["type"] + "_output",
                        "call_id": item["call_id"],
                        "output": result_text(item["call_id"]),
                    }
                )
            elif item["type"] == "local_shell_call":
                history.append(
                    {
                        "type": "local_shell_call_output",
                        "id": item["call_id"],
                        "status": "incomplete",
                        "output": result_text(item["call_id"]),
                    }
                )
            elif item["type"] == "tool_search_call" and is_client_item(item):
                history.append(
                    {
                        "type": "tool_search_output",
                        "call_id": item["call_id"],
                        "execution": "client",
                        "status": "incomplete",
                        "tools": [],
                    }
                )
                search_receipts.append(
                    f"Gateway delivery receipt for tool call {item['call_id']}: "
                    "the incomplete tool_search_output supplies no tool definitions. "
                    "It is not a completed search result. " + result_text(item["call_id"])
                )
        if search_receipts:
            history.append({"role": "user", "content": "\n\n".join(search_receipts)})
        result["input"] = history
    elif api == "messages":
        result["messages"].append({"role": "assistant", "content": deepcopy(response["content"])})
        result["messages"].append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": call.tool_use_id,
                        "content": result_text(call.tool_use_id),
                        **({"is_error": True} if call.tool_use_id not in released_ids else {}),
                    }
                    for call in calls
                ],
            }
        )
    else:
        message = response["choices"][0]["message"]
        result["messages"].append(deepcopy(message))
        for call in calls:
            location = (
                {"role": "function", "name": call.tool_name}
                if message.get("function_call")
                else {"role": "tool", "tool_call_id": call.tool_use_id}
            )
            result["messages"].append({**location, "content": result_text(call.tool_use_id)})
    return result


@overload
async def complete_replan(
    api: API, request: dict[str, Any], request_data: dict[str, Any], *, stream: Literal[False] = False
) -> dict[str, JsonValue]: ...


@overload
async def complete_replan(
    api: API, request: dict[str, Any], request_data: dict[str, Any], *, stream: Literal[True]
) -> AsyncIterator[Any]: ...


@overload
async def complete_replan(
    api: API, request: dict[str, Any], request_data: dict[str, Any], *, stream: bool
) -> dict[str, JsonValue] | AsyncIterator[Any]: ...


async def complete_replan(
    api: API, request: dict[str, Any], request_data: dict[str, Any], *, stream: bool = False
) -> dict[str, JsonValue] | AsyncIterator[Any]:
    """Generate one alternative through the current LiteLLM Router, without proxy recursion.

    Retains effective deployment routing, credentials, key/team metadata and
    parent tracing while replacing attempt-local logging state. With ``stream``
    true, returns the Router's iterator for the callback to validate and gate:
    Messages bytes, Chat chunks or Responses events. Otherwise returns a detached
    JSON response. The caller owns closing a returned stream, deadlines, further
    attempts and evaluating every replacement call before release. Provider and
    missing-Router errors propagate; this helper adds no retry policy.
    """
    # Proxy initialization loads callbacks before installing its Router; a local
    # import breaks the proxy_server -> callback -> replan -> proxy_server cycle.
    from litellm.proxy import proxy_server

    router = proxy_server.llm_router
    if router is None:
        raise ValueError("A configured LiteLLM Router is required for replanning")
    kwargs = independent_snapshot(
        {
            key: value
            for key, value in request_data.items()
            if key not in _ATTEMPT_STATE and key not in {"metadata", "litellm_metadata", "proxy_server_request"}
        }
    )
    # Copy metadata entries independently so one opaque span or auth handle does
    # not make the Router share and mutate unrelated request metadata containers.
    for key in ("metadata", "litellm_metadata"):
        if key in request_data:
            value = request_data[key]
            kwargs[key] = independent_snapshot(value) if isinstance(value, dict) else value
    routing_metadata = kwargs.get("metadata")
    payload = deepcopy(request)
    payload["stream"] = stream
    if not stream:
        payload.pop("stream_options", None)
    kwargs.update(payload)
    if api == "chat_completions" and isinstance(routing_metadata, dict):
        kwargs["metadata"] = routing_metadata
    if "model" in request_data:
        kwargs["model"] = request_data["model"]
    if "proxy_server_request" in request_data:
        kwargs["proxy_server_request"] = {
            **independent_snapshot(
                {key: value for key, value in request_data["proxy_server_request"].items() if key != "body"}
            ),
            "body": deepcopy(payload),
        }
    if api == "messages":
        response = await router.aanthropic_messages(**kwargs)
    elif api == "responses":
        response = await router.aresponses(**kwargs)
    else:
        response = await router.acompletion(**kwargs)
    if stream:
        if not isinstance(response, AsyncIterator):
            raise ValueError("Router did not return a streaming alternative")
        return response
    return _JSON_OBJECT.validate_python(
        response_dict(response)
        if api == "responses"
        else (response.model_dump(mode="json", by_alias=True) if isinstance(response, BaseModel) else response)
    )
