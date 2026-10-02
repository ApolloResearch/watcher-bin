#!/usr/local/bin/python
"""Retain original native bridge input, then execute the unchanged installed adapter.

The same process becomes Python's module runner, preserving native timeout and
cancellation behavior. Only fixture-owned payloads under /evidence are retained.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

raw = sys.stdin.buffer.read()
assert len(sys.argv) == 3 and sys.argv[1] == "-m"
module = sys.argv[2]
assert module in {"watcher_openclaw_bridge.integration", "watcher_openclaw_bridge.pre_tool"}
with Path("/evidence/bridge-inputs.jsonl").open("a") as output:
    output.write(json.dumps({"module": module, "raw": raw.decode()}) + "\n")
if module == "watcher_openclaw_bridge.integration":
    Path("/evidence/native-records.json").write_text(json.dumps(json.loads(raw)["messages"], indent=2))
with tempfile.TemporaryFile() as stream:
    stream.write(raw)
    stream.seek(0)
    os.dup2(stream.fileno(), 0)
    os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
