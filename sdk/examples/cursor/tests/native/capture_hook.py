"""Save only events delivered by the standalone native Cursor CLI."""

import json
import sys
from pathlib import Path

payload = json.load(sys.stdin)
with Path("/evidence/native-events.jsonl").open("a") as output:
    output.write(json.dumps(payload) + "\n")
event = payload.get("hook_event_name")
response = (
    {"permission": "allow"} if event == "preToolUse" else {"continue": True} if event == "beforeSubmitPrompt" else {}
)
sys.stdout.write(json.dumps(response) + "\n")
