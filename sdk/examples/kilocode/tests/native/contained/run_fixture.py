"""Run only Kilo's standalone CLI with container-local model and Watcher endpoints."""

import hashlib
import importlib.metadata
import json
import socket
import subprocess
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import distribution
from pathlib import Path
from typing import Any

EVIDENCE = Path("/evidence")
WORKSPACE = Path("/tmp/native-workspace")
WORKSPACE.mkdir(mode=0o700)
FILES = {"first.txt": "SDK50_KILO_FIRST_FILE", "second.txt": "SDK50_KILO_SECOND_FILE"}
for filename, content in FILES.items():
    (WORKSPACE / filename).write_text(content + "\n")
CALL_IDS = ["call00001", "call00002"]
FINAL = "sdk50 kilo completed"
SDK_REVISION = None
native_package = json.loads(Path("/opt/native/node_modules/@kilocode/cli/package.json").read_text())
assert native_package["version"] == "7.6.2"
sdk_distribution = distribution("watcher-sdk")
origin = json.loads(sdk_distribution.read_text("direct_url.json"))
assert origin["url"].endswith(f"/watcher_sdk-{importlib.metadata.version('watcher-sdk')}-py3-none-any.whl")
assert not origin.get("dir_info", {}).get("editable", False)
sdk_wheel = Path("/opt/fixture") / f"watcher_sdk-{importlib.metadata.version('watcher-sdk')}-py3-none-any.whl"
sdk_files_verified = 0
with zipfile.ZipFile(sdk_wheel) as package:
    for name in package.namelist():
        if not name.endswith("/") and name.startswith(("watcher_sdk/", "watcher_transcript_transport/")):
            assert sdk_distribution.locate_file(name).read_bytes() == package.read(name)
            sdk_files_verified += 1
assert sdk_files_verified > 0
assert Path.home() == Path("/home/probe")
assert {name for _, name in socket.if_nameindex()} == {"lo"}
assert not Path("/var/run/docker.sock").exists()
assert not Path("/home/probe/.aws").exists()
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.settimeout(1)
    try:
        probe.connect(("1.1.1.1", 443))
    except OSError:
        pass
    else:
        raise RuntimeError("External network route unexpectedly available")

sdk_requests = []
provider_requests = []
other_requests = []
protocol_errors = []
final_received = threading.Event()


class Handler(BaseHTTPRequestHandler):
    """Serve complete native Chat Completions and public SDK fixture responses."""

    def log_message(self, format: str, *args: object) -> None:
        pass

    def respond(self, data, *, status=200, headers=None):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        other_requests.append({"method": "GET", "path": self.path})
        if self.path == "/v1/models":
            self.respond({"data": [{"id": "fixture", "object": "model"}]})
        else:
            self.respond({"error": "fixture endpoint not found"}, status=404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.startswith("/v1/hooks/pre-tool-use"):
            sdk_requests.append(body)
            outcomes = [
                {
                    "tool_use_id": item["tool_use_id"],
                    "decision": "deferred",
                    "judged_decision": "allow",
                    "decision_source": "rule",
                    "enforcement_mode": "observe",
                    "verdict": {},
                    "latency_ms": 1,
                }
                for item in body["input"]
            ]
            self.respond(outcomes)
            if (
                body["input"] == []
                and body["messages"]
                and body["messages"][-1]["role"] == "assistant"
                and FINAL in json.dumps(body["messages"][-1]["content"])
            ):
                final_received.set()
            return
        if self.path != "/v1/chat/completions":
            other_requests.append({"method": "POST", "path": self.path, "body": body})
            self.respond({"error": "fixture endpoint not found"}, status=404)
            return
        provider_requests.append(body)
        try:
            tools = [entry["function"] for entry in body.get("tools", []) if entry.get("type") == "function"]
            results = [message for message in body["messages"] if message["role"] == "tool"]
            if tools and not results:
                selected = next(tool for tool in tools if tool["name"] in {"read_file", "read"})
                fields = selected["parameters"]["properties"]
                path_key = next(key for key in ("filePath", "file_path", "absolute_path", "path") if key in fields)
                calls = [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": selected["name"],
                            "arguments": json.dumps({path_key: str(WORKSPACE / filename)}),
                        },
                    }
                    for call_id, filename in zip(CALL_IDS, FILES, strict=True)
                ]
                message = {"role": "assistant", "content": None, "tool_calls": calls}
                finish = "tool_calls"
            else:
                if results:
                    assert {message["tool_call_id"] for message in results} >= set(CALL_IDS)
                    for marker in FILES.values():
                        assert any(marker in json.dumps(message["content"]) for message in results), marker
                message = {"role": "assistant", "content": FINAL}
                finish = "stop"
            assert len(provider_requests) <= 8, "Native run exceeded fixture request budget"
        except (AssertionError, KeyError, StopIteration) as error:
            protocol_errors.append(type(error).__name__ + ": " + str(error))
            self.respond(
                {"error": {"message": "Native request did not meet fixture contract", "type": "invalid_request_error"}},
                status=400,
            )
            return
        base = {"id": "chat-fixture", "object": "chat.completion", "created": 1, "model": "fixture"}
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        if not body.get("stream"):
            self.respond(
                {**base, "choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": usage}
            )
            return
        delta: dict[str, Any] = dict(message)
        if "tool_calls" in delta:
            delta["tool_calls"] = [{"index": index, **call} for index, call in enumerate(delta["tool_calls"])]
        chunks = [
            {
                **base,
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            },
            {
                **base,
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                "usage": usage,
            },
        ]
        payload = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload.encode())))
        self.end_headers()
        self.wfile.write(payload.encode())


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
url = f"http://127.0.0.1:{server.server_port}"
config = {
    "model": "fixture/fixture",
    "small_model": "fixture/fixture",
    "enabled_providers": ["fixture"],
    "provider": {
        "fixture": {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Contained fixture",
            "options": {"baseURL": url + "/v1", "apiKey": "fixture-only"},
            "models": {"fixture": {"name": "fixture", "tool_call": True, "limit": {"context": 65536, "output": 4096}}},
        }
    },
    "plugin": [
        "file:///opt/adapter/node_modules/watcher-kilocode-example/src/plugin.mjs",
        "file:///opt/fixture/capture_plugin.mjs",
    ],
    "permission": {"*": "deny", "read": "allow"},
}
config_path = WORKSPACE / "kilo.json"
config_path.write_text(json.dumps(config))
env = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": "/home/probe",
    "LANG": "C.UTF-8",
    "TERM": "dumb",
    "PYTHONDONTWRITEBYTECODE": "1",
    "WATCHER_URL": url,
    "WATCHER_API_KEY": "fixture-only",
    "WATCHER_PYTHON": "/opt/fixture/capture-python.sh",
    "KILO_CONFIG": str(config_path),
    "XDG_CONFIG_HOME": "/home/probe/.config",
    "XDG_DATA_HOME": "/home/probe/.local/share",
    "XDG_CACHE_HOME": "/home/probe/.cache",
    "XDG_STATE_HOME": "/home/probe/.local/state",
    "PWD": str(WORKSPACE),
    "NO_PROXY": "127.0.0.1,localhost",
}
command = [
    "/opt/native/node_modules/.bin/kilo",
    "run",
    "--model",
    "fixture/fixture",
    "--format",
    "json",
    "Read first.txt and second.txt with the read tool, then say sdk50 kilo completed.",
]
try:
    completed = subprocess.run(
        command,
        cwd=WORKSPACE,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=150,
        check=False,
    )
    (EVIDENCE / "stdout.txt").write_text(completed.stdout)
    (EVIDENCE / "stderr.txt").write_text(completed.stderr)
    final_received.wait(timeout=20)
    tool_path = EVIDENCE / "native-tool-events.jsonl"
    tools = [json.loads(line) for line in tool_path.read_text().splitlines()] if tool_path.exists() else []
    snapshots = [json.loads(path.read_text()) for path in EVIDENCE.glob("native-snapshot-*.json")]
    ids = [item["tool_use_id"] for request in sdk_requests for item in request["input"]]
    results = [message for request in sdk_requests for message in request["messages"] if message["role"] == "tool"]
    summary = {
        "native_package": "@kilocode/cli",
        "native_version": native_package["version"],
        "returncode": completed.returncode,
        "provider_request_count": len(provider_requests),
        "watcher_request_count": len(sdk_requests),
        "native_tool_event_count": len(tools),
        "native_plugin_snapshot_count": len(snapshots),
        "sdk_tool_ids": ids,
        "has_final_tail": final_received.is_set(),
        "protocol_errors": protocol_errors,
        "sdk_revision": SDK_REVISION,
        "sdk_noneditable": True,
        "sdk_files_verified": sdk_files_verified,
        "sdk_wheel_sha256": hashlib.sha256(sdk_wheel.read_bytes()).hexdigest(),
        "command": command,
        "provider_base_url": url + "/v1",
        "interfaces": ["lo"],
        "external_route": False,
        "native_environment_keys": sorted(env),
        "home": str(Path.home()),
    }
    (EVIDENCE / "summary.json").write_text(json.dumps(summary, indent=2))
    sys.stdout.write(json.dumps(summary) + "\n")
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert len(provider_requests) >= 2 and not protocol_errors
    assert set(ids) == set(CALL_IDS) and len(tools) >= 2 and snapshots
    assert final_received.is_set()
    for call_id, marker in zip(CALL_IDS, FILES.values(), strict=True):
        assert any(event["input"]["callID"] == call_id and marker in event["output"]["output"] for event in tools)
        assert any(
            message["tool_call_id"] == call_id and marker in json.dumps(message["content"]) for message in results
        )
finally:
    (EVIDENCE / "provider-requests.json").write_text(json.dumps(provider_requests, indent=2))
    (EVIDENCE / "sdk-requests.json").write_text(json.dumps(sdk_requests, indent=2))
    (EVIDENCE / "other-requests.json").write_text(json.dumps(other_requests, indent=2))
    (EVIDENCE / "protocol-errors.json").write_text(json.dumps(protocol_errors, indent=2))
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
