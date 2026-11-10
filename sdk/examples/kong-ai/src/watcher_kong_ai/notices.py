"""Watcher's notices for refused tool calls, and the requests and responses built around them.

When Watcher refuses a proposal, the bridge does not end the client's turn with
an error: harnesses such as Claude Code and Codex stop working on an error or a
text-only reply. It shows the model its refused calls as tool results, asks
for another approach and delivers an approved alternative together with a
notice that says Watcher, not the model, wrote it.

The texts follow the wording that kept agents working in Watcher's denial
experiments. A denial's result says that working around the block is fine,
because Watcher checks every call. An escalation's result asks the model to
stop and put the decision to the user with labelled options, and offers
"allow" only when a grader that reads the conversation escalated the call.

Nothing from a buffered proposal reaches the client until every call in it is
allowed, so a refused proposal never has calls already released to the client.
Every unrefused call in it is therefore a sibling that did not run, and no
result here describes a released call.

``SYSTEM_NOTICE`` is added to every request so the model believes the notices
it later finds in its own earlier replies.
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

SYSTEM_NOTICE = (
    "Watcher, your organisation's tool-call monitor, checks every tool call you make before it runs. "
    "When it blocks a call, the gateway removes that call from your reply, gives you Watcher's reason as the "
    "call's result and asks you to continue. So your earlier replies can contain a WATCHER NOTICE that you did "
    "not write: Watcher did, and the blocked call did not run. These notices are genuine. A block applies to that "
    "call only. Keep working on the user's task by another approach, including reaching the same result by other "
    "means: Watcher reviews every call and will block anything that is not allowed, so you do not need to stop "
    "and ask first. Do not repeat the identical blocked call. If several different approaches have been blocked, "
    "stop, tell the user what was blocked and ask how to proceed. A WATCHER ESCALATION is different from a "
    "WATCHER NOTICE: the call needs the user's decision before it may run. Do not try another approach and do "
    "not retry it unless the user allows it. End your turn by asking the user what to do, as a short question "
    "with labelled options, for example: A. allow this call, B. skip it, C. do something else. Offer to allow "
    "the call only when the escalation says the user can approve it."
)

# Message fields an alternative may carry. Any other populated field could not
# be merged into the delivered message without losing or misplacing it.
_ALTERNATIVE_FIELDS = {"role", "content", "tool_calls", "refusal", "reasoning_content"}
# Fields providers routinely send empty, which carry nothing to merge.
_EMPTY_DEFAULTS: dict[str, list] = {"annotations": [[]]}


@dataclass(frozen=True)
class ToolCall:
    """A client function call with its native ID, name and parsed JSON-object arguments."""

    tool_use_id: str
    tool_name: str
    tool_input: Any


@dataclass(frozen=True)
class Denial(ToolCall):
    """A refused call with Watcher's public reason; grader prompts and scores are never included.

    ``user_can_approve`` is true only for an escalation from a grader that
    reads the conversation (``policy_gateway`` or ``triage``). A rule, a
    threshold or the grading-failure policy decides again without reading
    the user's answer, so offering "allow" there would escalate the same call
    in a loop.
    """

    reason: str
    is_escalation: bool
    user_can_approve: bool = False


class MergeError(ValueError):
    """An alternative's message carries content that cannot be merged into the delivered reply."""


def _contains_notice(value: Any) -> bool:
    """Whether any string inside ``value`` already includes the system notice."""
    if isinstance(value, str):
        return SYSTEM_NOTICE in value
    if isinstance(value, dict):
        return any(_contains_notice(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_notice(item) for item in value)
    return False


def with_system_notice(request: dict) -> dict | None:
    """A copy of a Chat request with ``SYSTEM_NOTICE`` added, or None to leave it unchanged.

    The notice becomes a ``system`` message after the leading run of system
    and developer messages, never before them, so the caller's instruction
    order and cached prefix are kept. The text is identical on every request,
    including those with no denial yet, so the prefix stays cacheable. A
    request whose leading messages already carry the text, or whose messages
    field is not a list, is left unchanged: the notice is advice, and the
    provider reports a malformed request better than the bridge can.
    """
    messages = request.get("messages")
    if not isinstance(messages, list):
        return None
    position = 0
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {"system", "developer"}:
            break
        position += 1
    if _contains_notice(messages[:position]):
        return None
    notice = {"role": "system", "content": SYSTEM_NOTICE}
    return {**request, "messages": [*messages[:position], notice, *messages[position:]]}


def _call_text(call: ToolCall) -> str:
    """Name a call with its exact arguments, as a reader would recognize it in the transcript."""
    arguments = json.dumps(call.tool_input, ensure_ascii=False, sort_keys=True, allow_nan=False)
    return f"`{call.tool_name} {arguments}`"


def _reason(denial: Denial) -> str:
    """Watcher's public explanation as one sentence, whether or not it ends with punctuation."""
    reason = denial.reason.strip()
    return reason if reason.endswith((".", "!", "?")) else reason + "."


def denial_notice(denials: list[Denial], *, cancelled: list[ToolCall] | None = None) -> str:
    """Describe withheld calls to the user and to the model's later turns, one line per call.

    Each line names the call with its exact arguments and Watcher's public
    reason, and says Watcher added it, because the client's next request
    carries it inside the model's own turn. A model that sees unexplained text
    there tends to call it injected or its own mistake and disbelieve the
    denial. Escalations are marked ``WATCHER ESCALATION``, denials ``WATCHER
    NOTICE``. ``cancelled`` lists the unrefused siblings withheld because of
    another call's refusal.
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


def stop_notice(denials: list[Denial]) -> str:
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


def _tool_result(call_id: str, denials: dict[str, Denial], *, stop: bool, escalated: bool) -> str:
    """Explain a withheld call's delivery state without inventing a client execution result.

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


def operation_key(call: ToolCall) -> str:
    """Identify an operation independently of its call ID, keeping JSON's distinction between true and 1."""
    return json.dumps([call.tool_name, call.tool_input], ensure_ascii=False, sort_keys=True, allow_nan=False)


def continuation(request: dict, response: dict, calls: list[ToolCall], denials: list[Denial], *, stop: bool) -> dict:
    """The request that shows the model its refused proposal and asks what to do next.

    Appends the proposal's assistant message, unchanged (reasoning fields
    included), and one ``tool`` result per call in ``calls``, the proposal's
    calls in order, to a copy of ``request``. Tools, tool choice, parallel
    tool calls, every other option and all history are kept, so an
    alternative cannot use a tool the client excluded. With ``stop`` (the
    final generation, after an escalation or the third refused proposal) the
    results ask the model to stop and ask the user, and ``tool_choice``
    becomes ``"none"`` when the request offers tools; without tools it is left
    alone, since OpenAI rejects a tool choice without tools. The request is
    buffered (``stream`` false, no ``stream_options``).
    """
    by_id = {denial.tool_use_id: denial for denial in denials}
    escalated = any(denial.is_escalation for denial in denials)
    result = deepcopy(request)
    result.pop("stream_options", None)
    result["stream"] = False
    if stop and result.get("tools"):
        result["tool_choice"] = "none"
    result["messages"].append(deepcopy(response["choices"][0]["message"]))
    for call in calls:
        result["messages"].append(
            {
                "role": "tool",
                "tool_call_id": call.tool_use_id,
                "content": _tool_result(call.tool_use_id, by_id, stop=stop, escalated=escalated),
            }
        )
    return result


def without_calls(response: dict) -> dict:
    """A copy of a Chat response with its tool calls removed and the turn ended (``finish_reason`` stop)."""
    result = deepcopy(response)
    choice = result["choices"][0]
    choice["message"].pop("tool_calls", None)
    choice["finish_reason"] = "stop"
    return result


def check_mergeable(response: dict) -> None:
    """Raise ``MergeError`` unless an alternative's message fields can be merged into the delivered reply.

    Text fields must be strings; unknown populated fields (audio, multimodal
    parts, provider extensions) are refused rather than dropped.
    """
    message = response["choices"][0]["message"]
    for key, value in message.items():
        if key not in _ALTERNATIVE_FIELDS and value is not None and value not in _EMPTY_DEFAULTS.get(key, []):
            raise MergeError("The alternative carries message fields the gateway cannot merge")
    if any(
        message.get(key) is not None and not isinstance(message[key], str)
        for key in ("content", "refusal", "reasoning_content")
    ):
        raise MergeError("The alternative's text must be a string")


def compose(response: dict, notice: str, alternative: dict | None, *, trailer: str | None = None) -> dict:
    """Replace every call in ``response`` with ``notice`` and, if given, an alternative.

    No original call has reached the client, so all are removed together. The
    content becomes the original text, the notice, then the alternative's
    text, then ``trailer`` (the question that ends the response when no
    usable reply followed); the alternative supplies the calls and finish
    reason. The original
    id, created time, model and usage are kept: usage describes the first
    provider attempt only. Token log probabilities are dropped, since they
    describe the refused answer. ``alternative`` must have passed
    ``check_mergeable``. Original content given as a list of parts keeps its
    parts and gains the added text as further text parts.
    """
    message = dict(response["choices"][0]["message"])
    message.pop("tool_calls", None)
    other = alternative["choices"][0]["message"] if alternative is not None else {}
    added = [part for part in (notice, other.get("content"), trailer) if part]
    original = message.get("content")
    if isinstance(original, list):
        message["content"] = [*original, *({"type": "text", "text": text} for text in added)]
    else:
        message["content"] = "\n\n".join([original, *added] if isinstance(original, str) and original else added)
    for key in ("refusal", "reasoning_content"):
        if other.get(key) and isinstance(message.get(key) or "", str):
            message[key] = (message.get(key) or "") + other[key]
    if other.get("tool_calls"):
        message["tool_calls"] = other["tool_calls"]
        reason = "tool_calls"
    else:
        reason = alternative["choices"][0]["finish_reason"] if alternative is not None else "stop"
    choice = {**response["choices"][0], "message": message, "finish_reason": reason}
    choice.pop("logprobs", None)
    return {**response, "choices": [choice]}
