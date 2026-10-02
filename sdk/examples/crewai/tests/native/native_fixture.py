"""Run native CrewAI tools between contained HTTP model and Watcher fixtures.

run_fixture.py validates the network boundary before this process starts. The
fixture records actual model requests, native callbacks, tool invocations and
SDK HTTP bodies separately, then checks their identities and historical order.
"""

import asyncio
import hashlib
import json
import threading
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import distribution, version
from pathlib import Path

import httpx
from crewai.llms.base_llm import BaseLLM
from demo.observe import run_conversation
from watcher_crewai.adapter import IncompleteObservationError, WatcherTrace, messages_for_watcher, observe

from watcher_sdk import AsyncWatcherClient

EVIDENCE = Path("/evidence")
MODEL_RESPONSES = [
    'Thought: Double two\nAction: double\nAction Input: {"value": 2}',
    'Thought: Double three\nAction: double\nAction Input: {"value": 3}',
    "Thought: Finished\nFinal Answer: 4 and 6",
]


class EvidenceTrace(WatcherTrace):
    """Retain the native callback payload alongside the application transcript."""

    def __init__(self):
        super().__init__("Double 2 and 3")
        self.callbacks = []

    def on_step(self, step):
        self.callbacks.append(
            {"type": type(step).__name__, "data": asdict(step) if is_dataclass(step) else step.model_dump()}
        )
        super().on_step(step)


class LoopbackModel(BaseLLM):
    """Use CrewAI's public custom-LLM interface with the local HTTP text fixture."""

    def __init__(self, url):
        super().__init__(model="contained-text-fixture")
        self.url = url

    def call(self, messages, *args, **kwargs):
        with httpx.Client(timeout=10, trust_env=False) as client:
            response = client.post(self.url + "/model", json={"messages": messages, "stop": self.stop})
            response.raise_for_status()
            return response.json()["text"]


class Fixture:
    """Keep HTTP receipts and scenario state outside the adapter under test."""

    def __init__(self):
        self.model_requests = []
        self.sdk_requests = []
        self.unexpected_requests = []

    def handler(self):
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            """Serve synthetic text responses and completed observe receipts on loopback."""

            def log_message(self, format, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                capture = {"path": self.path, "body": body}
                headers = {}
                status = 200
                if self.path == "/model":
                    response = {"text": MODEL_RESPONSES[len(fixture.model_requests)]}
                    fixture.model_requests.append(capture)
                elif self.path == "/v1/hooks/pre-tool-use":
                    fixture.sdk_requests.append(capture)
                    assert "require_recording" not in self.path
                    response = [
                        {
                            "decision": "deferred",
                            "judged_decision": "allow",
                            "decision_source": "rule",
                            "enforcement_mode": "observe",
                            "tool_use_id": call["tool_use_id"],
                            "verdict": {"explanation": "Contained synthetic observation"},
                            "latency_ms": 1,
                        }
                        for call in body["input"] or []
                    ]
                    if body["external_ids"]["other"] == "crewai:missing-outcomes":
                        response = []
                else:
                    fixture.unexpected_requests.append(capture)
                    response = {"detail": "Unknown fixture endpoint"}
                    status = 404
                capture["response"] = response
                capture["response_headers"] = headers
                payload = json.dumps(response).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(payload)

        return Handler


async def exercise(fixture, url, trace, executions):
    """Compare actual tools and native prompts with successive SDK wire snapshots."""
    history = await run_conversation(LoopbackModel(url), trace=trace, executions=executions)
    before = deepcopy(history)
    transcript = messages_for_watcher(history)
    assert executions == [
        {"tool": "double", "arguments": {"value": 2}, "result": "4"},
        {"tool": "double", "arguments": {"value": 3}, "result": "6"},
    ]
    assert len(fixture.model_requests) == 3
    assert [event["type"] for event in trace.callbacks] == [
        "ToolResult",
        "AgentAction",
        "ToolResult",
        "AgentAction",
        "AgentFinish",
    ]
    assert transcript[0] == {"role": "user", "content": "Double 2 and 3"}
    assert transcript[-1] == {"role": "assistant", "content": "4 and 6"}
    calls = [call for message in transcript for call in message.get("tool_calls", [])]
    assert len(calls) == 2 and len({call["id"] for call in calls}) == 2
    assert [{"tool": call["function"], "arguments": call["arguments"]} for call in calls] == [
        {"tool": operation["tool"], "arguments": operation["arguments"]} for operation in executions
    ]
    results = [message for message in transcript if message["role"] == "tool"]
    assert [message["tool_call_id"] for message in results] == [call["id"] for call in calls]
    assert [message["content"] for message in results] == [operation["result"] for operation in executions]
    for request in fixture.model_requests:
        assert request["body"]["stop"], "Executor stop words did not reach the model"
        for message in request["body"]["messages"]:
            assert message in history, "Actual model request context is missing from captured history"
    assert any("calculator" in item["content"] for item in history if item["role"] == "system")
    assert any("Observation: 4" in item["content"] for item in fixture.model_requests[1]["body"]["messages"])
    assert any("Observation: 6" in item["content"] for item in fixture.model_requests[2]["body"]["messages"])
    async with AsyncWatcherClient(url, api_key="fixture-only", max_retries=0) as client:
        await observe(client, "contained", history[:-1])
        outcomes = await observe(client, "contained", history)
        try:
            await observe(client, "missing-outcomes", history)
        except IncompleteObservationError:
            pass
        else:
            raise AssertionError("Missing call outcomes were accepted")
    assert history == before
    assert len(executions) == 2 and len(fixture.model_requests) == 3, "Monitoring re-executed native work"
    assert [outcome.judged_decision for outcome in outcomes] == ["allow", "allow"]
    sent = [
        request["body"]
        for request in fixture.sdk_requests
        if request["body"]["external_ids"] == {"other": "crewai:contained"}
    ]
    assert len(sent) == 6
    evaluations = [body for body in sent if body["input"] is not None]
    assert [body["input"][0]["tool_use_id"] for body in evaluations] == [call["id"] for call in calls] * 2
    call_indexes = [index for index, message in enumerate(transcript) if message.get("tool_calls")]
    for round_start in (0, 3):
        for offset, index in enumerate(call_indexes):
            assert sent[round_start + offset]["messages"] == transcript[: index + 1]
            assert "settings_overrides" not in sent[round_start + offset]
    assert sent[2]["input"] is None and sent[2]["messages"] == transcript[:-1]
    assert sent[5]["input"] is None and sent[5]["messages"] == transcript
    failures = [
        request["body"]
        for request in fixture.sdk_requests
        if request["body"]["external_ids"] == {"other": "crewai:missing-outcomes"}
    ]
    assert len(failures) == 2 and failures[-1]["input"] is None and failures[-1]["messages"] == transcript
    assert not fixture.unexpected_requests
    return {
        "native_package": "crewai",
        "native_version": version("crewai"),
        "model_requests": 3,
        "native_tool_executions": len(executions),
        "native_callback_types": [event["type"] for event in trace.callbacks],
        "sdk_requests": len(fixture.sdk_requests),
        "application_tool_ids": [call["id"] for call in calls],
        "stable_snapshot_ids": True,
        "historical_prefixes_verified": True,
        "final_text_and_results_recorded": True,
        "missing_outcomes_raise_without_tool_reexecution": True,
    }


def main():
    fixture = Fixture()
    trace = EvidenceTrace()
    executions = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), fixture.handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        summary = asyncio.run(exercise(fixture, f"http://127.0.0.1:{server.server_port}", trace, executions))
        package = distribution("crewai")
        sources = [
            "crewai/agents/parser.py",
            "crewai/agents/crew_agent_executor.py",
            "crewai/llms/base_llm.py",
            "crewai/utilities/agent_utils.py",
            "crewai/tools/tool_usage.py",
        ]
        summary["native_sources"] = {
            name: hashlib.sha256(Path(str(package.locate_file(name))).read_bytes()).hexdigest() for name in sources
        }
        (EVIDENCE / "native-summary.json").write_text(json.dumps(summary, indent=2))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        for name, data in [
            ("model-requests", fixture.model_requests),
            ("sdk-requests", fixture.sdk_requests),
            ("native-callbacks", trace.callbacks),
            ("native-tool-executions", executions),
            ("captured-history", trace.messages),
            ("unexpected-requests", fixture.unexpected_requests),
        ]:
            (EVIDENCE / f"{name}.json").write_text(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
