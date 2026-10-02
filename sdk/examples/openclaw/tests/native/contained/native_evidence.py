"""Retain exact hook traffic and independent effects in contained native tests.

The test supplies an explicit execution oracle; Watcher responses alone never
decide whether a native tool ran. Forwarding accepts only a loopback relay.
"""

import ctypes
import hashlib
import json
import os
import sqlite3
import struct
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

EVIDENCE = Path("/evidence")
_WRITE_LOCK = threading.Lock()


def expects_execution(default: bool) -> bool:
    """Require an independent oracle whenever actual backend policy is forwarded."""
    if not os.environ.get("WATCHER_EXAMPLE_FORWARD_URL"):
        return default
    expected = os.environ.get("WATCHER_EXPECT_TOOL_EXECUTION")
    if expected not in {"0", "1"}:
        raise ValueError("Forwarded tests require WATCHER_EXPECT_TOOL_EXECUTION=0 or 1")
    return expected == "1"


def append(name: str, record: dict) -> None:
    """Keep concurrent native callbacks in separate, complete JSONL records."""
    with _WRITE_LOCK, (EVIDENCE / name).open("a") as output:
        output.write(json.dumps(record) + "\n")


def is_pending(body: dict) -> bool:
    """Identify these drivers' full gates; observers use triage_only histories.

    Retrospective observers deliberately omit later results from each historical
    prefix, so missing tool results alone cannot establish pending execution.
    """
    inputs = body.get("input")
    if not inputs or body.get("mode") != "full":
        return False
    if body.get("ephemeral") is True:
        return True
    calls = inputs if isinstance(inputs, list) else [inputs]
    completed = {message.get("tool_call_id") for message in body.get("messages", []) if message["role"] == "tool"}
    return all(call.get("tool_use_id") not in completed for call in calls)


def forward(handler, body: dict, raw: bytes, snapshot) -> bool:
    """Relay original bytes/status/body and capture effects before releasing a gate.

    Return False when forwarding is unconfigured. The snapshot callback must
    observe physical effects without creating those effects itself.
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
        raise ValueError("Forwarding requires the loopback test relay")
    expects_execution(False)
    gate = is_pending(body)
    before = {"monotonic": time.monotonic(), **snapshot()} if gate else None
    headers = {
        key: value
        for key, value in handler.headers.items()
        if key.lower() not in {"host", "content-length", "connection", "transfer-encoding"}
    }
    with httpx.Client(timeout=480, trust_env=False) as client:
        response = client.post(target.rstrip("/") + handler.path, content=raw, headers=headers)
    if gate:
        append(
            "gate-order.jsonl",
            {
                "path": handler.path,
                "input": body["input"],
                "ephemeral": body.get("ephemeral", False),
                "before_request": before,
                "after_response": {"monotonic": time.monotonic(), **snapshot()},
            },
        )
    append(
        "forwarded-sdk-responses.jsonl",
        {"path": handler.path, "status_code": response.status_code, "request": body, "response": response.text},
    )
    handler.send_response(response.status_code)
    handler.send_header("Content-Type", response.headers.get("content-type", "application/json"))
    handler.send_header("Content-Length", str(len(response.content)))
    handler.end_headers()
    handler.wfile.write(response.content)
    return True


class FileReads:
    """Count Linux IN_OPEN events per physical file, independently of tool output.

    Construct after writing fixture content and before launching the native CLI.
    Each supplied file must already exist. Reading them in the driver afterward
    would contaminate the oracle; keep their known content separately.
    """

    def __init__(self, paths):
        self.lock = threading.Lock()
        libc = ctypes.CDLL(None, use_errno=True)
        libc.inotify_init1.argtypes = [ctypes.c_int]
        libc.inotify_init1.restype = ctypes.c_int
        libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        libc.inotify_add_watch.restype = ctypes.c_int
        self.fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), "Cannot observe native file opens")
        self.paths = {}
        self.counts = {}
        for path in paths:
            descriptor = libc.inotify_add_watch(self.fd, os.fsencode(path), 0x20)
            if descriptor < 0:
                os.close(self.fd)
                raise OSError(ctypes.get_errno(), "Cannot watch fixture file")
            self.paths[descriptor] = str(path)
            self.counts[str(path)] = 0

    def snapshot(self) -> dict:
        """Drain pending events and return cumulative counts for each watched file."""
        with self.lock:
            while True:
                try:
                    data = os.read(self.fd, 65536)
                except BlockingIOError:
                    break
                offset = 0
                while offset < len(data):
                    descriptor, mask, _, length = struct.unpack_from("iIII", data, offset)
                    if mask & 0x4000:
                        raise AssertionError("File-open evidence overflowed")
                    if mask & 0x20:
                        self.counts[self.paths[descriptor]] += 1
                    offset += 16 + length
            return {"file_opens": dict(self.counts)}

    def verify(self, expected: bool) -> None:
        """Retain final counts; every requested file must open only when allowed."""
        result = self.snapshot()
        (EVIDENCE / "native-file-opens.json").write_text(json.dumps(result, indent=2))
        assert all(count > 0 if expected else count == 0 for count in result["file_opens"].values()), result

    def close(self) -> None:
        os.close(self.fd)


def retain_transcripts(roots) -> None:
    """Retain native logs and OpenClaw SQLite stores after the gateway exits.

    SQLite originals, including WAL sidecars, are copied without transformation.
    A consistent backup also captures committed WAL rows, and each event_json
    value is exported verbatim with its native session ID and sequence number.
    Callers must stop native writers first. Errors remain test failures.
    """
    target = EVIDENCE / "native-transcripts"
    target.mkdir(exist_ok=True)
    manifest = []
    for root in roots:
        for path in sorted(Path(root).rglob("*.jsonl")):
            if not path.is_file() or path.is_symlink():
                continue
            retained = target / (str(len(manifest)) + ".jsonl")
            retained.write_bytes(path.read_bytes())
            manifest.append(
                {
                    "native_path": str(path),
                    "retained": retained.name,
                    "sha256": hashlib.sha256(retained.read_bytes()).hexdigest(),
                }
            )
        for path in sorted(Path(root).rglob("openclaw-agent.sqlite")):
            if not path.is_file() or path.is_symlink():
                continue
            store = target / f"store-{len(manifest)}"
            store.mkdir()
            for suffix in ("", "-wal", "-shm"):
                original = Path(str(path) + suffix)
                if not original.exists():
                    continue
                if not original.is_file() or original.is_symlink():
                    raise ValueError(f"Native SQLite file is not a regular file: {original}")
                retained = store / original.name
                retained.write_bytes(original.read_bytes())
                manifest.append(
                    {
                        "native_path": str(original),
                        "retained": str(retained.relative_to(target)),
                        "sha256": hashlib.sha256(retained.read_bytes()).hexdigest(),
                        "format": "native-sqlite-file",
                    }
                )
            snapshot = store / "snapshot.sqlite"
            deadline = time.monotonic() + 10

            def require_deadline(_status, _remaining, _total, *, deadline=deadline):
                if time.monotonic() > deadline:
                    raise TimeoutError("Native transcript backup exceeded ten seconds")

            source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
            destination = sqlite3.connect(snapshot)
            try:
                source.backup(destination, pages=256, progress=require_deadline, sleep=0.05)
                assert destination.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
                query = "SELECT session_id, seq, event_json FROM transcript_events ORDER BY session_id, seq"
                events = []
                for index, (session_id, sequence, event_json) in enumerate(destination.execute(query)):
                    retained = store / f"event-{index}.json"
                    retained.write_bytes(event_json.encode("utf-8"))
                    events.append(
                        {
                            "session_id": session_id,
                            "seq": sequence,
                            "retained": str(retained.relative_to(target)),
                            "sha256": hashlib.sha256(retained.read_bytes()).hexdigest(),
                        }
                    )
            finally:
                destination.close()
                source.close()
            if not events:
                raise AssertionError("Native SQLite store contains no transcript events")
            manifest.append(
                {
                    "native_path": str(path),
                    "retained": str(snapshot.relative_to(target)),
                    "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                    "format": "sqlite-backup",
                    "query": query,
                    "events": events,
                }
            )
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2))
