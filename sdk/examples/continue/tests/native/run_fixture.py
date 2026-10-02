"""Exercise a standalone native CLI and retain exact model, hook and SDK traffic."""

import json
import os
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

APP = os.environ["SDK50_HARNESS"]
EVIDENCE = Path("/evidence")
WORKSPACE = Path("/tmp/native-workspace")
WORKSPACE.mkdir(mode=448)
(WORKSPACE / "fixture.txt").write_text("SDK50_FILE_CONTENT_MARKER\n")
assert str(Path.home()) == "/home/probe"
assert {name for _, name in socket.if_nameindex()} == {"lo"}
with socket.socket() as probe:
    probe.settimeout(1)
    try:
        probe.connect(("1.1.1.1", 443))
    except OSError:
        pass
    else:
        raise RuntimeError("External networking must be absent")
requests = []
provider_requests = []
flushed = threading.Event()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"data":[]}')

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if "/hooks/pre-tool-use" in self.path:
            requests.append(body)
            outputs = [
                {
                    "tool_use_id": item["tool_use_id"],
                    "decision": "deferred",
                    "judged_decision": "allow",
                    "decision_source": "rule",
                    "enforcement_mode": "observe",
                    "verdict": {"summary": "network-contained fixture"},
                    "latency_ms": 1,
                }
                for item in body["input"]
            ]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(outputs).encode())
            if not body["input"]:
                flushed.set()
            return
        provider_requests.append({"path": self.path, "body": body})
        has_result = any(message.get("role") == "tool" for message in body.get("messages", []))
        tool_defs = body.get("tools", [])
        should_call = bool(tool_defs) and (not has_result)
        message: dict[str, Any] = {"role": "assistant", "content": None if should_call else "sdk50 native completed"}
        calls = []
        if should_call:
            name = "Read"
            assert any(tool["function"]["name"] == name for tool in tool_defs), "Expected native file tool absent"
            args = {"filepath": str(WORKSPACE / "fixture.txt")}
            calls = [
                {
                    "id": "sdk50-native-call",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }
            ]
            message["tool_calls"] = calls
        finish = "tool_calls" if should_call else "stop"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream" if body.get("stream") else "application/json")
        self.end_headers()
        if body.get("stream"):
            delta = dict(message)
            if should_call:
                delta["tool_calls"] = [{"index": 0, **calls[0]}]
            chunks = [
                {
                    "id": "chatcmpl-fixture",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "gpt-4o",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                },
                {
                    "id": "chatcmpl-fixture",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "gpt-4o",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
            ]
            self.wfile.write(
                ("".join(("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)) + "data: [DONE]\n\n").encode()
            )
        else:
            self.wfile.write(
                json.dumps(
                    {
                        "id": "chatcmpl-fixture",
                        "object": "chat.completion",
                        "created": 1,
                        "model": "gpt-4o",
                        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    }
                ).encode()
            )


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_port}"
env = {
    **os.environ,
    "WATCHER_URL": url,
    "WATCHER_API_KEY": "fixture-only",
    "WATCHER_STATE_DIR": "/tmp/watcher-journal",
    "PWD": str(WORKSPACE),
    "PYTHONDONTWRITEBYTECODE": "1",
}
hooks = WORKSPACE / ".continue"
hooks.mkdir()
settings = json.loads(Path("/opt/fixture/hooks.example.json").read_text())
for groups in settings["hooks"].values():
    for group in groups:
        for hook in group["hooks"]:
            hook["command"] = "/usr/local/bin/python /opt/fixture/hook_entry.py"
(hooks / "settings.json").write_text(json.dumps(settings))
config = hooks / "config.yaml"
config.write_text(
    f"name: Fixture\nversion: 1.0.0\nschema: v1\nmodels:\n  - name: Fixture\n    provider: openai\n    model: gpt-4o\n    apiKey: fixture-only\n    apiBase: {url}/v1\n    roles: [chat]\n"
)
cli = "/opt/native/node_modules/.bin/cn"
command = [
    cli,
    "--config",
    str(config),
    "-p",
    "--format",
    "json",
    "Read fixture.txt with Read then say sdk50 native completed",
]
try:
    version = subprocess.run([cli, "--version"], cwd=WORKSPACE, env=env, text=True, capture_output=True, timeout=30)
    (EVIDENCE / "version.txt").write_text(version.stdout + version.stderr)
    result = subprocess.run(
        command, cwd=WORKSPACE, env=env, text=True, capture_output=True, stdin=subprocess.DEVNULL, timeout=120
    )
    flushed.wait(5)
    (EVIDENCE / "stdout.txt").write_text(result.stdout)
    (EVIDENCE / "stderr.txt").write_text(result.stderr)
    hook_path = EVIDENCE / "hook-inputs.jsonl"
    hook_count = len(hook_path.read_text().splitlines()) if hook_path.exists() else 0
    summary = {
        "returncode": result.returncode,
        "provider_requests": len(provider_requests),
        "watcher_requests": len(requests),
        "hook_deliveries": hook_count,
        "tool_ids": [item["tool_use_id"] for r in requests for item in r["input"]],
        "native_tool_ran": any(
            "SDK50_FILE_CONTENT_MARKER" in json.dumps(message.get("content"))
            for r in provider_requests
            for message in r["body"].get("messages", [])
            if message["role"] == "tool"
        ),
        "sdk_tool_result": any(
            "SDK50_FILE_CONTENT_MARKER" in json.dumps(message["content"])
            for r in requests
            for message in r["messages"]
            if message["role"] == "tool"
        ),
        "has_final": any("sdk50 native completed" in json.dumps(r["messages"][-1]["content"]) for r in requests),
        "egress_blocked": True,
        "interfaces": ["lo"],
    }
    (EVIDENCE / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
    assert result.returncode == 0 and summary["native_tool_ran"]
    assert summary["hook_deliveries"] == 0 and summary["watcher_requests"] == 0
    assert "sdk50 native completed" in result.stdout
finally:
    (EVIDENCE / "provider-requests.json").write_text(json.dumps(provider_requests, indent=2))
    (EVIDENCE / "sdk-requests.json").write_text(json.dumps(requests, indent=2))
    server.shutdown()
