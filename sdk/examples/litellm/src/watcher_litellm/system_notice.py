"""Tell the model, on every request, how to read Watcher's notices in its own turn.

When Watcher refuses a call, the callback asks the model for another approach
and returns the approved alternative with a ``WATCHER NOTICE`` in the same
reply. The client's next request carries that notice inside the model's own
turn, as text the model never wrote. Without an explanation, models often call
it injected or their own mistake, disbelieve the denial and retry. This fixed
system text explains the notices and says how to continue after a denial or an
escalation.

The text is byte-identical on every request, including those with no denial
yet, so the request prefix stays cacheable and no per-session state is needed.
It is added after the client's own system instructions, never before them, so
their cached prefix is unchanged. A request that already contains the text,
for example from managed client settings, is left as it is.
"""

from typing import Any

from watcher_litellm.streams import API

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


def _leading_instructions(messages: list[Any], roles: set[str]) -> int:
    """Count the messages at the start of a conversation that hold system instructions."""
    count = 0
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in roles:
            break
        count += 1
    return count


def system_notice_fields(api: API, body: dict[str, Any]) -> dict[str, Any]:
    """The request fields to replace so that ``body`` carries the notice, or ``{}`` to leave it unchanged.

    Returns new values and never mutates ``body``:

    - Messages: ``system`` gains a final text block, without ``cache_control``,
      after any string or blocks the client sent.
    - Chat Completions: a ``system`` message after the leading system and
      developer messages.
    - Responses: a ``developer`` message after the leading system and developer
      items of ``input``; string input becomes that message plus a user message.
      ``instructions`` is left unchanged.

    A body that already carries the notice, or whose field has a shape these
    APIs do not accept, is left unchanged: the notice is advice, and the
    provider reports a malformed request better than this callback can.
    """
    if api == "messages":
        system = body.get("system")
        if _contains_notice(system):
            return {}
        block = {"type": "text", "text": SYSTEM_NOTICE}
        if system is None or system == "":
            return {"system": [block]}
        if isinstance(system, str):
            return {"system": [{"type": "text", "text": system}, block]}
        if isinstance(system, list):
            return {"system": [*system, block]}
        return {}
    field = "messages" if api == "chat_completions" else "input"
    messages = body.get(field)
    if api == "responses" and isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    if not isinstance(messages, list):
        return {}
    position = _leading_instructions(messages, {"system", "developer"})
    if _contains_notice(messages[:position]):
        return {}
    notice = (
        {"role": "system", "content": SYSTEM_NOTICE}
        if api == "chat_completions"
        else {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": SYSTEM_NOTICE}]}
    )
    return {field: [*messages[:position], notice, *messages[position:]]}
