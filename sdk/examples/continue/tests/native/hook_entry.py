"""Retain each actual native hook payload, then invoke the public SDK adapter."""

import subprocess
import sys
from pathlib import Path

payload = sys.stdin.read()
with Path("/evidence/hook-inputs.jsonl").open("a") as output:
    output.write(payload + "\n")
subprocess.run([sys.executable, "-m", "watcher_continue.integration"], input=payload, text=True, check=False)
