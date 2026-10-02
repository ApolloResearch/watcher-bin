"""Capture exact buffered HTTP exchanges through public HTTPX response hooks."""

from contextvars import ContextVar

from watcher_huggingface_inference.raw import decode

_current: ContextVar[list | None] = ContextVar("watcher_provider_exchange", default=None)


async def capture_response(response):
    """Retain only successful responses inside the active monitored provider call.

    Authentication headers are never copied. The ContextVar isolates concurrent
    requests; captured bodies are consumed by the caller and not logged.
    """
    active = _current.get()
    if active is not None and 200 <= response.status_code < 300:
        await response.aread()
        active.append(
            {
                "request": decode(response.request.content),
                "response": decode(response.content),
                "url": str(response.request.url),
                "user_agent": response.request.headers.get("user-agent"),
            }
        )


async def captured(call, **request):
    """Run a buffered native method with exactly one captured successful exchange.

    Install capture_response on the client's public HTTPX transport first. A
    missing hook or ambiguous retry sequence fails rather than inventing raw JSON.
    """
    exchanges = []
    token = _current.set(exchanges)
    try:
        result = await call(**request)
    finally:
        _current.reset(token)
    if len(exchanges) != 1:
        raise RuntimeError("Expected one captured provider exchange; configure the HTTP client hook")
    return result, exchanges[0]
