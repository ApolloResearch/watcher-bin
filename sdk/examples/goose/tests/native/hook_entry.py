"""Retain the native hook payload and session export before running the adapter."""

import json
import subprocess
import sys
from pathlib import Path

payload = sys.stdin.read()
event = json.loads(payload)
with Path("/evidence/hook-inputs.jsonl").open("a") as out:
    out.write(payload + "\n")
export = subprocess.run(
    ["goose", "session", "export", "--session-id", event["session_id"], "--format", "json"],
    text=True,
    capture_output=True,
    check=False,
)
Path("/evidence/native-export.json").write_text(export.stdout)
Path("/evidence/export-stderr.txt").write_text(export.stderr)
subprocess.run(
    [sys.executable, "-m", "watcher_goose.integration", *sys.argv[1:]], input=payload, text=True, check=False
)
