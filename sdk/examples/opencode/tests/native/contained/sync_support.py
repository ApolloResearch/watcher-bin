"""Loopback Watcher fixture used only by contained native enforcement probes."""

import ctypes
import hashlib
import importlib.metadata
import json
import os
import struct
import threading
import zipfile
from importlib.metadata import distribution
from pathlib import Path
from urllib.parse import urlsplit

import httpx

SCENARIO = os.environ.get("WATCHER_EXAMPLE_SCENARIO", "allow")
PENDING = threading.Event()
RELEASE = threading.Event()


def expects_execution():
    """Read an explicit test oracle when SDK requests are forwarded to a real backend."""
    if os.environ.get("WATCHER_EXAMPLE_FORWARD_URL"):
        expected = os.environ.get("WATCHER_EXPECT_TOOL_EXECUTION")
        if expected not in {"0", "1"}:
            raise ValueError("Forwarded native runs require an explicit expected execution outcome")
        return expected == "1"
    return SCENARIO in {"allow", "observe-deferred", "paused-deferred", "grading-failure-allow"}


def forward(handler, body, *, raw: bytes):
    """Forward unchanged SDK hook requests to the isolated actual-backend relay.

    Returns False when no forwarding target was supplied. Only loopback targets
    are accepted. Retain the actual status/body; never add fixture acknowledgements.
    Native model requests remain local to the original contained provider fixture.
    """
    target = os.environ.get("WATCHER_EXAMPLE_FORWARD_URL")
    if not target:
        return False
    parsed = urlsplit(target)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
    ):
        raise ValueError("The Watcher forwarding target must be a local test relay")
    expects_execution()
    with httpx.Client(timeout=480, trust_env=False) as client:
        headers = {
            key: value
            for key, value in handler.headers.items()
            if key.lower() not in {"host", "content-length", "connection", "transfer-encoding"}
        }
        response = client.post(target.rstrip("/") + handler.path, content=raw, headers=headers)
    with Path("/evidence/forwarded-sdk-responses.jsonl").open("a") as output:
        output.write(
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
    return True


def retain_native_transcripts(home):
    """Copy fixture-native JSONL logs before the disposable container is removed."""
    target = Path("/evidence/native-transcripts")
    target.mkdir(exist_ok=True)
    manifest = []
    for path in sorted(Path(home).rglob("*.jsonl")):
        if path.is_file() and not path.is_symlink():
            retained = target / (str(len(manifest)) + ".jsonl")
            retained.write_bytes(path.read_bytes())
            manifest.append(
                {
                    "native_path": str(path),
                    "retained": retained.name,
                    "sha256": hashlib.sha256(retained.read_bytes()).hexdigest(),
                }
            )
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2))


def respond(handler, body):
    """Respond with a deterministic completed decision or one explicit failure case."""
    enforcement = bool(body["input"]) and "settings_overrides" not in body
    if enforcement:
        assert body["mode"] == "full" and "require_recording" not in handler.path
        for call in body["input"]:
            assert not any(m.get("tool_call_id") == call["tool_use_id"] for m in body["messages"])
        if SCENARIO == "timeout":
            PENDING.set()
            threading.Event().wait(3)
        if SCENARIO == "pending":
            PENDING.set()
            assert RELEASE.wait(30), "Pending fixture was not inspected and released"
    decision = SCENARIO if SCENARIO in {"deny", "escalate", "deferred"} else "allow"
    if SCENARIO == "pending":
        decision = "deny"
    mode = "observe" if SCENARIO == "observe-mode" else "paused" if SCENARIO == "paused" else "enforce"
    outcomes = [
        {
            "tool_use_id": "wrong-id" if enforcement and SCENARIO == "identity-error" else call["tool_use_id"],
            "decision": decision if enforcement else "deferred",
            "judged_decision": decision if enforcement else "allow",
            "enforcement_mode": mode if enforcement else "observe",
            "decision_source": "rule",
            "verdict": {},
            "latency_ms": 1,
        }
        for call in body["input"]
    ]
    handler.send_response(503 if enforcement and SCENARIO == "http-error" else 200)
    handler.send_header("Content-Type", "application/json")
    if enforcement and SCENARIO == "missing-outcome":
        outcomes = []
    handler.end_headers()
    handler.wfile.write(
        json.dumps(
            {"error": {"message": "fixture unavailable"}} if enforcement and SCENARIO == "http-error" else outcomes
        ).encode()
    )


def watch_pending(provider_requests, marker_path=None):
    """Check the native process is still waiting before delivering a deny response."""
    if SCENARIO != "pending":
        return

    def check():
        assert PENDING.wait(100), "The native pre-tool callback did not reach Watcher"
        has_result = any(
            "tool_result" in json.dumps(r)
            or "functionResponse" in json.dumps(r)
            or "function_call_output" in json.dumps(r)
            or '"role": "tool"' in json.dumps(r)
            for r in provider_requests
        )
        # Provider definitions can mention result strings; only actual message lists count.
        bodies = [r.get("body", r) if isinstance(r, dict) else {} for r in provider_requests]
        has_result = any(
            any(
                m.get("role") == "tool"
                or m.get("type") == "function_call_output"
                or any(
                    isinstance(b, dict) and b.get("type") == "tool_result"
                    for b in m.get("content", [])
                    if isinstance(m.get("content"), list)
                )
                for m in body.get("messages", body.get("input", []))
            )
            for body in bodies
        )
        exists = bool(marker_path and Path(marker_path).exists())
        opens = native_read_count()
        receipt = {
            "pending_before_response": True,
            "native_result_before_response": has_result,
            "side_effect_before_response": exists,
            "native_file_opens_before_response": opens,
            "native_file_accesses_before_response": _ACCESS_COUNT,
        }
        Path("/evidence/pending.json").write_text(json.dumps(receipt, indent=2))
        assert not has_result and not exists and _ACCESS_COUNT == 0
        RELEASE.set()

    threading.Thread(target=check, daemon=True).start()


def verify_pending():
    """A pending scenario passes only with the explicit before-response receipt."""
    if SCENARIO == "pending":
        receipt = json.loads(Path("/evidence/pending.json").read_text())
        assert (
            receipt["pending_before_response"]
            and not receipt["native_result_before_response"]
            and not receipt["side_effect_before_response"]
        )
        assert RELEASE.is_set()


_READ_FD = None
_READ_COUNT = 0
_ACCESS_COUNT = 0
_READ_PATHS = []


def watch_native_reads(paths):
    """Watch the fixture files themselves, independently of native/model output."""
    global _READ_FD, _READ_PATHS
    libc = ctypes.CDLL(None, use_errno=True)
    libc.inotify_init1.argtypes = [ctypes.c_int]
    libc.inotify_init1.restype = ctypes.c_int
    libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    libc.inotify_add_watch.restype = ctypes.c_int
    _READ_FD = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
    if _READ_FD < 0:
        raise OSError(ctypes.get_errno(), "Cannot observe native file opens")
    _READ_PATHS = [str(path) for path in paths]
    for path in _READ_PATHS:
        if libc.inotify_add_watch(_READ_FD, os.fsencode(path), 0x21) < 0:
            raise OSError(ctypes.get_errno(), "Cannot watch fixture file")


def native_read_count():
    """Drain Linux IN_OPEN events; no native output or model claim is used."""
    global _READ_COUNT, _ACCESS_COUNT
    if _READ_FD is None:
        return 0
    while True:
        try:
            data = os.read(_READ_FD, 65536)
        except BlockingIOError:
            break
        offset = 0
        while offset < len(data):
            _, mask, _, length = struct.unpack_from("iIII", data, offset)
            if mask & 0x20:
                _READ_COUNT += 1
            if mask & 0x1:
                _ACCESS_COUNT += 1
            offset += 16 + length
    return _READ_COUNT


def verify_native_reads():
    """Allowed native reads must open fixture files; every withheld case must not."""
    if _READ_FD is None:
        return
    count = native_read_count()
    Path("/evidence/native-file-opens.json").write_text(
        json.dumps({"paths": _READ_PATHS, "opens": count, "accesses": _ACCESS_COUNT, "scenario": SCENARIO}, indent=2)
    )
    assert len(_READ_PATHS) <= _ACCESS_COUNT if expects_execution() else _ACCESS_COUNT == 0


def verify_sdk_wheel():
    """Match every installed SDK package file against the supplied noneditable wheel."""
    package = distribution("watcher-sdk")
    origin_text = package.read_text("direct_url.json")
    assert origin_text is not None, "The SDK must be installed from the supplied wheel"
    origin = json.loads(origin_text)
    assert origin["url"].endswith(f"/watcher_sdk-{importlib.metadata.version('watcher-sdk')}-py3-none-any.whl")
    assert not origin.get("dir_info", {}).get("editable", False)
    wheel = Path("/opt/fixture") / f"watcher_sdk-{importlib.metadata.version('watcher-sdk')}-py3-none-any.whl"
    count = 0
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if not name.endswith("/") and name.startswith(("watcher_sdk/", "watcher_transcript_transport/")):
                assert Path(str(package.locate_file(name))).read_bytes() == archive.read(name)
                count += 1
    assert count > 0
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
    assert installed == expected, installed ^ expected
    Path("/evidence/sdk-wheel.json").write_text(
        json.dumps(
            {
                "noneditable": True,
                "files_verified": count,
                "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            },
            indent=2,
        )
    )


_ARMED = False


def arm_native_tool_reads():
    """Start tool-I/O measurement before the native process receives its first call.

    Preserve startup reads separately. This boundary comes from the local model
    fixture, so no side effect of the proposed tool can precede it.
    """
    global _READ_COUNT, _ACCESS_COUNT, _ARMED
    assert not _ARMED, "The fixture supports one proposed native tool batch"
    native_read_count()
    Path("/evidence/native-io-before-tool-proposal.json").write_text(
        json.dumps(
            {
                "opens": _READ_COUNT,
                "accesses": _ACCESS_COUNT,
                "phase": "before native process receives model tool proposals",
            },
            indent=2,
        )
    )
    _READ_COUNT = 0
    _ACCESS_COUNT = 0
    _ARMED = True
