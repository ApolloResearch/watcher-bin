"""Tell the model, on every request, how to read Watcher's notices in its own turn.

When Watcher refuses a call, the bridge asks the model for another approach and
returns the approved alternative with a ``WATCHER NOTICE`` in the same reply.
The client's next request carries that notice inside the model's own turn, as
text the model never wrote. Without an explanation, models often call it
injected or their own mistake, disbelieve the denial and retry. This fixed
system text explains the notices and says how to continue after a denial or an
escalation.

The text is byte-identical on every request, including those with no denial
yet, so the request prefix stays cacheable and no per-session state is needed.
It is added after the client's own system and developer messages, never before
them, so their order and cached prefix are unchanged. A request that already
contains the text there, for example from managed client settings, is left as
it is.
"""

from typing import Any

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


def _contains_notice(value: Any) -> bool:
    """Whether any string inside ``value`` already includes the notice."""
    if isinstance(value, str):
        return SYSTEM_NOTICE in value
    if isinstance(value, dict):
        return any(_contains_notice(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_notice(item) for item in value)
    return False


def with_system_notice(request: dict[str, Any]) -> dict[str, Any] | None:
    """A copy of a Chat Completions request carrying the notice, or None to leave it unchanged.

    The notice becomes a ``system`` message after the leading run of system and
    developer messages. ``request`` is never mutated. A request whose leading
    instructions already contain the notice, or whose ``messages`` is not a
    list, is left unchanged: the notice is advice, and the provider reports a
    malformed request better than the gateway can.
    """
    messages = request.get("messages")
    if not isinstance(messages, list):
        return None
    position = 0
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in ("system", "developer"):
            break
        position += 1
    if _contains_notice(messages[:position]):
        return None
    notice = {"role": "system", "content": SYSTEM_NOTICE}
    return {**request, "messages": [*messages[:position], notice, *messages[position:]]}
