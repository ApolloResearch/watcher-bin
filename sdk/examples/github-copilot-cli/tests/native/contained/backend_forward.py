"""Pass unchanged SDK calls to an isolated actual Watcher service during native tests."""

import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

EVIDENCE = Path("/evidence")


def expects_execution() -> bool:
    """Require an independent execution oracle when a real backend supplies policy."""
    expected = os.environ.get("WATCHER_EXPECT_TOOL_EXECUTION")
    if expected not in {"0", "1"}:
        raise ValueError("Forwarded native tests require WATCHER_EXPECT_TOOL_EXECUTION=0 or 1")
    return expected == "1"


def forward(handler, body: dict, raw: bytes, marker: Path) -> None:
    """Forward the exact request and record physical marker state before returning.

    Only loopback destinations are allowed. The gate is the request with one
    ``input`` object; recording snapshots send ``input=[]``. Gate ordering is kept
    with whether its decision was stored on a named native call or judged
    ephemerally.
    """
    target = os.environ["WATCHER_EXAMPLE_FORWARD_URL"]
    parsed = urlsplit(target)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
    ):
        raise ValueError("The forwarding target must be the loopback test relay")
    expects_execution()
    gate = isinstance(body.get("input"), dict)
    before = {"monotonic": time.monotonic(), "marker_exists": marker.exists()}
    with httpx.Client(timeout=480, trust_env=False) as client:
        headers = {
            key: value
            for key, value in handler.headers.items()
            if key.lower() not in {"host", "content-length", "connection", "transfer-encoding"}
        }
        response = client.post(target.rstrip("/") + handler.path, content=raw, headers=headers)
    after = {"monotonic": time.monotonic(), "marker_exists": marker.exists()}
    evidence = EVIDENCE
    if gate:
        with (evidence / "gate-order.jsonl").open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "path": handler.path,
                        "before_request": before,
                        "after_response": after,
                        "tool_name": body["input"]["tool_name"],
                        "tool_use_id": body["input"].get("tool_use_id"),
                        "ephemeral": body.get("ephemeral") is True,
                    }
                )
                + "\n"
            )
    with (evidence / "forwarded-sdk-responses.jsonl").open("a") as stream:
        stream.write(
            json.dumps(
                {"path": handler.path, "status_code": response.status_code, "request": body, "response": response.text}
            )
            + "\n"
        )
    handler.send_response(response.status_code)
    handler.send_header("Content-Type", response.headers.get("content-type", "application/json"))
    handler.send_header("Content-Length", str(len(response.content)))
    handler.end_headers()
    handler.wfile.write(response.content)


def forward_get(handler) -> None:
    """Relay a readback GET, such as a trajectory read, to the same loopback relay."""
    target = os.environ["WATCHER_EXAMPLE_FORWARD_URL"]
    parsed = urlsplit(target)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("The forwarding target must be the loopback test relay")
    headers = {
        key: value
        for key, value in handler.headers.items()
        if key.lower() not in {"host", "content-length", "connection", "transfer-encoding"}
    }
    with httpx.Client(timeout=60, trust_env=False) as client:
        response = client.get(target.rstrip("/") + handler.path, headers=headers)
    handler.send_response(response.status_code)
    handler.send_header("Content-Type", response.headers.get("content-type", "application/json"))
    handler.send_header("Content-Length", str(len(response.content)))
    handler.end_headers()
    handler.wfile.write(response.content)
