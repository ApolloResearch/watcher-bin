"""Probe public CLI entry points with no credentials or network; preserve exact exits."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

evidence = Path("/evidence")
workspace = Path("/workspace")
workspace.mkdir(exist_ok=True)
(workspace / ".cursor").mkdir(exist_ok=True)
(workspace / "fixture.txt").write_text("cursor local diagnostic fixture\n")
events = [
    "workspaceOpen",
    "sessionStart",
    "beforeSubmitPrompt",
    "preToolUse",
    "postToolUse",
    "postToolUseFailure",
    "afterAgentResponse",
    "stop",
]
(workspace / ".cursor/hooks.json").write_text(
    json.dumps({"version": 1, "hooks": {event: [{"command": "python3 /diag/capture_hook.py"}] for event in events}})
)
assert not any(
    name in os.environ for name in ["CURSOR_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "WATCHER_API_KEY"]
)
assert not Path("/home/probe/.cursor").exists()
evidence.joinpath("boundary.json").write_text(
    json.dumps(
        {
            "interfaces": sorted(path.name for path in Path("/sys/class/net").iterdir()),
            "routes": Path("/proc/net/route").read_text(),
            "environment_keys": sorted(os.environ),
            "uid": os.getuid(),
            "home_started_empty": True,
            "cursor_credentials_present": False,
        },
        indent=2,
    )
    + "\n"
)
assert sorted(path.name for path in Path("/sys/class/net").iterdir()) == ["lo"]
cli = "/opt/cursor/dist-package/cursor-agent"
commands = [
    ("version", [cli, "--version"]),
    ("help", [cli, "--help"]),
    ("status", [cli, "status", "--format", "json"]),
    (
        "headless",
        [
            cli,
            "--print",
            "--trust",
            "--workspace",
            str(workspace),
            "--output-format",
            "json",
            "Read fixture.txt with the shell tool and reply with its exact text.",
        ],
    ),
]
results = []
for label, command in commands:
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=workspace,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    timed_out = False
    try:
        output, _ = process.communicate(timeout=40)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGKILL)
        output, _ = process.communicate()
    evidence.joinpath(label + ".log").write_text(output)
    results.append(
        {
            "label": label,
            "command": command,
            "exit_code": process.returncode,
            "timed_out": timed_out,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    )
    evidence.joinpath("commands.json").write_text(json.dumps(results, indent=2) + "\n")
captured = evidence / "native-events.jsonl"
rows = [json.loads(line) for line in captured.read_text().splitlines()] if captured.exists() else []
status = json.loads(evidence.joinpath("status.log").read_text())
assert evidence.joinpath("version.log").read_text().strip() == "2026.09.10-fd3934a"
assert results[0]["exit_code"] == results[1]["exit_code"] == results[2]["exit_code"] == 0
assert status["isAuthenticated"] is False
assert results[3]["exit_code"] == 1 and not results[3]["timed_out"]
assert "Authentication required" in evidence.joinpath("headless.log").read_text()
assert not rows, "Unexpected native hook delivery before authentication; inspect captured evidence"
evidence.joinpath("summary.json").write_text(
    json.dumps(
        {
            "authentication_prerequisite_verified": True,
            "commands": results,
            "native_events": len(rows),
            "event_names": [row.get("hook_event_name") for row in rows],
            "native_tool_lifecycle_proven": False,
        },
        indent=2,
    )
    + "\n"
)
sys.stdout.write(
    json.dumps({"native_events": len(rows), "command_exits": {row["label"]: row["exit_code"] for row in results}})
    + "\n"
)
