"""Unknown provider metadata must not alter OpenClaw's native tool name."""

import asyncio
import json
from copy import deepcopy

import httpx
import pytest
from watcher_openclaw_bridge.enforcement import apply_policy, pending_messages
from watcher_openclaw_bridge.integration import convert

from watcher_sdk import AsyncWatcherClient


@pytest.mark.parametrize("name", ["exec", "mcp__files__write", "files.write"])
def test_provider_namespace_preserves_native_dispatch_identity(name):
    """A foreign namespace field cannot change callback matching or result linkage."""
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
    assert messages[-1]["tool_calls"] == [{**call, "type": "function"}]
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
    assert requests[0]["messages"][-1]["tool_calls"] == [{**call, "type": "function"}]
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
