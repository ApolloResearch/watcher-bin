#!/usr/bin/env python
"""Retain Mastra's exact native gate input, then invoke its installed SDK bridge.

This test-only executable replaces WATCHER_PYTHON to retain submitted prefixes.
It neither computes nor alters Watcher decisions. Human-approval exchanges forward
the initial JSON line and one parent reply without waiting for stdin EOF first.
All output and the real child exit status are retained and forwarded unchanged.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

args = sys.argv[1:]  # noqa: APE015 - Forward the native gate's already-tokenized arguments unchanged.
assert args[:2] == ["-m", "watcher_mastra_bridge.gate"]
human = "--human-approval" in args
raw = sys.stdin.buffer.readline() if human else sys.stdin.buffer.read()
messages = json.loads(raw)
identity = uuid4().hex
root = Path(os.environ["WATCHER_GATE_EVIDENCE"])
root.mkdir(exist_ok=True)
record = {"args": args, "messages": messages}
(root / (identity + ".input.json")).write_text(json.dumps(record, indent=2))
with (root / "order.jsonl").open("a") as order:
    order.write(json.dumps({"id": identity}) + "\n")
if human:
    chunks = []
    with (
        (root / (identity + ".stderr")).open("wb") as errors,
        subprocess.Popen(
            [sys.executable, *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors
        ) as child,
    ):
        assert child.stdin is not None and child.stdout is not None
        child.stdin.write(raw)
        child.stdin.flush()
        for line in child.stdout:
            chunks.append(line)
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
            # The real gate emits one request and waits for the parent's reply.
            reply = sys.stdin.buffer.readline()
            (root / (identity + ".reply.json")).write_bytes(reply)
            child.stdin.write(reply)
            child.stdin.close()
        code = child.wait()
    stdout = b"".join(chunks)
    stderr = (root / (identity + ".stderr")).read_bytes()
else:
    result = subprocess.run([sys.executable, *args], input=raw, capture_output=True, check=False)
    code, stdout, stderr = result.returncode, result.stdout, result.stderr
    sys.stdout.buffer.write(stdout)
(root / (identity + ".result.json")).write_text(
    json.dumps({"exit_code": code, "stdout": stdout.decode(), "stderr": stderr.decode()})
)
sys.stderr.buffer.write(stderr)
raise SystemExit(code)
