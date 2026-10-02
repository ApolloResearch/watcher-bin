"""Local fixture for scalar ephemeral decisions and native pending-result evidence."""

import hashlib
import json
import os
import socket
import threading
import zipfile
from importlib.metadata import distribution
from pathlib import Path

SCENARIO = os.environ.get("WATCHER_EXAMPLE_SCENARIO", "allow")
PENDING = threading.Event()
RELEASE = threading.Event()


def respond(handler, body):
    assert body["ephemeral"] is True and body["mode"] == "full"
    assert isinstance(body["input"], dict)
    assert "require_recording" not in handler.path
    call = body["input"]
    if SCENARIO == "pending":
        PENDING.set()
        assert RELEASE.wait(30), "Pending fixture was not inspected and released"
    decision = SCENARIO if SCENARIO in {"deny", "escalate", "deferred"} else "allow"
    if SCENARIO == "pending":
        decision = "deny"
    mode = "observe" if SCENARIO == "observe-mode" else "paused" if SCENARIO == "paused" else "enforce"
    outcome = {
        "tool_use_id": "wrong-id" if SCENARIO == "identity-error" else call.get("tool_use_id"),
        "decision": decision,
        "judged_decision": decision,
        "enforcement_mode": mode,
        "decision_source": "grading_error" if SCENARIO == "grading-error" else "rule",
        "verdict": {},
        "latency_ms": 1,
    }
    handler.send_response(503 if SCENARIO == "http-error" else 200)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(json.dumps(outcome).encode())


def native_results_seen(provider_requests):
    """Inspect only actual provider conversation items, including Gemini functionResponse."""
    for record in provider_requests:
        body = record.get("body", record)
        for message in body.get("contents", []):
            if any("functionResponse" in part for part in message.get("parts", [])):
                return True
        for message in body.get("messages", body.get("input", [])):
            if message.get("role") == "tool" or message.get("type") == "function_call_output":
                return True
            content = message.get("content")
            if isinstance(content, list) and any(
                isinstance(part, dict) and part.get("type") == "tool_result" for part in content
            ):
                return True
    return False


def recorded_ids(requests):
    return [
        call["tool_use_id"] for request in requests if isinstance(request["input"], list) for call in request["input"]
    ]


def watch_pending(provider_requests, marker_path=None):
    if SCENARIO != "pending":
        return

    def check():
        assert PENDING.wait(25), "The native pre-tool callback did not reach Watcher"
        threading.Event().wait(0.25)
        has_result = native_results_seen(provider_requests)
        has_marker = bool(marker_path and Path(marker_path).exists())
        receipt = {
            "pending_before_response": True,
            "native_result_before_response": has_result,
            "side_effect_before_response": has_marker,
            "verified": not has_result and not has_marker,
        }
        Path("/evidence/pending.json").write_text(json.dumps(receipt, indent=2))
        assert receipt["verified"]
        RELEASE.set()

    threading.Thread(target=check, daemon=True).start()


def verify_environment():
    """Check fresh HOME, no egress, and exact installed SDK bytes before native imports."""
    assert Path.home() == Path("/home/probe") and not list(Path.home().iterdir())
    assert socket.if_nameindex() == [(1, "lo")]
    assert not Path("/proc/net/route").read_text().splitlines()[1:]
    wheel = Path("/sdk-reference.whl")
    package = distribution("watcher-sdk")
    origin = json.loads(package.read_text("direct_url.json"))
    assert origin["url"].endswith(".whl") and not origin.get("dir_info", {}).get("editable", False)
    count = 0
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if not name.endswith("/") and name.startswith(("watcher_sdk/", "watcher_transcript_transport/")):
                assert package.locate_file(name).read_bytes() == archive.read(name), name
                count += 1
    with zipfile.ZipFile(wheel) as archive:
        expected = {
            name
            for name in archive.namelist()
            if not name.endswith("/") and name.startswith(("watcher_sdk/", "watcher_transcript_transport/"))
        }
    site = Path(str(package.locate_file("")))
    installed = {
        str(path.relative_to(site))
        for folder in ("watcher_sdk", "watcher_transcript_transport")
        for path in (site / folder).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert installed == expected and count == len(expected), installed ^ expected
    Path("/evidence/boundary.json").write_text(
        json.dumps(
            {
                "interfaces": ["lo"],
                "fresh_home": True,
                "sdk_files_verified": count,
                "sdk_noneditable": True,
                "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            },
            indent=2,
        )
    )
