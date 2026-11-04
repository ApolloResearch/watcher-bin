"""Watcher's texts for refused calls: client-visible notices, tool results and the system notice.

When Watcher refuses a proposal, the processor shows the client a notice and
asks the model, through tool results, for another approach. The wording
follows what kept agents working in Watcher's denial experiments with real
coding agents:

- A denial's tool result says that working around the block is fine, because
  Watcher checks every call. Inviting a text-only explanation instead ends the
  agent's turn: harnesses only call the model again after tool results.
- An escalation's tool result asks the model to stop and put the decision to
  the user with labelled options. Only Watcher's graders read the
  conversation, so the user can approve a call only when a grader escalated
  it; a rule, a threshold or the grading-failure policy would escalate it
  again, and the options then exclude "allow".
- Client-visible notices say that Watcher, not the model, wrote them. The
  client's next request carries them inside the model's own turn, and a model
  that sees unexplained text there tends to call it injected or its own
  mistake and retry the refused call.
- ``SYSTEM_NOTICE`` goes into every request and explains these notices up
  front. It is byte-identical on every request, so the request prefix stays
  cacheable and no per-session state is needed.

Nothing from a proposal reaches the client until Watcher has allowed every call
in it, so a refused proposal never has calls that were already delivered.
"""

import json
from copy import deepcopy

from watcher_agent_router.exchange import Denial, Evaluation, decode_json

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
# but it must stay small: the rewritten response replaces the provider's within
# the same size budget (MAX_BODY in processor.py).
_ECHO_LIMIT = 4096
_ID_LIMIT = 256
_NOTICE_LIMIT = 64 * 1024
_SUMMARY_ROOM = 256


def with_system_notice(request: dict) -> dict:
    """``request`` with ``SYSTEM_NOTICE`` as a system message after its leading instructions.

    The notice goes after the leading run of system and developer messages,
    never before them, so the caller's instruction order and cached prefix are
    unchanged. A request whose leading instructions already contain the text,
    for example from managed client settings, is returned as it is. Never
    mutates ``request``; call after ``validate_request``.
    """
    messages = request["messages"]
    position = 0
    while position < len(messages) and messages[position].get("role") in {"system", "developer"}:
        position += 1
    if SYSTEM_NOTICE in json.dumps(messages[:position], ensure_ascii=False):
        return request
    notice = {"role": "system", "content": SYSTEM_NOTICE}
    return {**request, "messages": [*messages[:position], notice, *messages[position:]]}


def _call_text(tool_name: str, tool_input: object) -> str:
    """Name a call with its arguments as a reader would recognize it, shortening long ones."""
    arguments = json.dumps(tool_input, ensure_ascii=False, sort_keys=True)
    if len(arguments) > _ECHO_LIMIT:
        arguments = arguments[:_ECHO_LIMIT] + " … (arguments shortened)"
    return f"`{tool_name[:_ID_LIMIT]} {arguments}`"


def _reason(denial: Denial) -> str:
    """Watcher's public explanation as one sentence, shortened, whether or not it ends with punctuation."""
    reason = denial.reason.strip()[:_ECHO_LIMIT]
    return reason if reason.endswith((".", "!", "?")) else reason + "."


def _line(denial: Denial) -> str:
    """One refused call as a client-visible notice line."""
    call = _call_text(denial.tool_name, denial.tool_input)
    if not denial.is_escalation:
        return f"WATCHER NOTICE {_ADDED_BY_WATCHER}: Watcher blocked {call}. Reason: {_reason(denial)} The call did not run."
    if denial.user_can_approve:
        return (
            f"WATCHER ESCALATION {_ADDED_BY_WATCHER}: {call} needs the user's decision before it can run. "
            f"Reason: {_reason(denial)} The call did not run."
        )
    return (
        f"WATCHER ESCALATION {_ADDED_BY_WATCHER}: {_HELD.format(call=call)} "
        f"Reason: {_reason(denial)} The call did not run."
    )


def denial_notice(denials: list[Denial], cancelled: list[tuple[str, object]]) -> str:
    """Describe withheld calls to the user and to the model's later turns, one paragraph per call.

    Escalations are marked ``WATCHER ESCALATION``, denials ``WATCHER
    NOTICE``. ``cancelled`` holds the (name, arguments) of calls withheld only
    because another call in the same response was refused; none of them ran.
    Long arguments and reasons are shortened, and once the notice reaches its
    size limit the remaining refused and withheld calls are only counted, so
    the rewritten response stays within the gateway's body limit.
    """
    entries = [_line(denial) for denial in denials] + [
        f"WATCHER NOTICE {_ADDED_BY_WATCHER}: {_call_text(name, arguments)} {_SIBLING}" for name, arguments in cancelled
    ]
    lines: list[str] = []
    # Encoded bytes and separators count, and room is kept for the count line.
    size = _SUMMARY_ROOM
    for line in entries:
        size += len(line.encode()) + 2
        if lines and size > _NOTICE_LIMIT:
            refused = max(len(denials) - len(lines), 0)
            lines.append(
                f"WATCHER NOTICE {_ADDED_BY_WATCHER}: {refused} more refused calls and "
                f"{len(entries) - len(lines) - refused} more withheld calls did not run."
            )
            break
        lines.append(line)
    return "\n\n".join(lines)


def withheld_notice(response: dict, evaluation: Evaluation, compact: bool = False) -> str:
    """The notice for a response's refused calls and the siblings withheld with them.

    ``compact`` gives a short count-only notice, for when the full one would
    push the rewritten response past its size budget.
    """
    denied = {denial.tool_use_id for denial in evaluation.denials}
    calls = response["choices"][0]["message"].get("tool_calls") or []
    cancelled = [
        (call["function"]["name"], decode_json(call["function"]["arguments"]))
        for call in calls
        if call["id"] not in denied
    ]
    if compact:
        return (
            f"WATCHER NOTICE {_ADDED_BY_WATCHER}: Watcher refused {len(evaluation.denials)} tool calls, so the gateway "
            f"withheld them and {len(cancelled)} other calls from the same response. None of them ran."
        )
    return denial_notice(evaluation.denials, cancelled)


def stop_notice(denials: list[Denial]) -> str:
    """End a response whose final, text-only generation proposed tool calls anyway.

    ``denials`` are the refusals that triggered the final generation. That
    generation was asked to stop and ask the user, so its calls are withheld
    without being graded, and this text puts the question to the user instead.
    It offers approval only when every escalation can be approved in the
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


def _tool_result(denial: Denial | None, *, stop: bool, escalated: bool) -> str:
    """What the model reads as one call's result: Watcher's reason and what to do next.

    Without ``stop`` a denial asks for another approach. On the final
    generation an escalation alone carries the ask, so a denied sibling's
    result adds no instruction that could contradict it.
    """
    if denial is None:
        return f"This call {_SIBLING}"
    if denial.is_escalation and denial.user_can_approve:
        return (
            "WATCHER ESCALATION: this call needs the user's decision before it can run. "
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


def continuation(request: dict, response: dict, evaluation: Evaluation, *, stop: bool = False) -> dict:
    """The request that asks the model what to do after a refused proposal.

    Appends the proposal and one tool result per call to a copy of the
    request: refused calls get Watcher's reason, their siblings say they did
    not run. Nothing in the proposal reached the client, so no result
    describes an execution. The request is buffered (``stream`` false)
    whatever the client asked for.

    Without ``stop`` a denied call's result asks for another approach, and
    tools, tool choice and every other option are kept, so an alternative
    cannot use a tool the client excluded. With ``stop`` (the final
    generation, after an escalation or the third refused proposal) results ask
    the model to stop and ask the user, and ``tool_choice`` becomes ``none``
    when the request offers tools so the model answers in text. A request
    without tools keeps no tool choice: OpenAI rejects one without tools.
    """
    result = deepcopy(request)
    result.pop("stream_options", None)
    result["stream"] = False
    if stop and result.get("tools"):
        result["tool_choice"] = "none"
    message = deepcopy(response["choices"][0]["message"])
    result["messages"].append(message)
    denials = {denial.tool_use_id: denial for denial in evaluation.denials}
    escalated = any(denial.is_escalation for denial in evaluation.denials)
    for call in message.get("tool_calls") or []:
        content = _tool_result(denials.get(call["id"]), stop=stop, escalated=escalated)
        result["messages"].append({"role": "tool", "tool_call_id": call["id"], "content": content})
    return result
