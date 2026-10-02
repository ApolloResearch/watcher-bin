"""Run compiled native LangChain4j against a private provider server, then the public SDK."""

import json
import os
import subprocess
import threading
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest
from watcher_langchain4j_bridge.bridge import observe_snapshots

from watcher_sdk import AsyncWatcherClient

CALLS: list[dict[str, Any]] = [
    {"id": "call-a", "type": "function", "function": {"name": "weather", "arguments": '{"city":"Paris"}'}},
    {"id": "call-b", "type": "function", "function": {"name": "weather", "arguments": '{"city":"Tokyo"}'}},
]


def response(message, reason):
    return {
        "id": "chat-1",
        "object": "chat.completion",
        "created": 1,
        "model": "fixture-model",
        "choices": [{"index": 0, "message": message, "finish_reason": reason}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }


def run_native(tmp_path, replies, status=200):
    """Run only this example's JVM and ephemeral local server; preserve full failure output."""
    received = []
    replies = iter(replies)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            body = json.dumps(next(replies)).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    classpath = os.environ["WATCHER_JAVA_CLASSPATH"]
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [
                os.environ["JAVA_BIN"],
                "-cp",
                classpath,
                "com.example.watcher.examples.langchain4j.WatcherExample",
                f"http://127.0.0.1:{server.server_port}/v1",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
            env={**os.environ, "PROVIDER_API_KEY": "fixture-key", "PROVIDER_MODEL": "fixture-model"},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert not thread.is_alive()
    return {"process": result, "requests": received}


@pytest.mark.asyncio
async def test_native_listener_tools_results_and_tail_reach_public_sdk(tmp_path):
    result = run_native(
        tmp_path,
        [
            response({"role": "assistant", "content": None, "tool_calls": CALLS}, "tool_calls"),
            response({"role": "assistant", "content": "Finished."}, "stop"),
        ],
    )
    assert result["process"].returncode == 0, result["process"].stdout + result["process"].stderr
    assert result["requests"][0]["tools"][0]["function"]["name"] == "weather"
    assert result["requests"][1]["messages"][2]["tool_call_id"] == "call-a"
    captured = []

    def handler(request):
        payload = json.loads(request.content)
        captured.append(payload)
        outcomes = [
            {
                "decision": "deferred",
                "judged_decision": "deny",
                "decision_source": "rule",
                "enforcement_mode": "observe",
                "verdict": {},
                "latency_ms": 1,
                "tool_use_id": item["tool_use_id"],
            }
            for item in payload["input"]
        ]
        return httpx.Response(200, json=outcomes)

    async with AsyncWatcherClient(
        "https://watcher.invalid",
        httpx_client=httpx.AsyncClient(base_url="https://watcher.invalid", transport=httpx.MockTransport(handler)),
    ) as watcher:
        queue = await observe_snapshots(watcher, [tmp_path / "0.json", tmp_path / "1.json"], "java-session")
    assert queue.errors == []
    assert captured[0]["input"] == [
        {"tool_use_id": "call-a", "tool_name": "weather", "tool_input": {"city": "Paris"}},
        {"tool_use_id": "call-b", "tool_name": "weather", "tool_input": {"city": "Tokyo"}},
    ]
    assert captured[-1]["input"] == []
    assert captured[-1]["messages"][-1]["content"] == "Finished."
    assert captured[-1]["messages"][2]["tool_call_id"] == "call-a"
    assert captured[-1]["messages"][3]["tool_call_id"] == "call-b"


def test_native_provider_failure_does_not_write_successful_snapshots(tmp_path):
    result = run_native(tmp_path, [{"error": {"message": "invalid request", "type": "invalid_request_error"}}], 400)
    assert result["process"].returncode != 0
    assert "invalid request" in result["process"].stderr
    assert list(tmp_path.glob("*.json")) == []


@pytest.mark.parametrize("arguments", ["{bad", "[1,2]", '{"city":"Paris","city":"Tokyo"}'])
def test_malformed_native_tool_arguments_fail_visibly(tmp_path, arguments):
    calls = deepcopy(CALLS)
    calls[0]["function"]["arguments"] = arguments
    result = run_native(
        tmp_path,
        [
            response({"role": "assistant", "content": None, "tool_calls": calls}, "tool_calls"),
            response({"role": "assistant", "content": "Finished."}, "stop"),
        ],
    )
    assert result["process"].returncode != 0
    assert list(tmp_path.glob("*.json")) == []
