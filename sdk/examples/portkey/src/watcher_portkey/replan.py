"""Build truthful tool-denial continuations and compose the reply the client receives.

The bridge owns attempt limits, deadlines, grading and delivery. These helpers
retain provider history, describe each refused call truthfully and combine an
approved alternative with the notices into one Chat Completions response.

The texts follow the wording that kept agents working in Watcher's denial
experiments. A denial's result says that working around the block is fine,
because Watcher checks every call; inviting a text-only explanation instead
ends the agent's turn, since harnesses only call the model again after tool
results. An escalation's result asks the model to stop and put the decision to
the user with labelled options. Client-visible notices say that Watcher, not
the model, wrote them: the next request carries them in the model's own turn.

Nothing from a proposal reaches the client through this gateway until every
call in it is allowed, so a refused proposal never has released siblings and no
"already sent to the client" receipt is needed: every unrefused sibling of a
refused call is reported as not run.
"""

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

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

# The notice echoes each refused call so the model can see what was withheld,
# but the client's next request carries it back through the bridge, which
# accepts at most MAX_BODY, so long arguments and reasons are shortened and
# the whole notice is bounded.
_ECHO_LIMIT = 4096
_NAME_LIMIT = 256
_NOTICE_LIMIT = 64 * 1024
_SUMMARY_ROOM = 256
# Message fields whose values can be combined across two completions. Any other
# populated field (audio, unknown provider extensions) fails closed rather than
# being silently dropped or attributed to the wrong attempt.
_MESSAGE_FIELDS = {"role", "content", "tool_calls", "reasoning_content", "refusal"}
_EMPTY_DEFAULTS: dict[str, list[Any]] = {"annotations": [[]]}


class UncomposableResponse(ValueError):
    """A completion has fields this bridge cannot merge into the delivered reply."""


@dataclass(frozen=True)
class ToolCall:
    """A client-executable function call with its parsed JSON-object arguments."""

    tool_use_id: str
    tool_name: str
    tool_input: dict[str, Any]


@dataclass(frozen=True)
class ToolDenial(ToolCall):
    """A refused call and Watcher's public explanation.

    ``user_can_approve`` says whether the user's answer can lead to approval of
    an escalation. Only Watcher's graders read the conversation; a rule, a
    threshold or the grading-failure policy decides again without it, so
    offering "allow" there would escalate the same call in a loop.
    """

    reason: str
    is_escalation: bool
    user_can_approve: bool = False


def tool_calls(response: dict[str, Any]) -> list[ToolCall]:
    """List the function calls of a single-choice completion, in provider order.

    ``response`` must already have passed the bridge's ``client_calls`` check,
    which rejects duplicate IDs, duplicate JSON keys, non-object arguments and
    non-finite numbers; this helper only reads the validated shape.
    """
    message = response["choices"][0]["message"]
    return [
        ToolCall(
            tool_use_id=call["id"],
            tool_name=call["function"]["name"],
            tool_input=json.loads(call["function"]["arguments"]),
        )
        for call in message.get("tool_calls") or []
    ]


def operation_key(call: ToolCall) -> str:
    """Identify an operation independently of its call ID, keeping JSON scalar types distinct."""
    return json.dumps([call.tool_name, call.tool_input], ensure_ascii=False, sort_keys=True, allow_nan=False)


def _call_text(call: ToolCall) -> str:
    """Name a call with its arguments, as a reader would recognize it in the transcript, shortening long ones."""
    arguments = json.dumps(call.tool_input, ensure_ascii=False, sort_keys=True, allow_nan=False)
    if len(arguments) > _ECHO_LIMIT:
        arguments = arguments[:_ECHO_LIMIT] + " … (arguments shortened)"
    return f"`{call.tool_name[:_NAME_LIMIT]} {arguments}`"


def _reason(denial: ToolDenial) -> str:
    """Watcher's public explanation as one sentence, shortened, whether or not it ends with punctuation."""
    reason = denial.reason.strip()[:_ECHO_LIMIT]
    return reason if reason.endswith((".", "!", "?")) else reason + "."


def denial_notice(denials: list[ToolDenial], *, cancelled: list[ToolCall] | None = None) -> str:
    """Describe withheld calls to the user and to the model's later turns, one line per call.

    Each line names the call with its exact arguments and Watcher's public
    reason, and says Watcher added it, because the client's next request
    carries it inside the model's own turn. A model that sees unexplained text
    there tends to call it injected or its own mistake and disbelieve the
    denial. Escalations are marked ``WATCHER ESCALATION``, denials ``WATCHER
    NOTICE``. ``cancelled`` contains unevaluated siblings withheld because of
    another call's refusal. Long arguments and reasons are shortened, and once
    the notice reaches its size limit the remaining refused and withheld calls
    are only counted. This helper emits no executable tool calls.
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
    entries = lines + [f"WATCHER NOTICE {_ADDED_BY_WATCHER}: {_call_text(call)} {_SIBLING}" for call in cancelled or []]
    shown: list[str] = []
    # Encoded bytes and separators count, and room is kept for the count line.
    size = _SUMMARY_ROOM
    for line in entries:
        size += len(line.encode()) + 2
        if shown and size > _NOTICE_LIMIT:
            refused = max(len(denials) - len(shown), 0)
            shown.append(
                f"WATCHER NOTICE {_ADDED_BY_WATCHER}: {refused} more refused calls and "
                f"{len(entries) - len(shown) - refused} more withheld calls did not run."
            )
            break
        shown.append(line)
    return "\n\n".join(shown)


def stop_notice(denials: list[ToolDenial]) -> str:
    """End a response whose final, text-only generation proposed tool calls anyway.

    ``denials`` are the refusals that triggered the final generation. That
    generation was asked to stop and ask the user, so its calls are withheld
    unevaluated, and this text puts the question to the user instead. It
    offers approval only when every escalation can be approved in the
    conversation; one "allow" answer cannot clear a call held by policy.
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


ALTERNATIVE_FAILED = (
    f"WATCHER NOTICE {_ADDED_BY_WATCHER}: Watcher blocked the assistant's tool calls, and the gateway could not "
    "get another approach from the assistant, so it delivered no further tool calls. None of the blocked calls "
    "ran. How would you like to proceed?"
)
"""Ends a response whose alternative failed, so the agent's turn ends with a question rather than a notice."""


def _tool_result(call_id: str, denials: dict[str, ToolDenial], *, stop: bool, escalated: bool) -> str:
    """Explain the call's actual delivery state without inventing a client execution result.

    A refused call's result tells the model what to do next: keep working by
    another approach, or, on the final generation, stop and ask the user. On
    that final generation an escalation alone carries the ask, so a denied
    sibling's result adds no instruction that could contradict it.
    """
    denial = denials.get(call_id)
    if denial is None:
        return f"This call {_SIBLING}"
    if denial.is_escalation and denial.user_can_approve:
        return (
            f"WATCHER ESCALATION: this call needs the user's decision before it can run. "
            f"Reason: {_reason(denial)} The call did not run. {_ASK_APPROVAL}"
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


def build_continuation(
    request: dict[str, Any], response: dict[str, Any], denials: list[ToolDenial], *, stop: bool
) -> dict[str, Any]:
    """Append the refused proposal and one tool result per call, without mutating either input.

    ``response`` must have passed the bridge's ``client_calls`` check and
    contain every call named by ``denials`` with the same name and arguments;
    anything else raises ``ValueError``. Unrefused calls in the same response
    are reported as not run. History (including reasoning fields), tools,
    ``tool_choice``, ``parallel_tool_calls`` and every other option are copied
    unchanged, except that the generation is buffered (``stream_options``
    removed) and, with ``stop``, ``tool_choice`` becomes ``"none"`` when the
    request offers tools. Requests without tools keep their tool choice as it
    is: OpenAI rejects a tool choice without tools.

    Without ``stop``, a denied call's result asks for another approach. With
    ``stop`` (the final generation, after an escalation or the third refused
    proposal), results ask the model to stop and put the decision or the
    blocked approaches to the user.
    """
    calls = {call.tool_use_id: call for call in tool_calls(response)}
    by_id = {denial.tool_use_id: denial for denial in denials}
    if not by_id or len(by_id) != len(denials) or not by_id.keys() <= calls.keys():
        raise ValueError("Invalid continuation denial identities")
    for call_id, denial in by_id.items():
        if operation_key(denial) != operation_key(calls[call_id]):
            raise ValueError("Invalid continuation denial tool details")
    escalated = any(denial.is_escalation for denial in denials)
    result = deepcopy(request)
    result.pop("stream_options", None)
    if "stream" in result:
        result["stream"] = False
    if stop and result.get("tools"):
        result["tool_choice"] = "none"
    result["messages"].append(deepcopy(response["choices"][0]["message"]))
    for call_id in calls:
        result["messages"].append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": _tool_result(call_id, by_id, stop=stop, escalated=escalated),
            }
        )
    return result


def check_composable(response: dict[str, Any]) -> None:
    """Raise ``UncomposableResponse`` unless the completion's message can be merged field by field.

    Only scalar content, reasoning and refusal text and function calls are
    merged; any other populated message field fails closed rather than being
    lost or attributed to the wrong attempt.
    """
    message = response["choices"][0]["message"]
    for key, value in message.items():
        if key not in _MESSAGE_FIELDS and value is not None and value not in _EMPTY_DEFAULTS.get(key, []):
            raise UncomposableResponse("Unsupported Chat message field in a recovered response")
    for key in ("content", "reasoning_content", "refusal"):
        if message.get(key) is not None and not isinstance(message[key], str):
            raise UncomposableResponse("Recovery requires scalar message text")


def compose(
    original: dict[str, Any], replacement: dict[str, Any] | None, notices: str, *, closing: str | None = None
) -> dict[str, Any]:
    """Return the one completion the client receives after a refusal.

    The message text is the original proposal's text, ``notices``, the
    replacement's text and ``closing``, joined by blank lines. Tool calls come
    only from ``replacement``, which must be an approved alternative or a final
    generation with its calls already removed; the original's calls are never
    delivered. The original's ``id``, ``created``, ``model`` and ``usage``
    remain. Token log probabilities are dropped: they describe the refused
    answer, not the merged text. Both inputs must pass ``check_composable``;
    neither is mutated.
    """
    for response in [original, *([replacement] if replacement is not None else [])]:
        check_composable(response)
    result = deepcopy(original)
    choice = result["choices"][0]
    message = choice["message"]
    other = replacement["choices"][0]["message"] if replacement is not None else {}
    parts = [message.get("content"), notices, other.get("content"), closing]
    message["content"] = "\n\n".join(part for part in parts if part)
    for key in ("reasoning_content", "refusal"):
        if message.get(key) or other.get(key):
            message[key] = (message.get(key) or "") + (other.get(key) or "")
    message.pop("tool_calls", None)
    if other.get("tool_calls"):
        message["tool_calls"] = deepcopy(other["tool_calls"])
    reason = replacement["choices"][0]["finish_reason"] if replacement is not None else "stop"
    if reason in {"stop", "tool_calls"}:
        reason = "tool_calls" if message.get("tool_calls") else "stop"
    choice["finish_reason"] = reason
    choice.pop("logprobs", None)
    return result
