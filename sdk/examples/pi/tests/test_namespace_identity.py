"""Provider namespaces must not change the name Pi dispatches and reports in hooks."""

import asyncio
import json
from copy import deepcopy

import httpx
import pytest
from watcher_pi_bridge.enforcement import apply_policy, pending_messages
from watcher_pi_bridge.integration import convert

from watcher_sdk import AsyncWatcherClient


@pytest.mark.parametrize("name", ["bash", "mcp__files__write", "files.write"])
def test_provider_namespace_preserves_native_dispatch_identity(name):
    """An existing pending call matches the callback and remains linked to its native result."""
    records = [
        {"role": "user", "content": "Run the requested native tool"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "toolCall",
                    "id": "native-namespaced-call",
                    "name": name,
                    "namespace": "provider_tools",
                    "arguments": {"command": "printf executed"},
                }
            ],
        },
    ]
    original = deepcopy(records)
    call = {"id": "native-namespaced-call", "function": name, "arguments": {"command": "printf executed"}}
    messages = convert(records)
    assert pending_messages(messages, call) == messages
    assert messages[-1]["tool_calls"] == [call]
    assert records == original
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=[
                {
                    "tool_use_id": "native-namespaced-call",
                    "decision": "allow",
                    "judged_decision": "allow",
                    "enforcement_mode": "enforce",
                    "decision_source": "rule",
                    "verdict": {},
                    "latency_ms": 1,
                }
            ],
        )

    async def approve():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, "namespaced-session", messages, call)

    asyncio.run(approve())
    assert len(requests) == 1
    assert requests[0]["input"][0]["tool_name"] == name
    assert requests[0]["messages"][-1]["tool_calls"] == [call]
    completed = convert(
        [
            *records,
            {
                "role": "toolResult",
                "toolCallId": "native-namespaced-call",
                "toolName": name,
                "content": [{"type": "text", "text": "executed"}],
                "isError": False,
            },
        ]
    )
    assert completed[-1]["tool_call_id"] == "native-namespaced-call"
    assert completed[-1]["function"] == name
