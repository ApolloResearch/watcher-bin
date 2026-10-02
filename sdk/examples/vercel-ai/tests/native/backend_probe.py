"""Drive installed native Vercel generateText tools through the real Watcher SDK.

run_conversation launches the installed Node executable and awaits its actual
native authorize/execute messages. The Python effect is reached only through
that scheduler. Preserve raw native histories separately from normalized SDK
messages and inspect actual effect files independently of Watcher decisions.
"""

import asyncio
import json
import os
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

from _test_support.readback import wait_for_conversation
from node_artifacts import verify_node_package
from watcher_vercel_ai_bridge.adapter import messages_for_watcher
from watcher_vercel_ai_bridge.monitoring import Monitor
from watcher_vercel_ai_bridge.synchronous import run_conversation

from watcher_sdk import AsyncWatcherClient

ROOT = Path("/evidence")


class CapturingMonitor(Monitor):
    """Retain exact Node-supplied histories while delegating every policy operation."""

    def __init__(self, client: AsyncWatcherClient, conversation_id: str, manual: bool):
        super().__init__(client, conversation_id, timeout=60, approval_callback=self.approve if manual else None)
        self.pending = []
        self.native_pending = []
        self.native_recorded = []

    async def approve(self, **request):
        """Hold the native scheduler until the test provides an explicit human choice."""
        with (ROOT / "approval-entered.jsonl").open("a") as stream:
            stream.write(json.dumps({"tool_use_id": request["tool_use_id"], "arguments": request["tool_input"]}) + "\n")
        async with asyncio.timeout(30):
            while not (ROOT / "approval-release.json").exists():
                await asyncio.sleep(0.02)
        return json.loads((ROOT / "approval-release.json").read_text())["approved"]

    async def before(self, messages, call_id, name, arguments):
        self.native_pending.append(deepcopy(messages))
        await super().before(messages, call_id, name, arguments)

    async def before_transcript(self, transcript, call_id, name, arguments):
        self.pending.append({"call_id": call_id, "name": name, "arguments": deepcopy(arguments)})
        (ROOT / "native-pending.json").write_text(json.dumps(self.pending, indent=2))
        await super().before_transcript(transcript, call_id, name, arguments)

    async def record(self, messages):
        self.native_recorded.append(deepcopy(messages))
        await super().record(messages)


async def run() -> None:
    """Require native tool requests, physical effects and exact public storage readback."""
    verify_node_package(ROOT)
    config = json.loads((ROOT / "input.json").read_text())
    executable = shutil.which("watcher-vercel-ai-sync")
    assert executable is not None, "Install the packed native Node package before this driver"
    executable = str(Path(executable).resolve(strict=True))
    assert "/node_modules/watcher-vercel-ai-example/" in executable
    os.environ["WATCHER_VERCEL_SYNC"] = executable
    inspected = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            "import {createRequire} from 'node:module'; const r=createRequire(import.meta.url); "
            "console.log(JSON.stringify({node:process.version,ai:r('ai/package.json').version,"
            "module:import.meta.resolve('watcher-vercel-ai-example/synchronous')}));",
        ],
        cwd="/opt/node-app",
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    installation = json.loads(inspected.stdout)
    installation["executable"] = executable
    (ROOT / "native-node-installation.json").write_text(json.dumps(installation, indent=2))

    def effect(value):
        with (ROOT / "side-effects.jsonl").open("a") as output:
            output.write(json.dumps({"value": value}) + "\n")
        return str(value * 2)

    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key", max_retries=0) as client:
        monitor = CapturingMonitor(client, config["conversation_id"], config["manual"])
        history = None
        try:
            history = await run_conversation(monitor, effect)
        finally:
            (ROOT / "native-source.json").write_text(
                json.dumps(
                    {
                        "returned_history": history,
                        "pending_histories": monitor.native_pending,
                        "recorded_histories": monitor.native_recorded,
                    },
                    indent=2,
                )
            )
        assert monitor.pending
        assert {item["call_id"] for item in monitor.pending} == {"double-2", "double-3"}
        transcript = messages_for_watcher(history)
        assert transcript[-1]["content"] == "4 and 6"
        effects_file = ROOT / "side-effects.jsonl"
        effects = (
            [json.loads(line)["value"] for line in effects_file.read_text().splitlines()]
            if effects_file.exists()
            else []
        )
        assert sorted(effects) == ([2, 3] if config["executes"] else [])
        (ROOT / "native-transcript.json").write_text(json.dumps(transcript, indent=2))
        await wait_for_conversation(
            client,
            external_ids={"other": ["vercel-ai:" + config["conversation_id"]]},
            final_text="4 and 6",
            expected_messages=transcript,
            decision_ids={item["call_id"] for item in monitor.pending},
            evidence=ROOT,
            timeout=30,
        )


if __name__ == "__main__":
    asyncio.run(run())
