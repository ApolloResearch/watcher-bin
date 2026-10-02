"""Run the installed Mastra Node agent through the real Watcher relay and SDK readback.

A tee executable records native processor submissions before invoking the real
Python gate unchanged. A refused native step can end without a final answer; in
that case verify its actual last submitted prefix instead of fabricating a result.
"""

import asyncio
import json
import os
import subprocess
from pathlib import Path

from _test_support.readback import wait_for_conversation
from node_artifacts import verify_node_package

from watcher_sdk import AsyncWatcherClient

ROOT = Path("/evidence")


async def readback(config: dict, transcript: list[dict], pending: list[dict], completed: bool) -> None:
    """Require the real public API to expose the exact history and actually attempted IDs."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key", max_retries=0) as client:
        await wait_for_conversation(
            client,
            external_ids={"other": [config["conversation_id"]]},
            final_text=None,
            expected_messages=transcript,
            decision_ids={item["call_id"] for item in pending},
            evidence=ROOT,
            timeout=30,
        )
    if completed:
        assert any(config["final_text"] in json.dumps(message["content"]) for message in transcript)


def main() -> None:
    """Keep native exit status, file effects, model traffic and actual gate input as separate evidence."""
    verify_node_package(ROOT)
    config = json.loads((ROOT / "input.json").read_text())
    gates = ROOT / "native-gates"
    gates.mkdir()
    script = Path(__file__).with_name("backend_fixture.mjs")
    environment = {
        **os.environ,
        "WATCHER_PYTHON": str(Path(__file__).with_name("capture_gate.py")),
        "WATCHER_BASE_URL": os.environ["WATCHER_URL"],
        "WATCHER_API_KEY": "fixture-key",
        "WATCHER_SESSION_ID": config["conversation_id"],
        "WATCHER_TIMEOUT": "60",
        "WATCHER_GATE_EVIDENCE": str(gates),
    }
    result = subprocess.run(
        ["node", str(script)], env=environment, capture_output=True, text=True, timeout=130, check=False
    )
    (ROOT / "node.stdout").write_text(result.stdout)
    (ROOT / "node.stderr").write_text(result.stderr)
    order = [json.loads(line)["id"] for line in (gates / "order.jsonl").read_text().splitlines()]
    submissions = [json.loads((gates / (identity + ".input.json")).read_text()) for identity in order]
    assert submissions, "The native Mastra scheduler never reached the installed SDK gate"
    pending = []
    for submitted in submissions:
        if "--" not in submitted["args"]:
            continue
        call_id = submitted["args"][submitted["args"].index("--") + 1]
        calls = [
            call for message in submitted["messages"] for call in message.get("tool_calls", []) if call["id"] == call_id
        ]
        assert len(calls) == 1
        call = calls[0]
        pending.append({"call_id": call_id, "name": call["function"], "arguments": call["arguments"]})
    assert pending and len({item["call_id"] for item in pending}) == len(pending)
    snapshots_path = ROOT / "native-snapshots.json"
    snapshots = json.loads(snapshots_path.read_text()) if snapshots_path.exists() else []
    transcript = snapshots[-1] if snapshots else submissions[-1]["messages"]
    effects_path = ROOT / "side-effects.jsonl"
    effects = [json.loads(line) for line in effects_path.read_text().splitlines()] if effects_path.exists() else []
    assert sorted(item["city"] for item in effects) == (["Paris", "Tokyo"] if config["executes"] else [])
    if config["executes"]:
        assert result.returncode == 0, result.stderr
        assert {item["call_id"] for item in pending} == set(config["call_ids"])
    else:
        assert result.returncode != 0, "The native denied step unexpectedly completed"
    (ROOT / "native-submissions.json").write_text(json.dumps(submissions, indent=2))
    (ROOT / "native-pending.json").write_text(json.dumps(pending, indent=2))
    (ROOT / "native-transcript.json").write_text(json.dumps(transcript, indent=2))
    asyncio.run(readback(config, transcript, pending, result.returncode == 0))


if __name__ == "__main__":
    main()
