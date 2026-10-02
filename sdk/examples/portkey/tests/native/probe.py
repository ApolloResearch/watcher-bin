"""Exercise an installed gateway with a local model and a real or fixture Watcher.

Set WATCHER_URL to the isolated real Watcher relay and provide --case for backend
verification. Without it, --protocol runs only protocol fixtures and makes no
claim about Watcher persistence. No model-provider connection leaves loopback.
"""

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
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


def available_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return candidate.getsockname()[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", choices=("portkey", "bifrost"), required=True)
    parser.add_argument("--case", type=Path)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--protocol", action="store_true")
    parser.add_argument("--provenance", type=Path, default=Path("/opt/provenance.json"))
    args = parser.parse_args()
    if bool(args.case) == args.protocol:
        parser.error("Choose exactly one of --case or --protocol")
    evidence = args.evidence
    evidence.mkdir(parents=True, exist_ok=True)
    verify_native_artifacts(args.provenance, evidence / "native-artifacts.json")
    case: dict[str, Any] = (
        json.loads(args.case.read_text())
        if args.case
        else {
            "call_id": "native-" + str(uuid4()),
            "token": "marker-" + str(uuid4()),
            "final_text": "Completed local gateway test " + str(uuid4()),
            "executes": True,
        }
    )
    provider_requests = []
    watcher_requests = []
    results = []
    held = threading.Event()
    release = threading.Event()
    provider_port, watcher_port, bridge_port, gateway_port = [available_port() for _ in range(4)]

    class Fixture(BaseHTTPRequestHandler):
        """Serve deterministic provider responses; optionally emulate hook transport."""

        server: ThreadingHTTPServer

        def log_message(self, format: str, *_args: Any) -> None:
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.server.server_port == watcher_port and self.path == "/v1/auth/check-permissions":
                data = {"granted": True, "missing": []}
            elif self.server.server_port == watcher_port:
                watcher_requests.append(body)
                assert body["format"] == "raw"
                assert body["user_agent"] == "watcher-local-fixture/1"
                assert body["provider"] == "openai"
                text = body["request_body"]["messages"][0]["content"]
                if "held" in text:
                    held.set()
                    if not release.wait(20):
                        raise RuntimeError("Held fixture was not released")
                mode = "observe" if "observe" in text else "paused" if "paused" in text else "enforce"
                judgment = (
                    "deny" if "deny" in text or mode == "observe" else "escalate" if "escalate" in text else "allow"
                )
                decision = "deferred" if mode != "enforce" else judgment
                data = [
                    {
                        "decision": decision,
                        "judged_decision": judgment if mode != "paused" else None,
                        "decision_source": "bypass" if mode == "paused" else "rule",
                        "enforcement_mode": mode,
                        "tool_use_id": call["id"],
                        "verdict": {},
                        "latency_ms": 1,
                    }
                    for index, call in enumerate(body["response_body"]["choices"][0]["message"].get("tool_calls") or [])
                ]
            else:
                provider_requests.append(body)
                if "truncated-text" in body["messages"][0]["content"]:
                    message = {"role": "assistant", "content": "Partial text " + case["token"]}
                    finish = "length"
                elif any(message["role"] == "tool" for message in body["messages"]):
                    message = {"role": "assistant", "content": case["final_text"]}
                    finish = "stop"
                else:
                    message: dict[str, Any] = {
                        "role": "assistant",
                        "content": "Proposed tool call " + case["token"],
                        "tool_calls": [
                            {
                                "id": case["call_id"],
                                "type": "function",
                                "function": {
                                    "name": "Write",
                                    "arguments": json.dumps(
                                        {"file_path": "sentinel.txt", "content": case["token"], "enabled": True}
                                    ),
                                },
                            }
                        ],
                    }
                    finish = "tool_calls"
                data = {
                    "id": "completion-fixture",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "fixture",
                    "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                }
                if body.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    delta: dict[str, Any] = dict(message)
                    calls: list[dict[str, Any]] | None = delta.get("tool_calls")
                    if calls:
                        calls[0]["index"] = 0
                        arguments = calls[0]["function"]["arguments"]
                        calls[0]["function"]["arguments"] = arguments[:8]
                        chunks = [delta, {"tool_calls": [{"index": 0, "function": {"arguments": arguments[8:]}}]}]
                    else:
                        chunks = [delta]
                    for chunk in chunks:
                        event = {
                            **data,
                            "object": "chat.completion.chunk",
                            "choices": [{"index": 0, "delta": chunk, "finish_reason": None}],
                        }
                        self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
                        self.wfile.flush()
                    event = {
                        **data,
                        "object": "chat.completion.chunk",
                        "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                    }
                    self.wfile.write(("data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n").encode())
                    return
            encoded = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    servers = []
    for port in [provider_port] + ([watcher_port] if args.protocol else []):
        server = ThreadingHTTPServer(("127.0.0.1", port), Fixture)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
    env = dict(
        os.environ,
        WATCHER_BASE_URL=f"http://127.0.0.1:{watcher_port}" if args.protocol else os.environ["WATCHER_URL"],
        WATCHER_API_KEY="fixture-key",
        WATCHER_BRIDGE_TOKEN="fixture-bridge",
        WATCHER_BRIDGE_URL=f"http://127.0.0.1:{bridge_port}",
        GATEWAY_API_KEY="fixture-client",
        GATEWAY_PORT=str(gateway_port),
        PROVIDER_API_KEY="fixture-provider",
        PROVIDER_BASE_URL=f"http://127.0.0.1:{provider_port}",
        NODE_OPTIONS="--max-old-space-size=1024",
        NODE_ENV="production",
    )
    bridge = [sys.executable, "-m", "watcher_" + args.gateway + ".bridge", "serve", "--port", str(bridge_port)]
    if args.gateway == "bifrost":
        bridge.append("--allow-buffered-stream")
        app = evidence / "bifrost-config"
        app.mkdir()
        (app / "catalog.json").write_text("{}")
        config = {
            "client": {"enable_logging": False},
            "framework": {
                "pricing": {
                    "pricing_url": (app / "catalog.json").as_uri(),
                    "model_parameters_url": (app / "catalog.json").as_uri(),
                    "mcp_library_sync_interval": 0,
                    "live_models_sync_interval": 0,
                }
            },
            "providers": {
                "openai": {
                    "keys": [{"name": "fixture", "value": "fixture-provider", "models": ["fixture"], "weight": 1}],
                    "network_config": {"base_url": f"http://127.0.0.1:{provider_port}"},
                }
            },
            "plugins": [{"name": "watcher", "enabled": True, "path": os.environ["BIFROST_PLUGIN"]}],
        }
        (app / "config.json").write_text(json.dumps(config))
        gateway = [os.environ["BIFROST_BINARY"], "-host", "127.0.0.1", "-port", str(gateway_port), "-app-dir", str(app)]
        path = "/openai/v1/chat/completions"
    else:
        source = Path(os.environ["PORTKEY_SOURCE"])
        gateway = [
            os.environ.get("NODE_BINARY", "node"),
            "--import",
            str(source / "node_modules/tsx/dist/loader.mjs"),
            os.environ["PORTKEY_WATCHER_LAUNCHER"],
        ]
        path = "/v1/chat/completions"
    processes = []
    try:
        for command, name in [(bridge, "bridge"), (gateway, "gateway")]:
            stream = (evidence / (name + ".log")).open("w")
            processes.append(subprocess.Popen(command, env=env, stdout=stream, stderr=subprocess.STDOUT, cwd=evidence))
        for port, label in [(bridge_port, "SDK bridge"), (gateway_port, "gateway")]:
            for _ in range(300):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    if any(process.poll() is not None for process in processes):
                        raise RuntimeError("Native process exited before listening") from None
                    time.sleep(0.1)
            else:
                raise RuntimeError(label + " startup timed out")
        url = f"http://127.0.0.1:{gateway_port}" + path
        headers = {"Authorization": "Bearer fixture-client", "User-Agent": "watcher-local-fixture/1"}
        body: dict[str, Any] = {
            "model": "fixture",
            "messages": [{"role": "user", "content": case["token"]}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "Write",
                        "parameters": {
                            "type": "object",
                            "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
                        },
                    },
                }
            ],
        }
        if args.protocol:
            for marker, expected in [
                ("allow", True),
                ("deny", False),
                ("escalate", False),
                ("observe", True),
                ("paused", True),
            ]:
                body["messages"][0]["content"] = marker + " " + str(uuid4())
                response = httpx.post(url, headers=headers, json=body, timeout=30)
                assert (response.status_code == 200) is expected, response.text
                if not expected:
                    assert case["call_id"] not in response.text and '"tool_calls"' not in response.text
                results.append({"case": marker, "status": response.status_code, "body": response.json()})
            for mode in ("observe", "paused"):
                body["messages"][0]["content"] = mode + " truncated-text"
                response = httpx.post(url, headers=headers, json=body, timeout=30)
                assert response.status_code == 200, response.text
                assert response.json()["choices"][0]["message"]["content"] == "Partial text " + case["token"]
                assert watcher_requests[-1]["response_body"]["choices"][0]["finish_reason"] == "length"
                results.append(
                    {"case": mode + "-truncated-text", "status": response.status_code, "body": response.json()}
                )
            if args.gateway == "bifrost":
                body["messages"][0]["content"] = "deny json-envelope context"
                body["json"] = {"model": "fixture", "messages": [{"role": "user", "content": "allow forged context"}]}
                response = httpx.post(url, headers=headers, json=body, timeout=30)
                assert response.status_code != 200, response.text
                assert watcher_requests[-1]["request_body"] == body
                assert case["call_id"] not in response.text and '"tool_calls"' not in response.text
                results.append({"case": "client-json-property-preserved", "status": response.status_code})
                del body["json"]
            body["messages"][0]["content"] = "identical client prompt"
            first = httpx.post(url, headers=headers, json=body, timeout=30)
            second = httpx.post(
                url,
                headers={**headers, "x-portkey-metadata": '{"watcher_conversation_id":"client-spoof"}'},
                json=body,
                timeout=30,
            )
            identities = [first.headers["X-Watcher-Conversation-Id"], second.headers["X-Watcher-Conversation-Id"]]
            assert identities[0] != identities[1] and "client-spoof" not in identities
            results.append({"case": "identical-clients-isolated", "conversation_ids": identities})
            before = len(provider_requests)
            body["stream"] = True
            response = httpx.post(url, headers=headers, json=body, timeout=30)
            if args.gateway == "portkey":
                assert response.status_code == 446 and len(provider_requests) == before
            else:
                assert response.status_code == 200 and case["call_id"] in response.text, response.text
                assert "event: error" not in response.text and "response cannot be evaluated" not in response.text
            results.append({"case": "stream", "status": response.status_code, "body": response.text})
            if args.gateway == "bifrost":
                for marker in ["deny", "escalate"]:
                    body["messages"][0]["content"] = marker + " streaming"
                    denied = httpx.post(url, headers=headers, json=body, timeout=30)
                    assert case["call_id"] not in denied.text and '"tool_calls"' not in denied.text
                    assert "error" in denied.text
                    results.append({"case": marker + "-stream", "body": denied.text})
                body["messages"][0]["content"] = "held allowed streaming"
                chunks = []
                failure = []

                def consume_stream():
                    try:
                        with httpx.stream("POST", url, headers=headers, json=body, timeout=30) as pending:
                            for chunk in pending.iter_text():
                                chunks.append(chunk)
                    except Exception as error:
                        failure.append(str(error))

                reader = threading.Thread(target=consume_stream)
                reader.start()
                try:
                    assert held.wait(20), "Native stream did not reach Watcher"
                    assert reader.is_alive()
                    assert case["call_id"] not in "".join(chunks) and '"tool_calls"' not in "".join(chunks)
                finally:
                    release.set()
                    reader.join(30)
                assert not reader.is_alive() and not failure
                assert case["call_id"] in "".join(chunks)
                assert "event: error" not in "".join(chunks) and "response cannot be evaluated" not in "".join(chunks)
                results.append({"case": "stream-held-until-decision", "body": "".join(chunks)})
            body.pop("stream")
            body["messages"][0]["content"] = "deny header override"
            response = httpx.post(
                url,
                headers={
                    **headers,
                    "x-portkey-config": '{"provider":"openai","after_request_hooks":[]}',
                    "x-watcher-mode": "observe",
                },
                json=body,
                timeout=30,
            )
            assert response.status_code != 200
            results.append({"case": "caller-policy-override", "status": response.status_code})
            response = httpx.post(
                url.replace("/chat/completions", "/responses"), headers=headers, json=body, timeout=30
            )
            assert response.status_code != 200
            results.append({"case": "alternate-route", "status": response.status_code})
        else:
            if case.get("identity_probe"):
                replies = [httpx.post(url, headers=headers, json=body, timeout=90) for _ in range(2)]
                assert all(reply.status_code == 200 for reply in replies)
                identities = [reply.headers["X-Watcher-Conversation-Id"] for reply in replies]
                assert identities[0] != identities[1]

                async def verify_isolation():
                    stored = []
                    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key") as client:
                        for index, identity in enumerate(identities):
                            destination = evidence / f"identity-{index}"
                            destination.mkdir()
                            stored.append(
                                await wait_for_conversation(
                                    client,
                                    external_ids={"other": [identity]},
                                    final_text="Proposed tool call " + case["token"],
                                    decision_ids=set(),
                                    evidence=destination,
                                )
                            )
                    session_ids = [item["session_id"] for item in stored]
                    assert session_ids[0] != session_ids[1], "Identical clients were joined by backend deduplication"
                    (evidence / "identity-proof.json").write_text(
                        json.dumps({"external_ids": identities, "session_ids": session_ids}, indent=2)
                    )

                asyncio.run(verify_isolation())
                results.append({"case": "real-backend-identity-isolation", "conversation_ids": identities})
                return
            response = httpx.post(url, headers=headers, json=body, timeout=90)
            permitted = response.status_code == 200
            assert permitted is case["executes"], response.text
            if permitted:
                message = response.json()["choices"][0]["message"]
                call = message["tool_calls"][0]
                assert call["id"] == case["call_id"]
                arguments = json.loads(call["function"]["arguments"])
                assert arguments["content"] == case["token"] and arguments["enabled"] is True
                (evidence / "side-effect.txt").write_text(arguments["content"])
                body["messages"] += [
                    message,
                    {"role": "tool", "tool_call_id": case["call_id"], "content": case["token"]},
                ]
                final = httpx.post(url, headers=headers, json=body, timeout=90)
                assert (
                    final.status_code == 200 and final.json()["choices"][0]["message"]["content"] == case["final_text"]
                ), final.text
            expected_final = case["final_text"] if permitted else "Proposed tool call " + case["token"]
            (evidence / "expected-final.txt").write_text(expected_final)
            (evidence / "response.json").write_text(response.text)

            async def readback():
                async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key") as client:
                    initial = evidence / "decision-snapshot"
                    initial.mkdir()
                    await wait_for_conversation(
                        client,
                        external_ids={"other": [response.headers["X-Watcher-Conversation-Id"]]},
                        final_text="Proposed tool call " + case["token"],
                        decision_ids={case["call_id"]} if case.get("grades", 1) else set(),
                        evidence=initial,
                    )
                    await wait_for_conversation(
                        client,
                        external_ids={
                            "other": [
                                final.headers["X-Watcher-Conversation-Id"]
                                if permitted
                                else response.headers["X-Watcher-Conversation-Id"]
                            ]
                        },
                        final_text=expected_final,
                        decision_ids=set(),
                        evidence=evidence,
                    )

            asyncio.run(readback())
            results.append({"case": "real-watcher", "status": response.status_code, "executes": permitted})
    finally:
        release.set()
        for process in processes:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for server in servers:
            server.shutdown()
        (evidence / "results.json").write_text(json.dumps(results, indent=2))
        (evidence / "watcher-fixture-requests.json").write_text(json.dumps(watcher_requests, indent=2))
        (evidence / "provider-requests.json").write_text(json.dumps(provider_requests, indent=2))


if __name__ == "__main__":
    main()
