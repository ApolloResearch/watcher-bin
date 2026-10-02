"""Check native Google request identities without contacting a hosted provider."""

import json

import pytest
from google.genai import types
from watcher_google_genai.monitoring import Monitor, Withheld

from tests.test_monitoring import Decisions, callbacks, clients, invoke, start_history, text_reply, tool_reply


@pytest.mark.asyncio
@pytest.mark.parametrize("time_id", [None, "google-b"])
async def test_missing_provider_ids_stay_absent_from_native_function_responses(tmp_path, time_id):
    response = tool_reply()
    del response["candidates"][0]["content"]["parts"][0]["functionCall"]["id"]
    response["candidates"][0]["content"]["parts"][1]["functionCall"]["id"] = time_id
    transport = Decisions()
    transport.responses = iter([response, text_reply()])
    provider, watcher = clients(transport)
    async with provider, watcher:
        monitor = Monitor(watcher, "native-id-fidelity")
        history = await invoke(provider, monitor, start_history(), callbacks(tmp_path / "effects"))
        assert history[-1].parts[0].function_response.id is None
        await invoke(provider, monitor, history, callbacks(tmp_path / "effects"))
    request = json.loads(transport.provider_requests[1].content)
    results = [
        part["functionResponse"]
        for content in request["contents"]
        for part in content["parts"]
        if "functionResponse" in part
    ]
    assert "id" not in results[0]
    if time_id is None:
        assert "id" not in results[1]
    else:
        assert results[1]["id"] == "google-b"
    assert types.FunctionResponse.model_validate(results[0]).id is None
    assert transport.watcher_requests[0]["input"][0]["tool_use_id"] == "genai-1-0"
    assert transport.watcher_requests[-1]["messages"][:-1] == transport.watcher_requests[-2]["messages"]
    assert (tmp_path / "effects").read_text().splitlines() == ["Paris", "Tokyo"]


@pytest.mark.asyncio
async def test_ambiguous_idless_calls_are_recorded_before_any_tool_executes(tmp_path):
    response = tool_reply()
    for part in response["candidates"][0]["content"]["parts"]:
        part["functionCall"].pop("id")
        part["functionCall"]["name"] = "weather"
    transport = Decisions()
    transport.responses = iter([response])
    provider, watcher = clients(transport)
    async with provider, watcher:
        with pytest.raises(Withheld, match="unique pending names"):
            await invoke(
                provider, Monitor(watcher, "ambiguous-native-ids"), start_history(), callbacks(tmp_path / "effects")
            )
    assert not (tmp_path / "effects").exists()
    assert len(transport.watcher_requests) == 1
    assert transport.watcher_requests[0]["input"] == []
