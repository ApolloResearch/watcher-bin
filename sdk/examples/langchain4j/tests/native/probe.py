"""Drive installed LangChain4j through a local provider and configured real Watcher.

Run only in a network-isolated fixture with WATCHER_URL pointing to its local
Watcher relay. Provider replies are deterministic; the native AI Services runner
owns tool dispatch. Public SDK readback proves the selected stored transcript and
decisions, independently of the JVM exit status and observable tool effect file.
"""

import argparse
import asyncio
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4

from artifacts import verify_native_artifacts

from watcher_sdk import AsyncWatcherClient, TrajectoryView


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    case: dict[str, Any] = json.loads(args.case.read_text())
    evidence = args.evidence
    evidence.mkdir(parents=True, exist_ok=True)
    verify_native_artifacts(evidence / "native-artifacts.json")
    assert sorted(os.listdir("/sys/class/net")) == ["lo"], "Native fixture requires loopback-only networking"
    session_id = "langchain4j:" + str(uuid4())
    requests: list[dict[str, Any]] = []
    pending_text = "Proposed tool call " + case["token"]
    tool_ids = ["call-a", "call-b"]

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert self.path == "/v1/chat/completions"
            requests.append(request)
            if any(message["role"] == "tool" for message in request["messages"]):
                message: dict[str, Any] = {"role": "assistant", "content": case["final_text"]}
                reason = "stop"
            else:
                message = {
                    "role": "assistant",
                    "content": pending_text,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": "weather", "arguments": json.dumps({"city": city})},
                        }
                        for call_id, city in zip(tool_ids, ["Paris", "Tokyo"], strict=True)
                    ],
                }
                reason = "tool_calls"
            encoded = json.dumps(
                {
                    "id": "native-fixture",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "fixture-model",
                    "choices": [{"index": 0, "message": message, "finish_reason": reason}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    human = case.get("human")
    if human is not None:
        assert human in ("allow", "deny")
    env = {
        **os.environ,
        "WATCHER_PYTHON": os.environ.get("WATCHER_PYTHON", "/usr/local/bin/python"),
        "WATCHER_BASE_URL": os.environ["WATCHER_URL"],
        "WATCHER_API_KEY": os.environ.get("WATCHER_API_KEY", "fixture-key"),
        "WATCHER_SESSION_ID": session_id,
        "PROVIDER_API_KEY": "fixture-key",
        "PROVIDER_MODEL": "fixture-model",
    }
    command = [
        os.environ.get("JAVA_BIN", "/opt/jdk/bin/java"),
        "-Xmx256m",
        "-cp",
        os.environ["WATCHER_JAVA_CLASSPATH"],
        "HumanApprovalProbe" if human else "com.example.watcher.examples.langchain4j.WatcherMonitoredExample",
        f"http://127.0.0.1:{server.server_port}/v1",
        str(evidence / "effects"),
        str(evidence),
    ]
    stdout_file = (evidence / "java.stdout").open("w")
    stderr_file = (evidence / "java.stderr").open("w")
    process = subprocess.Popen(command, env=env, stdout=stdout_file, stderr=stderr_file, text=True)
    try:
        if human:
            deadline = time.monotonic() + 90
            while not (evidence / "approval-entered.txt").exists():
                assert process.poll() is None, "The native run ended before human approval"
                assert time.monotonic() < deadline, "Native human approval did not become pending"
                time.sleep(0.02)
            assert not (evidence / "effects").exists(), "A tool ran before human approval"
            (evidence / "human-choice.txt").write_text(human)
        process.wait(timeout=120)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        stdout_file.close()
        stderr_file.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        (evidence / "provider-requests.json").write_text(json.dumps(requests, indent=2))
    stderr = (evidence / "java.stderr").read_text()
    assert requests, "The native model client did not reach its provider"
    executed = (evidence / "effects").read_text().splitlines() if (evidence / "effects").exists() else []
    assert executed == (["Paris", "Tokyo"] if case["executes"] else []), executed
    assert (process.returncode == 0) is case["executes"], stderr
    if case["executes"]:
        history = json.loads((evidence / "final.json").read_text())
        assert history[-1]["content"] == case["final_text"]
        assert {m["tool_call_id"] for m in history if m["role"] == "tool"} == set(tool_ids)

    async def verify():
        async with AsyncWatcherClient(env["WATCHER_BASE_URL"], api_key=env["WATCHER_API_KEY"]) as watcher:
            decisions = set(tool_ids if case["executes"] else tool_ids[:1]) if case.get("grades", 1) else set()
            await wait_for_conversation(
                watcher,
                external_ids={"other": [session_id]},
                final_text=case["final_text"] if case["executes"] else pending_text,
                decision_ids=decisions,
                evidence=evidence,
            )

    asyncio.run(verify())
    (evidence / "native-result.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "executes": case["executes"],
                "effects": executed,
                "human": human,
                "exit_code": process.returncode,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
