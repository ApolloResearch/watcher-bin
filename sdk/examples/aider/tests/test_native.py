"""Aider executes its actual Coder loop against LiteLLM's supported fake response."""

import asyncio
import json

import httpx
from aider.coders import Coder
from aider.io import InputOutput
from aider.models import Model
from watcher_aider.integration import convert, send

from watcher_sdk import AsyncWatcherClient


def test_native_coder_final_history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    model = Model("gpt-4o")
    model.extra_params = {"mock_response": "finished"}
    coder = Coder.create(
        main_model=model,
        edit_format="whole",
        io=InputOutput(yes=False, pretty=False),
        use_git=False,
        stream=False,
        map_tokens=0,
    )
    coder.run(with_message="Respond with finished; do not edit files")
    messages = convert(coder.done_messages + coder.cur_messages)
    assert "finished" in str(messages)
    assert all(not row.get("tool_calls") for row in messages)
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=[])

    async def exercise():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://watcher.test", transport=httpx.MockTransport(respond))
        ) as client:
            await send(client, "native-coder", messages)

    asyncio.run(exercise())
    assert requests[-1]["messages"] == messages
