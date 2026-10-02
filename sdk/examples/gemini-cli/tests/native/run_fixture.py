"""Exercise one native CLI with loopback-only model and Watcher fixture endpoints."""

import json
import os
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP = os.environ["SDK50_HARNESS"]
EVIDENCE = Path("/evidence")
WORKSPACE = Path("/tmp/native-workspace")
WORKSPACE.mkdir(mode=0o700)
if APP == "gemini-cli":
    (WORKSPACE / "fixture.txt").write_text("SDK50_FILE_CONTENT_MARKER\n")
assert {name for _, name in socket.if_nameindex()} == {"lo"}, "Runtime must use --network none"
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.settimeout(1)
    try:
        probe.connect(("1.1.1.1", 443))
    except OSError:
        pass
    else:
        raise RuntimeError("External TCP egress unexpectedly succeeded")

requests = []
provider_requests = []


def response_item_events(item, response_id):
    """Produce the public Responses streaming protocol, including finalized output."""
    response = {
        "id": response_id,
        "object": "response",
        "created_at": 1,
        "model": "fixture",
        "status": "in_progress",
        "output": [],
    }
    events = [{"type": "response.created", "response": response}]
    start = dict(item)
    if item["type"] == "function_call":
        start["arguments"] = ""
    else:
        start["content"] = []
    events.append({"type": "response.output_item.added", "output_index": 0, "item": start})
    if item["type"] == "function_call":
        events.append(
            {
                "type": "response.function_call_arguments.delta",
                "item_id": item["id"],
                "output_index": 0,
                "delta": item["arguments"],
            }
        )
        events.append(
            {
                "type": "response.function_call_arguments.done",
                "item_id": item["id"],
                "output_index": 0,
                "arguments": item["arguments"],
            }
        )
    else:
        events.append(
            {
                "type": "response.content_part.added",
                "item_id": item["id"],
                "output_index": 0,
                "content_index": 0,
                "part": {"type": "output_text", "text": "", "annotations": []},
            }
        )
        events.append(
            {
                "type": "response.output_text.delta",
                "item_id": item["id"],
                "output_index": 0,
                "content_index": 0,
                "delta": item["content"][0]["text"],
            }
        )
        events.append(
            {
                "type": "response.output_text.done",
                "item_id": item["id"],
                "output_index": 0,
                "content_index": 0,
                "text": item["content"][0]["text"],
            }
        )
    events.append({"type": "response.output_item.done", "output_index": 0, "item": item})
    events.append(
        {
            "type": "response.completed",
            "response": {
                **response,
                "status": "completed",
                "output": [item],
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            },
        }
    )
    return events


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        self.send_json({"data": []})

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
                    "verdict": {"summary": "network-isolated fixture"},
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
        if APP == "gemini-cli":
            if "countTokens" in self.path:
                self.send_json({"totalTokens": 10})
                return
            has_result = any(
                "functionResponse" in part for message in body.get("contents", []) for part in message.get("parts", [])
            )
            advertised = [tool for group in body.get("tools", []) for tool in group.get("functionDeclarations", [])]
            if not has_result and body.get("tools"):
                assert any(tool["name"] == "read_file" for tool in advertised), (
                    "Native read_file tool must be advertised"
                )
            part = (
                {
                    "functionCall": {
                        "id": "sdk50-native-call",
                        "name": "read_file",
                        "args": {"file_path": str(WORKSPACE / "fixture.txt")},
                    }
                }
                if body.get("tools") and not has_result
                else {"text": "sdk50 native completed"}
            )
            result = {
                "candidates": [{"content": {"role": "model", "parts": [part]}, "finishReason": "STOP", "index": 0}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 15},
                "modelVersion": "gemini-2.5-flash",
            }
            if "streamGenerateContent" in self.path:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(("data: " + json.dumps(result) + "\n\n").encode())
            else:
                self.send_json(result)
            return

        has_result = any(item.get("type") == "function_call_output" for item in body.get("input", []))
        if not has_result:
            advertised = []
            for tool in body.get("tools", []):
                if tool["type"] == "namespace":
                    advertised.extend([{**child, "namespace": tool["name"]} for child in tool["tools"]])
                else:
                    advertised.append(tool)
            chosen = next(
                (tool for tool in advertised if tool.get("name") in {"exec_command", "shell_command", "shell"}), None
            )
            if chosen is None:
                raise ValueError("No supported native shell tool was advertised")
            name = chosen["name"]
            args = (
                {"cmd": "pwd"}
                if name == "exec_command"
                else {"command": "pwd" if name == "shell_command" else ["/bin/sh", "-lc", "pwd"]}
            )
            item = {
                "id": "fc_fixture",
                "type": "function_call",
                "call_id": "sdk50-native-call",
                "name": name,
                "arguments": json.dumps(args),
                "status": "completed",
            }
            if chosen.get("namespace"):
                item["namespace"] = chosen["namespace"]
        else:
            item = {
                "id": "msg_fixture",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "sdk50 native completed", "annotations": []}],
            }
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for event in response_item_events(item, "resp_final" if has_result else "resp_call"):
            self.wfile.write(("event: " + event["type"] + "\ndata: " + json.dumps(event) + "\n\n").encode())


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_port}"
env = {
    **os.environ,
    "WATCHER_URL": url,
    "WATCHER_API_KEY": "fixture-only",
    "SDK50_PROVIDER_KEY": "fixture-only",
    "PWD": str(WORKSPACE),
    "PYTHONDONTWRITEBYTECODE": "1",
}
home = Path.home()
assert str(home) == "/home/probe", "Only the empty container-owned home may be used"
if APP == "codex":
    config = home / ".codex"
    config.mkdir()
    (config / "config.toml").write_text(f'''model = "fixture"
model_provider = "fixture"
[model_providers.fixture]
name = "Loopback fixture"
base_url = "{url}/v1"
wire_api = "responses"
env_key = "SDK50_PROVIDER_KEY"
requires_openai_auth = false
request_max_retries = 0
stream_max_retries = 0
''')
    command = [
        "/opt/native/node_modules/.bin/codex",
        "--enable",
        "use_legacy_landlock",
        "exec",
        "--skip-git-repo-check",
        "--json",
        "--sandbox",
        "read-only",
        "--model",
        "fixture",
        "Run pwd and then say sdk50 native completed",
    ]
else:
    config = home / ".gemini"
    config.mkdir()
    settings = json.loads(Path("/opt/fixture/hooks.example.json").read_text())
    settings["security"] = {"auth": {"selectedType": "gemini-api-key"}}
    settings["hooksConfig"] = {"enabled": True}
    settings["hooks"]["AfterAgent"][0]["hooks"][0]["command"] = "python /opt/fixture/hook_entry.py"
    (config / "settings.json").write_text(json.dumps(settings))
    (config / "trustedFolders.json").write_text(json.dumps({str(WORKSPACE): "TRUST_FOLDER"}))
    env["GEMINI_API_KEY"] = "fixture-only"
    env["GOOGLE_GEMINI_BASE_URL"] = url
    command = [
        "/opt/native/node_modules/.bin/gemini",
        "--prompt",
        "Read fixture.txt with read_file and then say sdk50 native completed",
        "--model",
        "gemini-2.5-flash",
        "--output-format",
        "json",
    ]

try:
    result = subprocess.run(
        command, cwd=WORKSPACE, env=env, stdin=subprocess.DEVNULL, text=True, capture_output=True, timeout=120
    )
    (EVIDENCE / "stdout.txt").write_text(result.stdout)
    (EVIDENCE / "stderr.txt").write_text(result.stderr)
    summary = {
        "returncode": result.returncode,
        "provider_requests": len(provider_requests),
        "watcher_requests": len(requests),
        "tool_ids": [i["tool_use_id"] for r in requests for i in r["input"]],
        "native_tool_ran": any(
            ("SDK50_FILE_CONTENT_MARKER" if APP == "gemini-cli" else str(WORKSPACE)) in json.dumps(m["content"])
            for r in requests
            for m in r["messages"]
            if m["role"] == "tool"
        ),
        "has_final": any("sdk50 native completed" in json.dumps(r["messages"][-1]["content"]) for r in requests),
        "egress_blocked": True,
        "interfaces": ["lo"],
    }
    (EVIDENCE / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
    assert result.returncode == 0 and summary["provider_requests"] >= 2
    assert summary["tool_ids"] and summary["native_tool_ran"] and summary["has_final"]
finally:
    (EVIDENCE / "provider-requests.json").write_text(json.dumps(provider_requests, indent=2))
    (EVIDENCE / "sdk-requests.json").write_text(json.dumps(requests, indent=2))
    server.shutdown()
