"""Exercise an installed Broadcast receiver with a fixture and real local Watcher.

The source is an explicit OTLP fixture, not hosted OpenRouter emission. The HTTP
receiver, public SDK, Watcher application and storage path are exercised normally.
"""

import asyncio
import importlib.metadata
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from watcher_sdk import AsyncWatcherClient, TrajectoryView


def main():
    root = Path("/evidence")
    case = json.loads((root / "input.json").read_text())
    distribution = importlib.metadata.distribution("watcher-openrouter-example")
    (root / "integration-installation.json").write_text(distribution.read_text("direct_url.json"))
    messages = [
        {"role": "user", "content": case["token"]},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": case["call_id"],
                    "type": "function",
                    "function": {"name": "Read", "arguments": '{"file_path":"fixture.txt","count":0,"enabled":false}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": case["call_id"], "content": "Actual fixture result " + case["token"]},
    ]
    payload = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": uuid4().hex,
                                "spanId": uuid4().hex[:16],
                                "startTimeUnixNano": "123",
                                "attributes": [
                                    {"key": "gen_ai.request.model", "value": {"stringValue": "fixture"}},
                                    {"key": "gen_ai.prompt", "value": {"stringValue": json.dumps(messages)}},
                                    {
                                        "key": "gen_ai.completion",
                                        "value": {
                                            "stringValue": json.dumps(
                                                [{"role": "assistant", "content": case["final_text"]}]
                                            )
                                        },
                                    },
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    (root / "source-payload.json").write_text(json.dumps(payload, indent=2))
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        port = candidate.getsockname()[1]
    log = (root / "receiver.log").open("w")
    process = subprocess.Popen(
        [
            str(Path(sys.executable).parent / "watcher-openrouter-receiver"),
            "serve",
            "fixture-account",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env={**os.environ, "WATCHER_API_KEY": "fixture-key", "OPENROUTER_WEBHOOK_TOKEN": "fixture-secret"},
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                if process.poll() is not None:
                    raise RuntimeError("Receiver exited before startup") from None
                time.sleep(0.1)
        else:
            raise TimeoutError("Receiver did not start")
        response = httpx.post(
            f"http://127.0.0.1:{port}/v1/traces",
            json=payload,
            headers={"Authorization": "Bearer fixture-secret"},
            timeout=60,
        )
        assert response.status_code == 200, response.text
        receipt = response.json()
        assert receipt["submitted"] == 1
        (root / "submission.json").write_text(response.text)

        async def verify():
            async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key") as client:
                await wait_for_conversation(
                    client,
                    external_ids={"other": receipt["conversation_ids"]},
                    final_text=case["final_text"],
                    decision_ids=set(),
                    evidence=root,
                )

        asyncio.run(verify())
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        log.close()


async def wait_for_conversation(
    client: AsyncWatcherClient,
    *,
    external_ids: dict[str, list[str]],
    final_text: str | None,
    decision_ids: set[str],
    evidence: Path,
    timeout: float = 15,
) -> dict[str, Any]:
    """Return one exact stored session's extended trajectory, or fail by deadline.

    External ID filters must identify one native conversation. Ambiguous matches
    fail immediately. An empty decision set supports paused/transcript-only runs;
    it does not claim they produced tool judgments. A null final_text is for an aborted native run with no final answer; it asserts only the selected decisions. Callers separately compare
    full tool names, typed arguments and actual native results to these records.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        result = await client.search_sessions(external_ids=external_ids)
        sessions = result.to_dict()
        (evidence / "sessions.json").write_text(json.dumps(sessions, indent=2))
        if sessions["total"] > 1:
            raise AssertionError("The native identity matched multiple Watcher sessions")
        if sessions["total"] == 1:
            item = sessions["sessions"][0]
            if item["latest_trajectory_id"] is not None:
                response = await client.get_trajectory(
                    item["session_id"], item["latest_trajectory_id"], view=TrajectoryView.EXTENDED
                )
                stored = response.to_dict()
                (evidence / "trajectory.json").write_text(json.dumps(stored, indent=2))
                has_final = any(
                    message.get("role") == "assistant" and message.get("content") == final_text
                    for message in stored["messages"]
                )
                if (has_final or final_text is None) and decision_ids <= stored["tool_call_decisions"].keys():
                    return stored
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(
                "The exact final transcript and tool decisions did not become readable through the SDK"
            )
        await asyncio.sleep(0.05)


if __name__ == "__main__":
    main()
