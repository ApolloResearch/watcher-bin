"""Gate native openai responses with Watcher's raw provider hook.

The caller supplies complete native history and executes only returned tools.
Provider requests and responses retain their wire JSON, URL and User-Agent;
Watcher converts them. Buffered client function tools are supported. Tool results
enter Watcher in the next successful provider exchange, so retain native history
if generation fails or the conversation stops between turns.
"""

from copy import deepcopy
from typing import Literal

from openai import AsyncOpenAI

from watcher_openai.raw import decode, evaluate, validate_request
from watcher_sdk import AsyncWatcherClient


async def complete(
    provider: AsyncOpenAI,
    watcher: AsyncWatcherClient,
    request: dict,
    session_id: str,
    *,
    api: Literal["responses", "chat_completions"] = "responses",
    enforcement: Literal["server", "enforce", "observe", "paused"] = "server",
    timeout: float | None = None,
):
    """Return a native response after every delivered tool has a matching decision.

    Both clients remain owned by the caller. Server settings are inherited;
    explicit overrides can be admin-locked. A denial, escalation, incomplete
    response or Watcher failure withholds the entire response. No tool executes
    here. Hook ingestion is asynchronous; verify recording through public reads.
    """
    if not session_id.strip() or enforcement not in {"server", "enforce", "observe", "paused"}:
        raise ValueError("A session ID and supported enforcement setting are required")
    payload = deepcopy(request)
    validate_request(payload, api)
    create = (
        provider.responses.with_raw_response.create
        if api == "responses"
        else provider.chat.completions.with_raw_response.create
    )
    raw = await create(**payload)
    wire = raw.http_response
    response = decode(wire.content)
    await evaluate(
        watcher,
        request=decode(wire.request.content),
        response=response,
        url=str(wire.request.url),
        user_agent=wire.request.headers.get("user-agent"),
        provider="openai",
        api=api,
        session_id=session_id,
        enforcement=enforcement,
        timeout=timeout,
    )
    return raw.parse()
