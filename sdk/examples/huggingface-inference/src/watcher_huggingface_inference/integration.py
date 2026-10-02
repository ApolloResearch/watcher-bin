"""Observe and gate buffered huggingface-inference calls using the public raw provider hook.

The native client retains its own message format. Watcher converts original HTTP
pairs; tool results are ingested with the next successful provider exchange.
"""

from copy import deepcopy

from huggingface_hub import AsyncInferenceClient, set_async_client_factory

from watcher_huggingface_inference.capture import capture_response, captured
from watcher_huggingface_inference.observation import ObservationQueue
from watcher_huggingface_inference.raw import validate_request

_configured = False


def configure_http_client_factory(factory):
    """Install the application's public Hugging Face HTTP factory with capture.

    This explicitly changes Hugging Face's process-wide async client factory.
    Call once at application startup, before creating native clients. Pass your
    existing factory to preserve its proxies, TLS, timeouts and response hooks;
    each invocation must return a fresh HTTPX AsyncClient. This helper never
    replaces a customer's factory implicitly and never reads private SDK state.
    """

    def wrapped():
        client = factory()
        client.event_hooks["response"].append(capture_response)
        return client

    global _configured
    set_async_client_factory(wrapped)
    _configured = True


def make_client(api_key, base_url):
    """Create a native dedicated-endpoint client after explicit HTTP factory setup."""
    if not _configured:
        raise RuntimeError("Call configure_http_client_factory before creating an inference client")
    return AsyncInferenceClient(api_key=api_key, base_url=base_url)


async def fetch(client, request):
    """Capture raw Chat Completions JSON before generated types insert default keys."""
    validate_request(request, "chat_completions")
    return await captured(client.chat_completion, **deepcopy(request))


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
