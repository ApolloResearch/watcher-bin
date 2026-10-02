"""Capture the actual native completion event and transcript before invoking the adapter."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

payload = sys.stdin.read()
with Path("/evidence/hook-inputs.jsonl").open("a") as handle:
    handle.write(payload + "\n")
event = json.loads(payload)
path = Path(event["transcript_path"])
name = hashlib.sha256(event["session_id"].encode()).hexdigest()
shutil.copyfile(path, "/evidence/native-transcript-" + name + ".jsonl")
result = subprocess.run(
    [sys.executable, "-m", "watcher_qwen_code.integration", *sys.argv[1:]],
    input=payload,
    capture_output=True,
    text=True,
    check=False,
)
with Path("/evidence/adapter-results.jsonl").open("a") as handle:
    handle.write(json.dumps({"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}) + "\n")
sys.stdout.write(result.stdout)
sys.stderr.write(result.stderr)
sys.exit(result.returncode)
