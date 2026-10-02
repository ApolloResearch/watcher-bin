"""Capture the native plugin's exact stdin, then run the shipped Python bridge."""

import json
import subprocess
import sys
import time
from pathlib import Path

payload = sys.stdin.read()
event = json.loads(payload)
assert event["session_id"] and isinstance(event["messages"], list)
name = str(time.time_ns())
Path("/evidence/native-snapshot-" + name + ".json").write_text(payload)
# This test recorder transparently forwards Python arguments; it is not a user CLI.
result = subprocess.run(
    [sys.executable, *sys.argv[1:]],  # noqa: APE015
    input=payload,
    capture_output=True,
    text=True,
    check=False,
)
Path("/evidence/adapter-result-" + name + ".json").write_text(
    json.dumps({"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
)
sys.stdout.write(result.stdout)
sys.stderr.write(result.stderr)
sys.exit(result.returncode)
