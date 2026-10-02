"""Native provider clients backed by deterministic local HTTP transports."""

import asyncio
import json
from contextlib import asynccontextmanager
from copy import deepcopy

import httpx
from watcher_huggingface_inference.integration import configure_http_client_factory, make_client

from watcher_sdk import AsyncWatcherClient

CALLS: list[dict] = [
    {"id": "call-a", "type": "function", "function": {"name": "weather", "arguments": '{"city":"Paris"}'}},
    {"id": "call-b", "type": "function", "function": {"name": "weather", "arguments": '{"city":"Tokyo"}'}},
]
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "Read weather",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
        },
    }
]
HISTORY = [{"role": "user", "content": "Read weather"}]


def reply(*, calls=None, text="Done"):
    return {
        "id": "chat-1",
        "object": "chat.completion",
        "created": 1,
        "model": "fixture-model",
        "system_fingerprint": "fixture",
        "provider_extension": {"kept": True, "null": None},
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None if calls else text,
                    **({"tool_calls": deepcopy(calls)} if calls else {}),
                },
                "finish_reason": "tool_calls" if calls else "stop",
            }
        ],
    }


class Transport:
    def __init__(
        self,
        responses=None,
        *,
        mode="enforce",
        decision="allow",
        mutation=None,
        provider_status=200,
        watcher_status=200,
    ):
        self.responses = iter(responses or [reply(calls=CALLS)])
        self.mode, self.decision, self.mutation = mode, decision, mutation
        self.provider_status, self.watcher_status = provider_status, watcher_status
        self.provider_requests, self.watcher_requests, self.wire_responses = [], [], []
        self.started, self.release = asyncio.Event(), asyncio.Event()
        self.release.set()

    def provider(self, request):
        self.provider_requests.append(request)
        body = next(self.responses)
        self.wire_responses.append(body)
        return httpx.Response(self.provider_status, json=body)

    async def watcher(self, request):
        self.started.set()
        await self.release.wait()
        body = json.loads(request.content)
        self.watcher_requests.append(body)
        assert body["format"] == "raw"
        assert body["provider"] == "huggingface"
        matching = [item for item in self.provider_requests if json.loads(item.content) == body["request_body"]]
        assert matching
        assert body["url"] == str(matching[-1].url)
        assert body["user_agent"] == matching[-1].headers["user-agent"]
        assert body["response_body"] in self.wire_responses
        assert "input" not in body and "messages" not in body
        if self.watcher_status != 200:
            return httpx.Response(self.watcher_status, json={"detail": "unavailable"})
        outcomes = [
            {
                "tool_use_id": call["id"],
                "decision": "deferred" if self.mode in {"observe", "paused"} else self.decision,
                "judged_decision": None if self.mode == "paused" else self.decision,
                "decision_source": "bypass" if self.mode == "paused" else "rule",
                "enforcement_mode": self.mode,
                "verdict": {},
                "latency_ms": 0,
            }
            for index, call in enumerate(body["response_body"]["choices"][0]["message"].get("tool_calls", []))
        ]
        if self.mutation == "missing":
            outcomes = []
        elif self.mutation == "wrong-id":
            outcomes[0]["tool_use_id"] = "other"
        elif self.mutation == "missing-id":
            outcomes[0].pop("tool_use_id")
        elif self.mutation == "reverse":
            outcomes.reverse()
        elif self.mutation == "duplicate":
            outcomes[-1] = outcomes[0]
        elif self.mutation == "deny-second":
            outcomes[-1].update(decision="deny", judged_decision="deny")
        elif self.mutation == "failure-allow":
            for outcome in outcomes:
                outcome.update(
                    decision_source="grading_error", grading_error={"code": "grader_failed", "message": "fixture"}
                )
        return httpx.Response(200, json=outcomes)


@asynccontextmanager
async def clients(transport):
    provider_http = httpx.AsyncClient(transport=httpx.MockTransport(transport.provider))
    configure_http_client_factory(lambda: provider_http)
    provider_context = make_client("hf_fixture", "https://provider.invalid/v1")
    try:
        async with (
            provider_context as provider,
            AsyncWatcherClient(
                "https://watcher.invalid",
                max_retries=0,
                httpx_client=httpx.AsyncClient(
                    base_url="https://watcher.invalid", transport=httpx.MockTransport(transport.watcher)
                ),
            ) as watcher,
        ):
            yield provider, watcher
    finally:
        await provider_http.aclose()
