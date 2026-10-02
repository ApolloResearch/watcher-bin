"""Exercise a standalone native CLI and retain exact model, hook and SDK traffic."""

import hashlib
import importlib.metadata
import json
import os
import socket
import subprocess
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import distribution
from pathlib import Path
from typing import Any

from sync_support import (
    SCENARIO,
    expects_execution,
    forward,
    respond,
    retain_native_transcripts,
    verify_native_reads,
    verify_pending,
    verify_sdk_wheel,
    watch_native_reads,
    watch_pending,
)

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
verify_sdk_wheel()

requests = []
sdk_request_paths = []
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
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        body = json.loads(raw)
        if "/hooks/pre-tool-use" in self.path and os.environ.get("WATCHER_EXAMPLE_FORWARD_URL"):
            requests.append(body)
            assert forward(self, body, raw=raw)
            if body["input"] == []:
                flushed.set()
            return
        if "/hooks/pre-tool-use" in self.path and body["input"] and "settings_overrides" not in body:
            requests.append(body)
            respond(self, body)
            return
        if "/hooks/pre-tool-use" in self.path:
            requests.append(body)
            sdk_request_paths.append(self.path)
            if body["input"]:
                assert body["mode"] == "triage_only"
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
            name = "read_files"
            assert any(tool["function"]["name"] == name for tool in tool_defs), "Expected native file tool absent"
            args = {"files": [{"path": str(WORKSPACE / "fixture.txt")}]}
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
if SCENARIO == "timeout":
    env["WATCHER_TIMEOUT_SECONDS"] = "1"
else:
    env.pop("WATCHER_TIMEOUT_SECONDS", None)
hooks = WORKSPACE / ".cline/hooks"
hooks.mkdir(parents=True)
for name in ("TaskComplete",):
    script = hooks / name
    script.write_text("#!/bin/sh\nexec /usr/local/bin/python /opt/fixture/hook_entry.py --record-only\n")
    script.chmod(448)
pre_hook = hooks / "PreToolUse"
pre_hook.write_text("#!/bin/sh\nexec /usr/local/bin/python -m watcher_cline_bridge.pre_tool\n")
pre_hook.chmod(448)
cli = "/opt/native/node_modules/.bin/cline"
core_package = json.loads(Path("/opt/native/node_modules/@cline/core/package.json").read_text())
cli_package = json.loads(Path("/opt/native/node_modules/cline/package.json").read_text())
assert core_package["version"] == "0.0.82" and cli_package["version"] == "3.0.61"
lockfile = Path("/opt/fixture/package-lock.json")
lock = json.loads(lockfile.read_text())
assert lock["packages"]["node_modules/@cline/core"]["version"] == core_package["version"]
assert lock["packages"]["node_modules/cline"]["version"] == cli_package["version"]
resolution = subprocess.run(
    ["node", "--input-type=module", "--eval", "process.stdout.write(import.meta.resolve('@cline/core'))"],
    cwd="/opt/fixture",
    env=env,
    text=True,
    capture_output=True,
    timeout=10,
    check=True,
)
assert resolution.stdout.startswith("file:///opt/adapter/node_modules/@cline/core/")
assert (
    json.loads(Path("/opt/adapter/node_modules/@cline/core/package.json").read_text())["version"]
    == core_package["version"]
)
(EVIDENCE / "native-packages.json").write_text(
    json.dumps(
        {
            "core": core_package["version"],
            "cli": cli_package["version"],
            "history_reader_module_resolution": resolution.stdout,
            "lockfile_sha256": hashlib.sha256(lockfile.read_bytes()).hexdigest(),
        },
        indent=2,
    )
)
sdk_revision = None
sdk_distribution = distribution("watcher-sdk")
origin = json.loads(sdk_distribution.read_text("direct_url.json"))
assert origin["url"].endswith(f"/watcher_sdk-{importlib.metadata.version('watcher-sdk')}-py3-none-any.whl")
assert not origin.get("dir_info", {}).get("editable", False)
wheel = Path("/opt/fixture") / f"watcher_sdk-{importlib.metadata.version('watcher-sdk')}-py3-none-any.whl"
sdk_files_verified = 0
with zipfile.ZipFile(wheel) as package:
    for name in package.namelist():
        if not name.endswith("/") and name.startswith(("watcher_sdk/", "watcher_transcript_transport/")):
            assert sdk_distribution.locate_file(name).read_bytes() == package.read(name)
            sdk_files_verified += 1
assert sdk_files_verified > 0
env["CLINE_SESSION_BACKEND_MODE"] = "local"
env["CLINE_HOOKS_LOG_PATH"] = "/evidence/native-hooks-log.jsonl"
auth = subprocess.run(
    [
        cli,
        "auth",
        "--provider",
        "openai-compatible",
        "--apikey",
        "fixture-only",
        "--modelid",
        "gpt-4o",
        "--baseurl",
        url + "/v1",
    ],
    cwd=WORKSPACE,
    env=env,
    text=True,
    capture_output=True,
    timeout=60,
)
(EVIDENCE / "auth-stdout.txt").write_text(auth.stdout)
(EVIDENCE / "auth-stderr.txt").write_text(auth.stderr)
assert auth.returncode == 0
command = [
    cli,
    "--provider",
    "openai-compatible",
    "--model",
    "gpt-4o",
    "--json",
    "--timeout",
    "90",
    "Read fixture.txt with read_files then say sdk50 native completed",
]
watch_native_reads([WORKSPACE / "fixture.txt"])
watch_pending(provider_requests)
try:
    version = subprocess.run([cli, "--version"], cwd=WORKSPACE, env=env, text=True, capture_output=True, timeout=30)
    (EVIDENCE / "version.txt").write_text(version.stdout + version.stderr)
    result = subprocess.run(
        command, cwd=WORKSPACE, env=env, text=True, capture_output=True, stdin=subprocess.DEVNULL, timeout=120
    )
    flushed.wait(55 if expects_execution() else 0)
    (EVIDENCE / "stdout.txt").write_text(result.stdout)
    (EVIDENCE / "stderr.txt").write_text(result.stderr)
    retain_native_transcripts(env["HOME"])
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
        "sdk_revision": sdk_revision,
        "sdk_noneditable": True,
        "sdk_files_verified": sdk_files_verified,
        "sdk_wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "lockfile_sha256": hashlib.sha256(lockfile.read_bytes()).hexdigest(),
    }
    summary["has_initial_user_context"] = any(
        message["role"] == "user" and "Read fixture.txt with read_files" in json.dumps(message["content"])
        for request in requests
        for message in request["messages"]
    )
    verify_pending()
    verify_native_reads()
    (EVIDENCE / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
    assert result.returncode == 0
    assert summary["tool_ids"]
    assert summary["has_final"] == expects_execution()
    assert summary["native_tool_ran"] == expects_execution()
    assert summary["sdk_tool_result"] == expects_execution()
    assert any(r["input"] and "settings_overrides" not in r for r in requests)
    assert summary["has_initial_user_context"]
finally:
    (EVIDENCE / "provider-requests.json").write_text(json.dumps(provider_requests, indent=2))
    (EVIDENCE / "sdk-requests.json").write_text(json.dumps(requests, indent=2))
    (EVIDENCE / "sdk-request-paths.json").write_text(json.dumps(sdk_request_paths, indent=2))
    server.shutdown()
