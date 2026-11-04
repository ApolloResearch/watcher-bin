"""Build truthful Chat Completions continuations and the notices a client receives.

The bridge owns attempt limits, deadlines, grading and delivery. These helpers
describe refused calls to the model (as tool results) and to the client (as
notices in the delivered reply), and compose the one completion the client
receives.

Nothing from a proposal reaches the client until every call in it is allowed,
so a refused proposal never has calls that were already released: its other
calls are withheld siblings, and every tool result says the call did not run.
That is why there is no receipt for a released call here.

The texts follow the wording that kept agents working in Watcher's denial
experiments. A denial's result says that working around the block is fine,
because Watcher checks every call; inviting a text-only explanation instead
ends the agent's turn, since harnesses only call the model again after tool
results. An escalation's result asks the model to stop and put the decision to
the user with labelled options. Client-visible notices say that Watcher, not
the model, wrote them: the next request carries them in the model's own turn.
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

# Message fields an alternative may carry. Any other populated field could not
# be merged into the delivered message without losing or misplacing it.
_ALTERNATIVE_FIELDS = {"role", "content", "tool_calls", "refusal", "reasoning_content"}
# Fields providers routinely send empty, which carry nothing to merge.
_EMPTY_DEFAULTS: dict[str, list] = {"annotations": [[]]}


@dataclass(frozen=True)
class ToolCall:
    """A client function call with its parsed JSON-object arguments."""

    tool_use_id: str
    tool_name: str
    tool_input: dict[str, Any]


@dataclass(frozen=True)
class ToolDenial(ToolCall):
    """A refused call and Watcher's public explanation, excluding grader prompts and scores.

    ``user_can_approve`` says whether the user's answer can lead to approval of
    an escalation. Only Watcher's graders read the conversation; a rule, a
    threshold or the grading-failure policy decides again without it, so
    offering "allow" there would escalate the same call in a loop.
    """

    reason: str
    is_escalation: bool
    user_can_approve: bool = False


class UnmergeableAlternative(ValueError):
    """A generated alternative carries content the gateway cannot deliver faithfully."""


def tool_calls(response: dict[str, Any]) -> list[ToolCall]:
    """The client function calls of an already validated response, in provider order."""
    calls = response["choices"][0]["message"].get("tool_calls") or []
    return [
        ToolCall(
            tool_use_id=call["id"],
            tool_name=call["function"]["name"],
            tool_input=json.loads(call["function"]["arguments"]),
        )
        for call in calls
    ]


def operation_key(call: ToolCall) -> str:
    """Identify an operation independently of its call ID, keeping JSON's distinction between true and 1."""
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
    NOTICE``. ``cancelled`` contains unevaluated or allowed siblings withheld
    because of another call's refusal. Long arguments and reasons are
    shortened, and once the notice reaches its size limit the remaining
    refused and withheld calls are only counted.
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


def continuation(
    request: dict[str, Any], response: dict[str, Any], denials: list[ToolDenial], *, stop: bool
) -> dict[str, Any]:
    """The request asking the model for another proposal, without mutating either input.

    Appends the refused assistant message unchanged (reasoning fields included)
    and one ``tool`` result per call: refused calls get Watcher's explanation,
    their siblings say they did not run. Tools, tool choice, parallel tool
    calls, every other option and all history are kept, so an alternative
    cannot use a tool the client excluded. With ``stop`` (the final
    generation, after an escalation or the third refused proposal) the results
    ask the model to stop and ask the user, and ``tool_choice`` becomes
    ``"none"`` when the request offers tools; without tools it is left alone,
    since OpenAI rejects a tool choice without tools. The request is buffered
    (``stream`` false, no ``stream_options``) whatever the client asked for.
    """
    result = deepcopy(request)
    result["stream"] = False
    result.pop("stream_options", None)
    if stop and result.get("tools"):
        result["tool_choice"] = "none"
    message = deepcopy(response["choices"][0]["message"])
    result["messages"].append(message)
    by_id = {denial.tool_use_id: denial for denial in denials}
    escalated = any(denial.is_escalation for denial in denials)
    for call in message.get("tool_calls") or []:
        result["messages"].append(
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": _tool_result(call["id"], by_id, stop=stop, escalated=escalated),
            }
        )
    return result


def alternative_message(response: dict[str, Any]) -> dict[str, Any]:
    """Return a generated response's assistant message once its fields are known to merge cleanly.

    Requires one choice holding an assistant message. Text fields must be
    strings; unknown populated fields (audio, multimodal parts, provider
    extensions) raise ``UnmergeableAlternative`` rather than being dropped.
    """
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise UnmergeableAlternative("The alternative must have exactly one choice")
    message = choices[0].get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise UnmergeableAlternative("The alternative must contain an assistant message")
    for key, value in message.items():
        if key not in _ALTERNATIVE_FIELDS and value is not None and value not in _EMPTY_DEFAULTS.get(key, []):
            raise UnmergeableAlternative("The alternative carries message fields the gateway cannot merge")
    if any(
        message.get(key) is not None and not isinstance(message[key], str)
        for key in ("content", "refusal", "reasoning_content")
    ):
        raise UnmergeableAlternative("The alternative's text must be a string")
    return message


def compose(
    original: dict[str, Any],
    notices: list[str],
    alternative: dict[str, Any] | None,
    *,
    release_calls: bool,
    closing: str | None = None,
) -> dict[str, Any]:
    """The single completion the client receives after a refusal.

    No original call has reached the client, so all are removed. The content
    becomes the original text, every notice, the alternative's text, then
    ``closing`` (the stop notice after a final generation that proposed calls).
    With ``release_calls`` (an approved alternative) the alternative supplies
    its tool calls and finish reason; otherwise no call is delivered and the
    finish reason is ``stop``. The original identity, creation time, model and
    usage are kept: usage describes the first provider attempt only. Token log
    probabilities are dropped, since they describe the refused answer.
    ``alternative`` must have passed ``alternative_message``.

    Original content given as a list of parts keeps its parts and gains the
    added text as further text parts.
    """
    message = dict(original["choices"][0]["message"])
    message.pop("tool_calls", None)
    other = alternative["choices"][0]["message"] if alternative is not None else {}
    added = [part for part in (*notices, other.get("content"), closing) if part]
    text = message.get("content")
    if isinstance(text, list):
        message["content"] = [*text, *({"type": "text", "text": part} for part in added)]
    else:
        message["content"] = "\n\n".join([text, *added] if isinstance(text, str) and text else added)
    for key in ("refusal", "reasoning_content"):
        if other.get(key) and isinstance(message.get(key) or "", str):
            message[key] = (message.get(key) or "") + other[key]
    reason = "stop"
    if release_calls and alternative is not None:
        if other.get("tool_calls"):
            message["tool_calls"] = deepcopy(other["tool_calls"])
        reason = alternative["choices"][0]["finish_reason"]
    choice = {**original["choices"][0], "message": message, "finish_reason": reason}
    choice.pop("logprobs", None)
    return {**original, "choices": [choice]}
