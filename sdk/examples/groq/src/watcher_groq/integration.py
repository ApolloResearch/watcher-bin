"""Observe and gate buffered groq calls using the public raw provider hook.

The native client retains its own message format. Watcher converts original HTTP
pairs; tool results are ingested with the next successful provider exchange.
"""

from copy import deepcopy

from groq import AsyncGroq

from watcher_groq.observation import ObservationQueue
from watcher_groq.raw import decode, validate_request


def make_client(api_key, base_url, http_client=None):
    """Construct the native buffered Groq client; callers own its context lifetime."""
    return AsyncGroq(api_key=api_key, base_url=base_url, http_client=http_client, max_retries=0)


async def fetch(client, request):
    """Read public raw-response bytes before native normalization changes the JSON."""
    validate_request(request, "chat_completions")
    raw = await client.chat.completions.with_raw_response.create(**deepcopy(request))
    wire = raw.http_response
    return await raw.parse(), {
        "request": decode(wire.request.content),
        "response": decode(wire.content),
        "url": str(wire.request.url),
        "user_agent": wire.request.headers.get("user-agent"),
    }


class Observation(ObservationQueue):
    """Queue released native HTTP pairs for advisory monitoring."""


async def complete(client, observation, *, model, messages, tools=None):
    """Return native output and queue its original exchange for observation.

    Provider failures propagate. Watcher failures are visible after flush through
    error_count/errors. The caller retains full native tool-result history.
    """
    request = {"model": model, "messages": deepcopy(messages)}
    if tools is not None:
        request["tools"] = deepcopy(tools)
    response, exchange = await fetch(client, request)
    observation.enqueue(exchange)
    return response
