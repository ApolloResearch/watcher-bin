"""Observe and gate buffered mistralai calls using the public raw provider hook.

The native client retains its own message format. Watcher converts original HTTP
pairs; tool results are ingested with the next successful provider exchange.
"""

from contextlib import asynccontextmanager
from copy import deepcopy

import httpx
from mistralai.client import Mistral

from watcher_mistralai.capture import capture_response, captured
from watcher_mistralai.observation import ObservationQueue
from watcher_mistralai.raw import validate_request


@asynccontextmanager
async def make_client(api_key, base_url, http_client=None):
    """Yield a native Mistral client with a public HTTPX capture hook installed.

    Existing response hooks are retained. Do not share this transport with another
    client context. A supplied transport remains caller-owned; an internally
    created transport is closed on exit. No global client settings are changed.
    """
    transport = http_client or httpx.AsyncClient()
    transport.event_hooks["response"].append(capture_response)
    try:
        async with Mistral(api_key=api_key, server_url=base_url, async_client=transport) as client:
            yield client
    finally:
        transport.event_hooks["response"].remove(capture_response)
        if http_client is None:
            await transport.aclose()


async def fetch(client, request):
    """Capture a native buffered chat call; the make_client context owns the hook."""
    validate_request(request, "chat_completions")
    return await captured(client.chat.complete_async, **deepcopy(request))


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
