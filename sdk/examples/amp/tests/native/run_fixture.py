"""Exercise the real Amp SDK/CLI against a contained service endpoint and retain failures."""

import asyncio
import json
import os
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from amp_sdk import ProcessError
from watcher_amp.integration import run_amp

from watcher_sdk import AsyncWatcherClient

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
evidence = Path("/evidence")
workspace = Path("/tmp/native-workspace")
workspace.mkdir()
cli = "/opt/native/node_modules/.bin/amp"
for name, args in {
    "version": ["--version"],
    "help": ["--help"],
    "router-help": ["config", "model-providers", "add-router", "--help"],
    "providers-help": ["config", "model-providers", "--help"],
}.items():
    result = subprocess.run(
        [cli, *args], cwd=workspace, stdin=subprocess.DEVNULL, text=True, capture_output=True, timeout=30
    )
    (evidence / (name + ".txt")).write_text(result.stdout + result.stderr)
requests = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def handle_request(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode()
        requests.append({"method": self.command, "path": self.path, "body": body})
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error":"No Amp service implementation is configured at this loopback endpoint"}')

    do_GET = handle_request
    do_POST = handle_request
    do_PUT = handle_request


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_port}"
os.environ.update(
    {
        "AMP_URL": url,
        "AMP_API_KEY": "sgamp_fixture_only",
        "AMP_CLI_PATH": cli,
        "AMP_LOG_FILE": "/evidence/native.log",
        "PWD": str(workspace),
    }
)


async def main():
    try:
        async with AsyncWatcherClient(url, api_key="fixture-only") as client:
            async with asyncio.timeout(45):
                await run_amp("Run pwd then say sdk50 native completed", str(workspace), client)
    except ProcessError as exc:
        (evidence / "error.txt").write_text(type(exc).__name__ + ": " + str(exc))
        (evidence / "stderr.txt").write_text(exc.stderr)
        return {"native_completed": False, "error_type": type(exc).__name__}
    return {"native_completed": True}


try:
    summary = asyncio.run(main())
    summary.update(
        {
            "requests": len(requests),
            "paths": [request["path"] for request in requests],
            "egress_blocked": True,
            "interfaces": ["lo"],
        }
    )
    (evidence / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
    assert summary["native_completed"] is False
    assert "/api/internal?getUserInfo" in summary["paths"]
    assert all("/hooks/pre-tool-use" not in path for path in summary["paths"])
finally:
    (evidence / "service-requests.json").write_text(json.dumps(requests, indent=2))
    server.shutdown()
