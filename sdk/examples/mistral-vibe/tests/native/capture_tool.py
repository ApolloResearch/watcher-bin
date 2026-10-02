"""Record native post-tool delivery without changing the tool result or permission flow."""

import json
import sys
from pathlib import Path

payload = json.load(sys.stdin)
with Path("/evidence/post-tool-events.jsonl").open("a") as handle:
    handle.write(json.dumps(payload) + "\n")
sys.stdout.write("{}\n")
