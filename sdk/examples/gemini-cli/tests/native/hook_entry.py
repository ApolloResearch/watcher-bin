"""Record the actual native completion payload, then invoke the public SDK adapter."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

payload = sys.stdin.read()
with Path("/evidence/hook-inputs.jsonl").open("a") as out:
    out.write(payload + "\n")
event = json.loads(payload)
transcript = event.get("transcript_path")
if transcript and Path(transcript).is_file():
    name = hashlib.sha256(str(event.get("session_id")).encode()).hexdigest()
    shutil.copyfile(transcript, "/evidence/native-transcript-" + name + ".jsonl")
    records = [json.loads(line) for line in Path(transcript).read_text().splitlines() if line.strip()]
    Path("/evidence/native-records.json").write_text(json.dumps(records, indent=2))
subprocess.run([sys.executable, "-m", "watcher_gemini_cli.integration"], input=payload, text=True, check=False)
