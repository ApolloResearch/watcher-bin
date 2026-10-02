"""Observe buffered Cohere V2 chat calls through the public Watcher SDK.

Use ``complete`` instead of the provider chat method and flush before shutdown.
Streaming and provider-executed tools are outside this example's supported scope.
"""

from copy import deepcopy
from typing import cast

from cohere import AsyncClientV2, ChatMessageV2, ToolV2

from watcher_cohere.conversion import convert_exchange
from watcher_cohere.observation import ObservationQueue


def make_client(api_key: str, base_url: str, http_client=None) -> AsyncClientV2:
    """Construct the upstream client; pass an HTTP transport only for local tests."""
    return AsyncClientV2(api_key=api_key, base_url=base_url, httpx_client=http_client, max_retries=0)


class Observation(ObservationQueue):
    """Normalize full buffered exchanges and enqueue ordered monitoring snapshots."""

    def record(self, request: dict, response: dict) -> None:
        try:
            exchange = convert_exchange(request, response)
        except ValueError as error:
            self.fail(type(error).__name__)
            return
        self.enqueue(exchange.messages, exchange.inputs)


async def complete(client: AsyncClientV2, observation: Observation, *, model: str, messages: list[dict], tools=None):
    """Run one native, non-streaming chat request and queue its full transcript.

    Provider failures propagate unchanged. A Watcher failure is reported by
    ``observation.errors`` after ``flush``, while the original result is returned.
    Supply tool results in the next call's history with their original call IDs.
    """
    # Cohere serializes JSON dictionaries as well as its annotated message/tool models.
    native_messages = cast(list[ChatMessageV2], deepcopy(messages))
    request: dict[str, object] = {"model": model, "messages": native_messages}
    if tools is not None:
        native_tools = cast(list[ToolV2], deepcopy(tools))
        request["tools"] = native_tools
        response = await client.chat(model=model, messages=native_messages, tools=native_tools)
    else:
        response = await client.chat(model=model, messages=native_messages)
    native = response.model_dump(mode="json", exclude_none=True)
    observation.record(request, native)
    return response
