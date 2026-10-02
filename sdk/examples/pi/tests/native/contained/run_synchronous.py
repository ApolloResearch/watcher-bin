"""Run contained Pi against a deterministic loopback model and SDK capture."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from sync_support import SCENARIO, expects_execution, forward, respond, verify_pending, verify_sdk_wheel, watch_pending

assert str(Path.home()) == "/home/probe", "Run this probe with run-contained.sh"
assert {name for _, name in socket.if_nameindex()} == {"lo"}, "External networking must be absent"
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.settimeout(1)
    try:
        probe.connect(("1.1.1.1", 443))
    except OSError:
        pass
    else:
        raise RuntimeError("External TCP egress unexpectedly succeeded")
evidence = Path("/evidence")

slug = "pi"
if (Path.home() / ".pi").exists() or os.environ.get("PI_CODING_AGENT_DIR"):
    raise RuntimeError(
        "Preserve the existing Pi configuration in a dedicated test setup before running this isolated probe"
    )
root = Path(tempfile.mkdtemp(prefix="sdk50-native-" + slug + "-"))
root.chmod(0o700)
verify_sdk_wheel()

requests = []
provider_requests = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

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
                    "tool_use_id": i["tool_use_id"],
                    "decision": "deferred",
                    "judged_decision": "allow",
                    "decision_source": "rule",
                    "enforcement_mode": "observe",
                    "verdict": {"summary": "fixture"},
                    "latency_ms": 1,
                }
                for i in body["input"]
            ]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(outputs).encode())
            return
        provider_requests.append({"path": self.path, "body": body})
        has_result = any(m.get("role") == "tool" for m in body.get("messages", []))
        should_call = bool(body.get("tools")) and not has_result
        args = {"command": "pwd; printf native-write > /tmp/pi-execution-marker"}
        call = {
            "id": "sdk50-native-call",
            "type": "function",
            "function": {"name": "bash", "arguments": json.dumps(args)},
        }
        message: dict[str, Any] = {"role": "assistant", "content": None if should_call else "sdk50 native completed"}
        if should_call:
            message["tool_calls"] = [call]
        finish = "tool_calls" if should_call else "stop"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream" if body.get("stream") else "application/json")
        self.end_headers()
        if body.get("stream"):
            delta = dict(message)
            if should_call:
                delta["tool_calls"] = [{"index": 0, **call}]
            chunks = [
                {
                    "id": "chatcmpl-fixture",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "fixture",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                },
                {
                    "id": "chatcmpl-fixture",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "fixture",
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
                        "model": "fixture",
                        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    }
                ).encode()
            )


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_port}"
example = Path(__file__).parent
env = {
    **os.environ,
    "WATCHER_URL": url,
    "WATCHER_TIMEOUT_SECONDS": "1" if SCENARIO == "timeout" else "420",
    "WATCHER_API_KEY": "fixture",
    "WATCHER_PYTHON": sys.executable,
    "PYTHONDONTWRITEBYTECODE": "1",
    "PWD": str(root),
}
agent_dir = root / "agent"
agent_dir.mkdir()
(agent_dir / "models.json").write_text(
    json.dumps(
        {
            "providers": {
                "sdk50-fixture": {
                    "baseUrl": url + "/v1",
                    "api": "openai-completions",
                    "apiKey": "fixture",
                    "models": [{"id": "fixture"}],
                }
            }
        }
    )
)
env["PI_CODING_AGENT_DIR"] = str(agent_dir)
command = [
    "/opt/native/node_modules/.bin/pi",
    "-p",
    "--mode",
    "json",
    "--provider",
    "sdk50-fixture",
    "--model",
    "fixture",
    "--session",
    str(root / "session.jsonl"),
    "-e",
    "/opt/adapter/node_modules/watcher-pi-example/src/plugin.enforce.mjs",
    "Run pwd and then say sdk50 native completed",
]
watch_pending(provider_requests, "/tmp/pi-execution-marker")
try:
    result = subprocess.run(
        command, cwd=root, env=env, stdin=subprocess.DEVNULL, text=True, capture_output=True, timeout=100
    )
    (evidence / "stdout.txt").write_text(result.stdout)
    (evidence / "native-session.jsonl").write_bytes((root / "session.jsonl").read_bytes())
    (evidence / "stderr.txt").write_text(result.stderr)
    (evidence / "sdk-requests.json").write_text(json.dumps(requests, indent=2))
    summary = {
        "root": str(root),
        "returncode": result.returncode,
        "provider_requests": len(provider_requests),
        "watcher_requests": len(requests),
        "observed_tool_ids": [i["tool_use_id"] for r in requests for i in r["input"]],
        "has_final": any("sdk50 native completed" in json.dumps(r.get("messages", [])) for r in requests),
        "native_tool_ran": any(
            "error" not in m and any(block["text"] == str(root) + "\n" for block in m["content"])
            for r in requests
            for m in r["messages"]
            if m["role"] == "tool"
        ),
    }
    summary["native_file_written"] = Path("/tmp/pi-execution-marker").exists()
    assert summary["native_file_written"] == expects_execution()
    summary["egress_blocked"] = True
    summary["interfaces"] = ["lo"]
    verify_pending()
    (evidence / "summary.json").write_text(json.dumps(summary, indent=2))
    (evidence / "provider-requests.json").write_text(json.dumps(provider_requests, indent=2))
    print(json.dumps(summary))
    assert result.returncode == 0 and len(provider_requests) >= 2
    assert summary["observed_tool_ids"] and summary["has_final"]
    assert summary["native_tool_ran"] == expects_execution()
    assert any(r["input"] and "settings_overrides" not in r for r in requests)
finally:
    server.shutdown()
