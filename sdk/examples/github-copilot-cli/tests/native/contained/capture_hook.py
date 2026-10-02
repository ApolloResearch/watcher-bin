"""Retain the actual native command input and forward its bytes without changes."""

import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

mode = sys.argv[1]
directory = Path("/evidence/hook-inputs")
directory.mkdir(exist_ok=True)
identity = f"{mode}-{uuid4()}"
payload = sys.stdin.buffer.read()
(directory / f"{identity}.json").write_bytes(payload)
result = subprocess.run(["watcher-github-copilot-cli", *sys.argv[1:]], input=payload, capture_output=True, check=False)
(directory / f"{identity}.receipt").write_text(json.dumps({"returncode": result.returncode}))
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
raise SystemExit(result.returncode)
