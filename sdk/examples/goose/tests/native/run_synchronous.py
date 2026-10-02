"""Exercise native Goose Stop/export dispatch against network-contained fixtures."""

import json
import os
import shutil
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from sync_support import (
    SCENARIO,
    expects_execution,
    forward,
    respond,
    verify_native_reads,
    verify_pending,
    verify_sdk_wheel,
    watch_native_reads,
    watch_pending,
)

EVIDENCE = Path("/evidence")
WORKSPACE = Path("/tmp/native-workspace")
WORKSPACE.mkdir(mode=0o700)
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

verify_sdk_wheel()

requests = []
provider_requests = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"data": []}')

    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        body = json.loads(raw)
        if "/hooks/pre-tool-use" in self.path and os.environ.get("WATCHER_EXAMPLE_FORWARD_URL"):
            requests.append(body)
            assert forward(self, body, raw=raw)
            return
        if "/hooks/pre-tool-use" in self.path and body["input"] and "settings_overrides" not in body:
            requests.append(body)
            respond(self, body)
            return
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
            return
        provider_requests.append({"path": self.path, "body": body})
        has_result = any(message.get("role") == "tool" for message in body.get("messages", []))
        tools = body.get("tools", [])
        should_call = bool(tools) and not has_result
        message: dict[str, Any] = {"role": "assistant", "content": None if should_call else "sdk50 native completed"}
        tool_calls = []
        if should_call:
            tool = next(tool["function"] for tool in tools if tool["function"]["name"] == "shell")
            tool_calls = [
                {
                    "id": "sdk50-native-call",
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "arguments": json.dumps({"command": "cat /tmp/native-workspace/fixture.txt"}),
                    },
                }
            ]
            message["tool_calls"] = tool_calls
        finish = "tool_calls" if should_call else "stop"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream" if body.get("stream") else "application/json")
        self.end_headers()
        if body.get("stream"):
            delta = dict(message)
            if should_call:
                delta["tool_calls"] = [{"index": 0, **tool_calls[0]}]
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
                ("".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n").encode()
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
plugin = WORKSPACE / ".agents/plugins/watcher-example"
(plugin / "hooks").mkdir(parents=True)
shutil.copyfile("/opt/fixture/plugin.json", plugin / "plugin.json")
hooks = json.loads(Path("/opt/fixture/hooks.json").read_text())
hooks["hooks"]["Stop"][0]["hooks"][0]["command"] = "/usr/local/bin/python /opt/fixture/hook_entry.py --record-only"
hooks["hooks"]["PreToolUse"] = [
    {
        "hooks": [
            {"type": "command", "command": "python -m watcher_goose.pre_tool", "timeout": 480, "on_failure": "block"}
        ]
    }
]
(plugin / "hooks/hooks.json").write_text(json.dumps(hooks))
env = {
    **os.environ,
    "OPENAI_BASE_URL": url + "/v1",
    "OPENAI_API_KEY": "fixture-only",
    "GOOSE_PROVIDER": "openai",
    "GOOSE_MODEL": "gpt-4o",
    "WATCHER_URL": url,
    "WATCHER_TIMEOUT_SECONDS": "1" if SCENARIO == "timeout" else "420",
    "WATCHER_API_KEY": "fixture-only",
    "PWD": str(WORKSPACE),
    "PYTHONDONTWRITEBYTECODE": "1",
}
(WORKSPACE / "fixture.txt").write_text(str(WORKSPACE) + "\n")
watch_native_reads([WORKSPACE / "fixture.txt"])
watch_pending(provider_requests)
try:
    version = subprocess.run(["goose", "--version"], text=True, capture_output=True, check=True)
    (EVIDENCE / "version.txt").write_text(version.stdout)
    result = subprocess.run(
        [
            "goose",
            "run",
            "--text",
            "Run pwd then say sdk50 native completed",
            "--with-builtin",
            "developer",
            "--max-turns",
            "3",
            "--output-format",
            "json",
        ],
        cwd=WORKSPACE,
        env=env,
        text=True,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )
    (EVIDENCE / "stdout.txt").write_text(result.stdout)
    (EVIDENCE / "stderr.txt").write_text(result.stderr)
    exported = json.loads((EVIDENCE / "native-export.json").read_text())
    summary = {
        "returncode": result.returncode,
        "provider_requests": len(provider_requests),
        "watcher_requests": len(requests),
        "tool_ids": [i["tool_use_id"] for r in requests for i in r["input"]],
        "native_tool_ran": any(
            "error" not in m and any(part["text"] == str(WORKSPACE) for part in m["content"])
            for r in requests
            for m in r["messages"]
            if m["role"] == "tool"
        )
        and any(
            block["toolResult"]["value"]["structuredContent"]["exit_code"] == 0
            and block["toolResult"]["value"]["structuredContent"]["stdout"] == str(WORKSPACE)
            for message in exported["conversation"]
            for block in message["content"]
            if block["type"] == "toolResponse" and block["id"] == "sdk50-native-call"
        ),
        "has_final": any("sdk50 native completed" in json.dumps(r["messages"][-1]["content"]) for r in requests),
        "egress_blocked": True,
        "interfaces": ["lo"],
    }
    verify_pending()
    verify_native_reads()
    (EVIDENCE / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
    assert result.returncode == 0 and summary["provider_requests"] >= 2
    assert summary["tool_ids"] and summary["has_final"]
    assert summary["native_tool_ran"] == expects_execution()
    assert any(r["input"] and "settings_overrides" not in r for r in requests)
finally:
    (EVIDENCE / "provider-requests.json").write_text(json.dumps(provider_requests, indent=2))
    (EVIDENCE / "sdk-requests.json").write_text(json.dumps(requests, indent=2))
    server.shutdown()


if SCENARIO == "allow" and not os.environ.get("WATCHER_EXAMPLE_FORWARD_URL"):
    contract = subprocess.run(
        [
            "python",
            "-m",
            "pytest",
            "--noconftest",
            "-c",
            "pyproject.toml",
            "-q",
            "--junitxml=/evidence/contract-tests.xml",
            "-p",
            "no:cacheprovider",
            "/opt/fixture/tests/test_enforcement.py",
        ],
        cwd="/opt/fixture",
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    Path("/evidence/contract-tests.stdout").write_text(contract.stdout)
    Path("/evidence/contract-tests.stderr").write_text(contract.stderr)
    Path("/evidence/contract-tests.exit").write_text(str(contract.returncode))
    assert contract.returncode == 0, "SDK contract regressions failed; inspect captured output"
