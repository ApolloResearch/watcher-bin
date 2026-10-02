"""Capture actual native events and inspect the public history reader at completion."""

import json
import subprocess
import sys
from pathlib import Path

payload = sys.stdin.read()
event = json.loads(payload)
with Path("/evidence/hook-inputs.jsonl").open("a") as output:
    output.write(payload + "\n")
if event["hookName"] == "agent_end":
    Path("/evidence/history-started.txt").write_text("started")
    history = subprocess.run(
        ["/opt/adapter/node_modules/.bin/watcher-cline-history", event["sessionContext"]["rootSessionId"]],
        capture_output=True,
        text=True,
        check=False,
        timeout=25,
    )
    Path("/evidence/native-history.json").write_text(history.stdout)
    Path("/evidence/history-stderr.txt").write_text(history.stderr)
subprocess.run(
    [sys.executable, "-m", "watcher_cline_bridge.integration", *sys.argv[1:]], input=payload, text=True, check=False
)
