"""Run pinned Aider edits and adapter regressions in a network-none container."""

import asyncio
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
from importlib.metadata import distribution, version
from pathlib import Path

from aider.coders import Coder
from watcher_aider.observation import Capture, ObservedIO, ObservedModel, run_prompt, send_capture

from watcher_sdk import AsyncWatcherClient

EVIDENCE = Path("/evidence")
WORKSPACE = Path("/tmp/native-workspace")
WORKSPACE.mkdir(mode=0o700)
os.chdir(WORKSPACE)
assert version("aider-chat") == "0.86.2"
assert Path.home() == Path("/home/probe")
assert {name for _, name in socket.if_nameindex()} == {"lo"}
assert not Path("/var/run/docker.sock").exists()
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.settimeout(1)
    try:
        probe.connect(("1.1.1.1", 443))
    except OSError:
        pass
    else:
        raise RuntimeError("External network route unexpectedly available")
revision = None
sdk_distribution = distribution("watcher-sdk")
origin = json.loads(sdk_distribution.read_text("direct_url.json"))
assert origin["url"].endswith(f"/watcher_sdk-{importlib.metadata.version('watcher-sdk')}-py3-none-any.whl")
assert not origin.get("dir_info", {}).get("editable", False)
wheel = Path("/opt/fixture") / f"watcher_sdk-{importlib.metadata.version('watcher-sdk')}-py3-none-any.whl"
verified = 0
with zipfile.ZipFile(wheel) as package:
    for name in package.namelist():
        if not name.endswith("/") and name.startswith(("watcher_sdk/", "watcher_transcript_transport/")):
            assert sdk_distribution.locate_file(name).read_bytes() == package.read(name)
            verified += 1
assert verified > 0
requests = []
request_paths = []


class Handler(BaseHTTPRequestHandler):
    """Acknowledge only the public SDK hook and retain its exact submitted body."""

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_POST(self):
        assert self.path.startswith("/v1/hooks/pre-tool-use")
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        requests.append(body)
        request_paths.append(self.path)
        if body["input"]:
            assert body["mode"] == "triage_only"
        outcomes = [
            {
                "tool_use_id": item["tool_use_id"],
                "decision": "deferred",
                "judged_decision": "allow",
                "enforcement_mode": "observe",
                "decision_source": "rule",
                "verdict": {},
                "latency_ms": 1,
            }
            for item in body["input"]
        ]
        encoded = json.dumps(outcomes).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
capture = Capture()
target = WORKSPACE / "greeting.txt"
target.write_text("before native edit\n")
(EVIDENCE / "before.txt").write_bytes(target.read_bytes())
model = ObservedModel("gpt-4o", capture)
model.extra_params = {"mock_response": "greeting.txt\n```text\nafter native edit\n```"}
coder = Coder.create(
    main_model=model,
    edit_format="whole",
    io=ObservedIO(capture, yes=False, pretty=False),
    fnames=[str(target)],
    use_git=False,
    stream=False,
    map_tokens=0,
    auto_lint=False,
    auto_test=False,
)
try:
    run_prompt(coder, capture, "Replace the supplied file with after native edit.")
    assert target.read_text() == "after native edit\n"
    model.extra_params = {"mock_response": "finished native edit"}
    run_prompt(coder, capture, "Confirm completion without editing any file.")

    async def submit():
        async with AsyncWatcherClient(f"http://127.0.0.1:{server.server_port}", api_key="fixture-only") as client:
            await send_capture(client, "contained-native-edit", capture)

    asyncio.run(submit())
    operations = [operation for exchange in capture.exchanges for operation in exchange["writes"]]
    assert len(capture.exchanges) == 2 and len(operations) == 1
    assert operations[0]["status"] == "completed"
    assert len(requests) == 2 and requests[0]["input"][0]["tool_use_id"] == operations[0]["id"]
    assert requests[-1]["input"] == [] and requests[-1]["messages"][-1]["role"] == "assistant"
    assert "finished native edit" in json.dumps(requests[-1]["messages"][-1]["content"])
    tests = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--noconftest",
            "-c",
            "/opt/fixture/pyproject.toml",
            "-p",
            "no:cacheprovider",
            "--junitxml=/evidence/tests.xml",
            "/opt/fixture/tests",
        ],
        text=True,
        capture_output=True,
        timeout=150,
        check=False,
    )
    (EVIDENCE / "tests.stdout.txt").write_text(tests.stdout)
    (EVIDENCE / "tests.stderr.txt").write_text(tests.stderr)
    summary = {
        "native_package": "aider-chat",
        "native_version": version("aider-chat"),
        "source_revision": "253f0368b873ba30d8ee26e463718f0c03614ddf",
        "model_exchange_count": len(capture.exchanges),
        "native_write_count": len(operations),
        "write_ids": [operation["id"] for operation in operations],
        "sdk_request_count": len(requests),
        "final_assistant_tail": True,
        "test_exit_code": tests.returncode,
        "sdk_revision": revision,
        "sdk_noneditable": True,
        "sdk_files_verified": verified,
        "sdk_wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "model_response_source": "LiteLLM supported mock_response setting",
        "runtime_network": "Docker --network none",
        "interfaces": ["lo"],
        "external_route": False,
    }
    (EVIDENCE / "summary.json").write_text(json.dumps(summary, indent=2))
    sys.stdout.write(json.dumps(summary) + "\n")
    assert tests.returncode == 0, tests.stdout[-5000:]
finally:
    (EVIDENCE / "capture.json").write_text(json.dumps(capture.model_dump(), indent=2))
    (EVIDENCE / "sdk-requests.json").write_text(json.dumps(requests, indent=2))
    (EVIDENCE / "sdk-request-paths.json").write_text(json.dumps(request_paths, indent=2))
    (EVIDENCE / "after.txt").write_bytes(target.read_bytes())
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
