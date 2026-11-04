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
    A decision counts when the trajectory shows its call or lists it among the
    calls the gateway withheld in favour of a delivered message.
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
                decided = stored["tool_call_decisions"].keys() | {
                    withheld["tool_use_id"] for withheld in stored.get("gateway_withheld_decisions") or []
                }
                if (has_final or final_text is None) and decision_ids <= decided:
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


def first_user_text(messages: list[dict[str, Any]]) -> str:
    """The client's prompt, which selects each fixture's behaviour; system notices come before it."""
    return next(message["content"] for message in messages if message["role"] == "user")


def sse_events(text: str) -> list[Any]:
    """Decode every SSE data event, requiring valid JSON and a final [DONE]."""
    data = [line[len("data: ") :] for line in text.splitlines() if line.startswith("data: ")]
    assert data and data[-1] == "[DONE]", "stream did not end with [DONE]"
    return [json.loads(item) for item in data[:-1]]


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
    provider_headers = []
    watcher_requests = []
    # Recordings of delivered replacements, kept apart from gradings: they arrive
    # after the reply, and every one names the calls it withheld.
    recordings = []
    results = []
    held = threading.Event()
    release = threading.Event()
    provider_port, watcher_port, bridge_port, gateway_port = [available_port() for _ in range(4)]
    alternative_id = "alternative-" + str(uuid4())

    class Fixture(BaseHTTPRequestHandler):
        """Serve deterministic provider responses; optionally emulate hook transport.

        The client's prompt selects behaviour. Watcher: ``deny-first`` refuses only
        the client's original call; ``escalate`` escalates, from a grader when the
        prompt says ``approvable``. Provider: a continuation for a prompt naming
        ``alternative`` proposes a different call unless tool choice is ``none``,
        which yields the final question; other continuations return final text.
        """

        server: ThreadingHTTPServer

        def log_message(self, format: str, *_args: Any) -> None:
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.server.server_port == watcher_port and self.path == "/v1/auth/check-permissions":
                data = {"granted": True, "missing": []}
            elif self.server.server_port == watcher_port:
                (recordings if "withheld_tool_use_ids" in body else watcher_requests).append(body)
                assert body["format"] == "raw"
                assert body["user_agent"] == "watcher-local-fixture/1"
                assert body["provider"] == "openai"
                text = first_user_text(body["request_body"]["messages"])
                if "held" in text:
                    held.set()
                    if not release.wait(20):
                        raise RuntimeError("Held fixture was not released")
                mode = "observe" if "observe" in text else "paused" if "paused" in text else "enforce"

                def judged(call: dict[str, Any]) -> str:
                    if "deny-first" in text:
                        return "deny" if call["id"] == case["call_id"] else "allow"
                    if "deny" in text or mode == "observe":
                        return "deny"
                    return "escalate" if "escalate" in text else "allow"

                source = "policy_gateway" if "approvable" in text else "rule"
                data = [
                    {
                        "decision": "deferred" if mode != "enforce" else judged(call),
                        "judged_decision": judged(call) if mode != "paused" else None,
                        "decision_source": "bypass" if mode == "paused" else source,
                        "enforcement_mode": mode,
                        "tool_use_id": call["id"],
                        "verdict": {"explanation": "Fixture policy"},
                        "latency_ms": 1,
                    }
                    for index, call in enumerate(body["response_body"]["choices"][0]["message"].get("tool_calls") or [])
                ]
            else:
                provider_requests.append(body)
                provider_headers.append({key.lower(): value for key, value in self.headers.items()})
                text = first_user_text(body["messages"])
                if "truncated-text" in text:
                    message = {"role": "assistant", "content": "Partial text " + case["token"]}
                    finish = "length"
                elif body.get("tool_choice") == "none":
                    message = {
                        "role": "assistant",
                        "content": "Final question "
                        + case["token"]
                        + ": should I A. allow this call, B. skip it, or C. do something else?",
                    }
                    finish = "stop"
                elif any(message["role"] == "tool" for message in body["messages"]) and "alternative" in text:
                    message = {
                        "role": "assistant",
                        "content": "Alternative text " + case["token"],
                        "tool_calls": [
                            {
                                "id": alternative_id,
                                "type": "function",
                                "function": {"name": "Read", "arguments": json.dumps({"file_path": "alt.txt"})},
                            }
                        ],
                    }
                    finish = "tool_calls"
                elif case.get("repeat_id") and sum(bool(m.get("tool_calls")) for m in body["messages"]) == 1:
                    # The first alternative repeats the refused Write under a new ID,
                    # with a new sibling; the gateway refuses it without grading.
                    message = {
                        "role": "assistant",
                        "content": "Trying again " + case["token"],
                        "tool_calls": [
                            {
                                "id": case["repeat_id"],
                                "type": "function",
                                "function": {
                                    "name": "Write",
                                    "arguments": json.dumps(
                                        {"file_path": "sentinel.txt", "content": case["token"], "enabled": True}
                                    ),
                                },
                            },
                            {
                                "id": case["repeat_sibling_id"],
                                "type": "function",
                                "function": {"name": "Read", "arguments": json.dumps({"file_path": "other.txt"})},
                            },
                        ],
                    }
                    finish = "tool_calls"
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
                    if case.get("sibling_id"):
                        # A second call in the same proposal: withheld with the refused one.
                        message["tool_calls"].append(
                            {
                                "id": case["sibling_id"],
                                "type": "function",
                                "function": {"name": "Read", "arguments": json.dumps({"file_path": "sibling.txt"})},
                            }
                        )
                    finish = "tool_calls"
                if "oversized-buffered" in text:
                    message["content"] = "x" * (8 * 1024 * 1024 + 1)
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
        env["WATCHER_TEST_BRIDGE_MODULE"] = "watcher_bifrost.bridge"
        env["WATCHER_TEST_CAPTURE_DIR"] = str(evidence / "bridge-exchanges")
        env["WATCHER_GATEWAY_URL"] = f"http://127.0.0.1:{gateway_port}"
        bridge = [
            sys.executable,
            str(Path(__file__).with_name("bridge_capture.py")),
            "serve",
            "--port",
            str(bridge_port),
            "--allow-buffered-stream",
        ]
        app = evidence / "bifrost-config"
        app.mkdir()
        (app / "catalog.json").write_text("{}")
        config = {
            # The allowlist makes Bifrost forward these client headers upstream, so
            # the probe can show the alternative marker is blanked before the provider.
            "client": {
                "enable_logging": False,
                "allow_direct_keys": True,
                "header_filter_config": {"allowlist": ["x-watcher-alternative", "x-probe-forwarded"]},
            },
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
                    "keys": [
                        {"name": "fixture", "value": "fixture-provider", "models": ["fixture"], "weight": 1},
                        {"name": "selected", "value": "selected-provider", "models": ["fixture"], "weight": 1},
                        {"name": "third", "value": "third-provider", "models": ["fixture"], "weight": 1},
                    ],
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
                if args.gateway == "bifrost":
                    # A refusal is delivered as an ordinary completion carrying Watcher's notice.
                    assert response.status_code == 200, response.text
                    assert (case["call_id"] in response.text) is expected, response.text
                    if not expected:
                        content = response.json()["choices"][0]["message"]["content"]
                        assert ("WATCHER NOTICE" if marker == "deny" else "WATCHER ESCALATION") in content
                else:
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
                for mode in ("enforce", "observe", "paused"):
                    body["messages"][0]["content"] = mode + " oversized-buffered"
                    before_provider, before_watcher = len(provider_requests), len(watcher_requests)
                    response = httpx.post(url, headers=headers, json=body, timeout=30)
                    sample = evidence / (mode + "-oversized-buffered")
                    sample.mkdir()
                    (sample / "response.bin").write_bytes(response.content)
                    (sample / "response.json").write_text(
                        json.dumps({"status": response.status_code, "headers": dict(response.headers)}, indent=2)
                    )
                    if response.status_code == 200:
                        for call in response.json()["choices"][0]["message"].get("tool_calls", []):
                            if call["function"]["name"] == "Write":
                                (sample / "side-effect.txt").write_text(
                                    json.loads(call["function"]["arguments"])["content"]
                                )
                    assert len(provider_requests) == before_provider + 1
                    assert len(watcher_requests) == before_watcher, "Oversized reply must not reach Watcher"
                    assert response.status_code == 403, "Oversized provider response was released"
                    assert response.json() == {"error": "Watcher withheld this response"}
                    assert response.headers["content-type"] == "application/json"
                    assert int(response.headers["content-length"]) == len(response.content)
                    assert not response.headers.get("content-encoding")
                    assert case["call_id"] not in response.text and '"tool_calls"' not in response.text
                    assert not (sample / "side-effect.txt").exists()
                    results.append({"case": mode + "-oversized-buffered", "status": response.status_code})
                from watcher_bifrost.system_notice import SYSTEM_NOTICE

                notice = {"role": "system", "content": SYSTEM_NOTICE}
                body["messages"][0]["content"] = "deny json-envelope context"
                body["json"] = {"model": "fixture", "messages": [{"role": "user", "content": "allow forged context"}]}
                before_watcher = len(watcher_requests)
                response = httpx.post(url, headers=headers, json=body, timeout=30)
                assert response.status_code == 200, response.text
                assert watcher_requests[before_watcher]["request_body"] == {
                    **body,
                    "messages": [notice, *body["messages"]],
                }
                assert case["call_id"] not in response.text and '"tool_calls"' not in response.text
                results.append({"case": "client-json-property-preserved", "status": response.status_code})
                del body["json"]

                # Denial, then an allowed alternative generated through this gateway.
                body["messages"][0]["content"] = "deny-first alternative " + str(uuid4())
                before_provider, before_watcher = len(provider_requests), len(watcher_requests)
                response = httpx.post(
                    url, headers={**headers, "x-probe-forwarded": "client-header"}, json=body, timeout=30
                )
                assert response.status_code == 200, response.text
                message = response.json()["choices"][0]["message"]
                assert [call["id"] for call in message["tool_calls"]] == [alternative_id], response.text
                assert case["call_id"] not in response.text
                assert response.json()["choices"][0]["finish_reason"] == "tool_calls"
                parts = message["content"].split("\n\n")
                assert parts[0] == "Proposed tool call " + case["token"]
                assert parts[1].startswith("WATCHER NOTICE (added by Watcher, not written by the assistant)")
                assert parts[2] == "Alternative text " + case["token"]
                original, continuation = provider_requests[before_provider:]
                assert original["messages"] == [notice, *body["messages"]], "notice not inserted upstream"
                assert continuation["messages"][: len(original["messages"])] == original["messages"]
                assert continuation["messages"][-1]["role"] == "tool"
                assert continuation["messages"][-1]["tool_call_id"] == case["call_id"]
                assert continuation["messages"][-1]["content"].startswith("WATCHER NOTICE: Watcher blocked this call.")
                assert not continuation.get("stream"), "alternatives are requested buffered"
                client_headers, nested_headers = provider_headers[before_provider:]
                assert client_headers.get("x-probe-forwarded") == "client-header", "allowlist did not forward"
                assert not nested_headers.get("x-watcher-alternative"), "marker reached the provider"
                # Exactly two gradings: the client's proposal and the alternative, never the nested pass.
                graded = watcher_requests[before_watcher:]
                assert len(graded) == 2
                # Both are graded in the client's session and declare that refused calls are withheld.
                conversation = response.headers["X-Watcher-Conversation-Id"]
                assert [request["external_ids"]["other"] for request in graded] == [conversation, conversation]
                assert all(request["withholds_refused_calls"] is True for request in graded)
                # After the reply, the bridge records it in the same session, naming the refused
                # call; the delivered call moves into history behind an empty response.
                deadline = time.monotonic() + 10
                while not any(item["external_ids"]["other"] == conversation for item in recordings):
                    assert time.monotonic() < deadline, "the delivered reply was not recorded"
                    time.sleep(0.05)
                (recorded,) = [item for item in recordings if item["external_ids"]["other"] == conversation]
                assert recorded["withheld_tool_use_ids"] == [case["call_id"]]
                assert recorded["withholds_refused_calls"] is True
                assert recorded["response_body"]["choices"][0]["message"] == {"role": "assistant", "content": None}
                carried = recorded["request_body"]["messages"][-1]
                assert carried["content"] == message["content"]
                assert [call["id"] for call in carried["tool_calls"]] == [alternative_id]
                # Watcher grades the bridge's continuation; Bifrost re-encodes what the
                # provider receives (omitting stream=false and null fields).
                history = graded[1]["request_body"]
                assert history["stream"] is False
                assert [(m["role"], m.get("content")) for m in history["messages"]] == [
                    (m["role"], m.get("content")) for m in continuation["messages"]
                ]
                results.append({"case": "denial-then-alternative", "body": response.json()})

                # Escalation a grader made: one final text-only generation asking the user.
                body["messages"][0]["content"] = "escalate approvable " + str(uuid4())
                before_provider, before_watcher = len(provider_requests), len(watcher_requests)
                response = httpx.post(url, headers=headers, json=body, timeout=30)
                assert response.status_code == 200, response.text
                choice = response.json()["choices"][0]
                assert "tool_calls" not in choice["message"] and choice["finish_reason"] == "stop"
                assert "needs the user's decision before it can run" in choice["message"]["content"]
                # The final reply asks in its own words, so no second question follows it.
                assert choice["message"]["content"].endswith(
                    "Final question "
                    + case["token"]
                    + ": should I A. allow this call, B. skip it, or C. do something else?"
                )
                assert len(provider_requests) == before_provider + 2 and len(watcher_requests) == before_watcher + 1
                final = provider_requests[-1]
                assert final["tool_choice"] == "none"
                assert "A. allow this call, B. skip it, C. do something else." in final["messages"][-1]["content"]
                results.append({"case": "escalation-final-question", "body": response.json()})

                # A client's direct key or stored-key selection also selects the alternative's key.
                for mode, extra, expected_key in [
                    (
                        "direct-key",
                        {"Authorization": "Bearer direct-provider-key", "x-bf-direct-key": "true"},
                        "direct-provider-key",
                    ),
                    ("stored-key-selection", {"x-bf-api-key": "selected"}, "selected-provider"),
                ]:
                    body["messages"][0]["content"] = "deny-first alternative " + mode
                    before_provider, before_watcher = len(provider_requests), len(watcher_requests)
                    response = httpx.post(url, headers={**headers, **extra}, json=body, timeout=30)
                    assert response.status_code == 200, response.text
                    calls = response.json()["choices"][0]["message"]["tool_calls"]
                    assert [call["id"] for call in calls] == [alternative_id], response.text
                    keys = [item.get("authorization") for item in provider_headers[before_provider:]]
                    assert keys == ["Bearer " + expected_key] * 2, keys
                    assert len(watcher_requests) == before_watcher + 2
                    results.append({"case": mode + "-alternative", "provider_keys": len(keys)})

                # A session bound to one of several eligible keys keeps it for the alternative:
                # an allowed request binds the session to whichever key served it, then a
                # denial's original and alternative must both use that key. Three sessions
                # per header make a lucky match without forwarding unlikely (1 in 27).
                for session_header in ("x-bf-session-id", "x-claude-code-session-id"):
                    for _ in range(3):
                        session = {session_header: "session-" + str(uuid4())}
                        body["messages"][0]["content"] = "allow session binding " + str(uuid4())
                        before_provider = len(provider_requests)
                        bound = httpx.post(url, headers={**headers, **session}, json=body, timeout=30)
                        assert bound.status_code == 200 and case["call_id"] in bound.text, bound.text
                        (key,) = [item.get("authorization") for item in provider_headers[before_provider:]]
                        body["messages"][0]["content"] = "deny-first alternative session " + str(uuid4())
                        before_provider, before_watcher = len(provider_requests), len(watcher_requests)
                        response = httpx.post(url, headers={**headers, **session}, json=body, timeout=30)
                        calls = response.json()["choices"][0]["message"]["tool_calls"]
                        assert [call["id"] for call in calls] == [alternative_id], response.text
                        keys = [item.get("authorization") for item in provider_headers[before_provider:]]
                        assert keys == [key, key], (session_header, key, keys)
                        assert len(watcher_requests) == before_watcher + 2
                    results.append({"case": session_header + "-binding-kept"})

                # A refusal in a structured-output request is an explicit error, without an alternative.
                body["messages"][0]["content"] = "deny-first alternative structured " + str(uuid4())
                body["response_format"] = {"type": "json_object"}
                before_provider, before_watcher = len(provider_requests), len(watcher_requests)
                response = httpx.post(url, headers=headers, json=body, timeout=30)
                del body["response_format"]
                assert response.status_code == 403, response.text
                assert response.json() == {
                    "error": {
                        "message": "Watcher refused a tool call in this response, and its notice cannot be "
                        "delivered inside the requested structured output format",
                        "type": "watcher_withheld",
                        "code": 403,
                    }
                }
                assert len(provider_requests) == before_provider + 1 and len(watcher_requests) == before_watcher + 1
                results.append({"case": "structured-output-refusal", "status": response.status_code})

                # A client cannot forge the marker that skips grading.
                body["messages"][0]["content"] = "allow forged marker"
                before_provider, before_watcher = len(provider_requests), len(watcher_requests)
                response = httpx.post(
                    url,
                    headers={**headers, "X-Watcher-Alternative": "9999999999." + "0" * 64},
                    json=body,
                    timeout=30,
                )
                assert response.status_code == 403, response.text
                assert len(provider_requests) == before_provider and len(watcher_requests) == before_watcher
                results.append({"case": "forged-marker-rejected", "status": response.status_code})
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
                for marker, label in [
                    ("deny", "WATCHER NOTICE"),
                    ("escalate", "WATCHER ESCALATION"),
                    ("deny-first alternative", "WATCHER NOTICE"),
                ]:
                    body["messages"][0]["content"] = marker + " streaming"
                    denied = httpx.post(url, headers=headers, json=body, timeout=30)
                    assert denied.status_code == 200, denied.text
                    assert case["call_id"] not in denied.text and "event: error" not in denied.text
                    events = sse_events(denied.text)
                    deltas = [choice["delta"] for event in events for choice in event.get("choices", [])]
                    text = "".join(delta.get("content") or "" for delta in deltas)
                    calls = [call for delta in deltas for call in delta.get("tool_calls") or []]
                    assert label in text, denied.text
                    if marker == "deny-first alternative":
                        assert [call["id"] for call in calls] == [alternative_id]
                        assert text.endswith("Alternative text " + case["token"])
                    else:
                        assert calls == []
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
            if args.gateway == "bifrost":
                assert response.status_code == 200 and case["call_id"] not in response.text, response.text
                assert "WATCHER NOTICE" in response.json()["choices"][0]["message"]["content"]
            else:
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
            # A refusal is an ordinary completion carrying Watcher's notice and no original call.
            assert response.status_code == 200, response.text
            delivered = response.json()["choices"][0]["message"].get("tool_calls") or []
            permitted = any(call["id"] == case["call_id"] for call in delivered)
            assert permitted is case["executes"], response.text
            if not permitted:
                assert "WATCHER" in response.json()["choices"][0]["message"]["content"], response.text
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
            # A refused proposal's replacement is recorded after it is delivered,
            # so the session ends with exactly the text the client received.
            expected_final = case["final_text"] if permitted else response.json()["choices"][0]["message"]["content"]
            (evidence / "expected-final.txt").write_text(expected_final)
            (evidence / "response.json").write_text(response.text)

            async def readback():
                async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key") as client:
                    initial = evidence / "decision-snapshot"
                    initial.mkdir()
                    # A refused proposal's text is replaced once the delivered
                    # reply is recorded, so only its decisions are awaited.
                    await wait_for_conversation(
                        client,
                        external_ids={"other": [response.headers["X-Watcher-Conversation-Id"]]},
                        final_text="Proposed tool call " + case["token"] if permitted else None,
                        decision_ids=(
                            {case["call_id"], *([case["sibling_id"]] if case.get("sibling_id") else [])}
                            if case.get("grades", 1)
                            else set()
                        ),
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
        (evidence / "watcher-fixture-recordings.json").write_text(json.dumps(recordings, indent=2))
        (evidence / "provider-requests.json").write_text(json.dumps(provider_requests, indent=2))
        (evidence / "provider-headers.json").write_text(json.dumps(provider_headers, indent=2))


if __name__ == "__main__":
    main()
