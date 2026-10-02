"""Drive a pinned native CLI against container-local provider and Watcher fixtures.

The image supplies code/dependencies; runtime owns an empty home, fresh workspace,
and only a writable evidence directory. No host authentication or projects enter.
"""

import hashlib
import importlib.metadata
import json
import os
import socket
import subprocess
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import distribution
from pathlib import Path
from typing import Any

APP = os.environ["SDK50_HARNESS"]
EVIDENCE = Path("/evidence")
WORKSPACE = Path("/tmp/native-workspace")
WORKSPACE.mkdir(mode=0o700)
FILES = {"first.txt": "SDK50_NATIVE_FIRST_FILE", "second.txt": "SDK50_NATIVE_SECOND_FILE"}
for filename, content in FILES.items():
    (WORKSPACE / filename).write_text(content + "\n")
CALL_IDS = ["call00001", "call00002"]
FINAL = "sdk50 native completed"
SDK_REVISION = None
sdk_distribution = distribution("watcher-sdk")
sdk_origin = json.loads(sdk_distribution.read_text("direct_url.json"))
assert sdk_origin["url"].endswith(f"/watcher_sdk-{importlib.metadata.version('watcher-sdk')}-py3-none-any.whl")
assert not sdk_origin.get("dir_info", {}).get("editable", False)
sdk_wheel = Path("/opt/fixture") / f"watcher_sdk-{importlib.metadata.version('watcher-sdk')}-py3-none-any.whl"
sdk_files_verified = 0
with zipfile.ZipFile(sdk_wheel) as package:
    for filename in package.namelist():
        if not filename.endswith("/") and filename.startswith(("watcher_sdk/", "watcher_transcript_transport/")):
            assert sdk_distribution.locate_file(filename).read_bytes() == package.read(filename)
            sdk_files_verified += 1
assert sdk_files_verified > 0
if APP == "qwen-code":
    native_version = json.loads(Path("/opt/native/node_modules/@qwen-code/qwen-code/package.json").read_text())[
        "version"
    ]
    assert native_version == "0.23.4"
else:
    (native_metadata,) = Path("/opt/native/lib/python3.12/site-packages").glob("mistral_vibe-*.dist-info/METADATA")
    native_version = next(
        line.removeprefix("Version: ")
        for line in native_metadata.read_text().splitlines()
        if line.startswith("Version: ")
    )
    assert native_version == "2.25.4"


assert Path.home() == Path("/home/probe")
assert {name for _, name in socket.if_nameindex()} == {"lo"}
assert not Path("/var/run/docker.sock").exists()
assert not Path("/home/probe/.aws").exists()
assert not Path("/home/probe/.codex").exists()
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
                path_key = next(key for key in ("file_path", "absolute_path", "path") if key in fields)
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
env = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": "/home/probe",
    "LANG": "C.UTF-8",
    "TERM": "dumb",
    "PYTHONDONTWRITEBYTECODE": "1",
    "WATCHER_URL": url,
    "WATCHER_API_KEY": "fixture-only",
    "SDK50_PROVIDER_KEY": "fixture-only",
    "PWD": str(WORKSPACE),
    "NO_PROXY": "127.0.0.1,localhost",
}
hook_command = sys.executable + " /opt/fixture/hook_entry.py"
capture_command = sys.executable + " /opt/fixture/capture_tool.py"
prompt = "Read first.txt and second.txt using the file-reading tool, then say sdk50 native completed."
if APP == "qwen-code":
    config = Path.home() / ".qwen"
    config.mkdir()
    settings = json.loads(Path("/opt/fixture/hooks.example.json").read_text())
    settings["hooks"]["Stop"][0]["hooks"][0]["command"] = hook_command
    settings["hooks"]["PostToolUse"] = [{"hooks": [{"type": "command", "command": capture_command, "timeout": 15}]}]
    settings["security"] = {"auth": {"selectedType": "openai"}}
    (config / "settings.json").write_text(json.dumps(settings))
    env.update(
        {
            "QWEN_HOME": str(config),
            "QWEN_RUNTIME_DIR": str(config),
            "OPENAI_API_KEY": "fixture-only",
            "OPENAI_BASE_URL": url + "/v1",
            "OPENAI_MODEL": "fixture",
            "QWEN_MODEL": "fixture",
        }
    )
    command = [
        "/opt/native/node_modules/.bin/qwen",
        "--prompt",
        prompt,
        "--auth-type",
        "openai",
        "--model",
        "fixture",
        "--openai-base-url",
        url + "/v1",
        "--openai-api-key",
        "fixture-only",
        "--output-format",
        "stream-json",
    ]
elif APP == "mistral-vibe":
    config = Path.home() / ".vibe"
    config.mkdir()
    (config / "config.toml").write_text(f'''active_model = "fixture"
default_agent = "plan"
[[models]]
name = "fixture"
provider = "fixture"
alias = "fixture"
[[providers]]
name = "fixture"
api_base = "{url}/v1"
api_key_env_var = "SDK50_PROVIDER_KEY"
backend = "generic"
api_style = "openai"
''')
    project = WORKSPACE / ".vibe"
    project.mkdir()
    hooks = Path("/opt/fixture/hooks.example.toml").read_text()
    original = 'command = "__WATCHER_PYTHON__ -m watcher_qwen_code.integration"'
    assert hooks.count(original) == 1
    hooks = hooks.replace(original, "command = " + json.dumps(hook_command))
    hooks += f'''\n[[hooks]]
name = "native-execution-evidence"
type = "post_tool"
command = "{capture_command}"
timeout = 15
'''
    (project / "hooks.toml").write_text(hooks)
    (config / "trusted_folders.toml").write_text(f'trusted = ["{WORKSPACE}"]\nuntrusted = []\n')
    env["VIBE_HOME"] = str(config)
    command = ["/opt/native/bin/vibe", "--prompt", prompt, "--agent", "plan", "--max-turns", "4", "--output", "json"]
else:
    raise ValueError("Unsupported harness")

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
    post_tool_path = EVIDENCE / "post-tool-events.jsonl"
    post_tools = (
        [json.loads(line) for line in post_tool_path.read_text().splitlines()] if post_tool_path.exists() else []
    )
    ids = [item["tool_use_id"] for request in sdk_requests for item in request["input"]]
    results = [message for request in sdk_requests for message in request["messages"] if message["role"] == "tool"]
    summary = {
        "harness": APP,
        "returncode": completed.returncode,
        "provider_request_count": len(provider_requests),
        "watcher_request_count": len(sdk_requests),
        "post_tool_event_count": len(post_tools),
        "sdk_tool_ids": ids,
        "interfaces": ["lo"],
        "external_route": False,
        "native_tool_results": all(
            any(marker in json.dumps(message["content"]) for message in results) for marker in FILES.values()
        ),
        "has_final_tail": any(
            request["input"] == []
            and request["messages"][-1]["role"] == "assistant"
            and FINAL in json.dumps(request["messages"][-1]["content"])
            for request in sdk_requests
        ),
        "protocol_errors": protocol_errors,
        "command": command,
        "provider_base_url": url + "/v1",
        "home": str(Path.home()),
        "native_environment_keys": sorted(env),
        "sdk_revision": SDK_REVISION,
        "sdk_wheel_sha256": hashlib.sha256(sdk_wheel.read_bytes()).hexdigest(),
        "sdk_files_verified": sdk_files_verified,
        "sdk_noneditable": True,
        "native_version": native_version,
    }
    (EVIDENCE / "summary.json").write_text(json.dumps(summary, indent=2))
    sys.stdout.write(json.dumps(summary) + "\n")
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert len(provider_requests) >= 2 and not protocol_errors
    assert len(post_tools) >= 2 and all(marker in json.dumps(post_tools) for marker in FILES.values())
    if APP == "mistral-vibe":
        assert all(event["tool_status"] == "success" for event in post_tools)
    assert set(ids) == set(CALL_IDS), ids
    assert {message["tool_call_id"] for message in results} >= set(CALL_IDS)
    assert summary["native_tool_results"] and summary["has_final_tail"]
finally:
    (EVIDENCE / "provider-requests.json").write_text(json.dumps(provider_requests, indent=2))
    (EVIDENCE / "sdk-requests.json").write_text(json.dumps(sdk_requests, indent=2))
    (EVIDENCE / "other-requests.json").write_text(json.dumps(other_requests, indent=2))
    (EVIDENCE / "protocol-errors.json").write_text(json.dumps(protocol_errors, indent=2))
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
