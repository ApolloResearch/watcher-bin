"""Run ordinary clients through installed Kong, its native plugin and the SDK.

Run inside a network-disabled fixture container. A Kong companion shares only
that container's network namespace. It starts after companion-ready is written.
--protocol supplies local Watcher replies; --case uses the real Watcher relay.
Neither mode connects to a model provider outside the local namespace.
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

from watcher_sdk import AsyncWatcherClient, TrajectoryView

PROVIDER_PORT = 11866
BRIDGE_PORT = 11865
GATEWAY_PORT = 11867
WATCHER_PORT = 11864
BRIDGE_RECORDER_PORT = 11863


def wait_for_port(port: int, deadline: float) -> None:
    """Wait for a private fixture listener, bounded by a monotonic deadline."""
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"Listener {port} did not become ready")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--case", type=Path)
    parser.add_argument("--protocol", action="store_true")
    args = parser.parse_args()
    if bool(args.case) == args.protocol:
        parser.error("Choose --protocol or --case")
    root = args.evidence
    root.mkdir(parents=True, exist_ok=True)
    case: dict[str, Any] = (
        json.loads(args.case.read_text())
        if args.case
        else {
            "call_id": "call-" + str(uuid4()),
            "token": "marker-" + str(uuid4()),
            "final_text": "Completed Kong test " + str(uuid4()),
            "executes": True,
        }
    )
    provider_requests, watcher_requests, bridge_requests, results = [], [], [], []
    held, release = threading.Event(), threading.Event()

    class Fixture(BaseHTTPRequestHandler):
        """Provide a local model and, only for protocol tests, scripted hook replies."""

        server: ThreadingHTTPServer

        def log_message(self, format: str, *_args: Any) -> None:
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.server.server_port == BRIDGE_RECORDER_PORT:
                bridge_requests.append({"path": self.path, "body": request})
                try:
                    response = httpx.post(
                        f"http://127.0.0.1:{BRIDGE_PORT}{self.path}",
                        json=request,
                        headers={"Authorization": self.headers.get("Authorization", "")},
                        timeout=30,
                    )
                    status, data = response.status_code, response.content
                except httpx.RequestError:
                    status, data = 503, b'{"error":"fixture bridge unavailable"}'
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if self.server.server_port == WATCHER_PORT:
                if self.path == "/v1/auth/check-permissions":
                    payload = {"granted": True, "missing": []}
                else:
                    watcher_requests.append(request)
                    marker = request["request_body"]["messages"][0]["content"]
                    if "held" in marker:
                        held.set()
                        assert release.wait(20), "Pending decision was never released"
                    if marker == "malformed exchange":
                        error_body = json.dumps(
                            {"detail": [{"loc": ["body"], "msg": "malformed_exchange", "type": "value_error"}]}
                        ).encode()
                        self.send_response(422)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(error_body)))
                        self.end_headers()
                        self.wfile.write(error_body)
                        return
                    mode = "observe" if "observe" in marker else "paused" if "paused" in marker else "enforce"
                    judgment = "deny" if "deny" in marker else "escalate" if "escalate" in marker else "allow"
                    payload = [
                        {
                            "tool_use_id": call["id"],
                            "decision_source": "bypass" if mode == "paused" else "rule",
                            "decision": "deferred" if mode != "enforce" else judgment,
                            "judged_decision": None if mode == "paused" else judgment,
                            "enforcement_mode": mode,
                            "verdict": {},
                            "latency_ms": 1,
                        }
                        for index, call in enumerate(
                            request["response_body"]["choices"][0]["message"].get("tool_calls") or []
                        )
                    ]
            else:
                provider_requests.append(request)
                if any(message["role"] == "tool" for message in request["messages"]):
                    message = {"role": "assistant", "content": case["final_text"]}
                    finish = "stop"
                else:
                    message = {
                        "role": "assistant",
                        "content": "Proposed tool call " + case["token"],
                        "tool_calls": [
                            {
                                "id": case["call_id"],
                                "type": "function",
                                "function": {
                                    "name": "Write",
                                    "arguments": json.dumps(
                                        {
                                            "file_path": "sentinel.txt",
                                            "content": case["token"],
                                            "enabled": True,
                                            "ratio": 1.0,
                                        }
                                    ),
                                },
                            }
                        ],
                    }
                    finish = "tool_calls"
                payload = {
                    "id": "completion-fixture",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "fixture",
                    "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
                    "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                }
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    servers = []
    for port in [PROVIDER_PORT] + ([WATCHER_PORT, BRIDGE_RECORDER_PORT] if args.protocol else []):
        server = ThreadingHTTPServer(("127.0.0.1", port), Fixture)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
    env = dict(
        os.environ,
        WATCHER_BASE_URL=f"http://127.0.0.1:{WATCHER_PORT}" if args.protocol else os.environ["WATCHER_URL"],
        WATCHER_API_KEY="fixture-key",
        WATCHER_BRIDGE_TOKEN="fixture-bridge",
    )
    bridge_config = {
        "bridge_url": f"http://127.0.0.1:{BRIDGE_RECORDER_PORT if args.protocol else BRIDGE_PORT}",
        "bridge_token": "fixture-bridge",
    }
    config = {
        "_format_version": "3.0",
        "services": [
            {
                "name": "monitored-chat",
                "url": f"http://127.0.0.1:{PROVIDER_PORT}",
                "routes": [
                    {"name": "chat", "paths": ["~/v1/chat/completions$"], "methods": ["POST"], "strip_path": False}
                ],
                "plugins": [
                    {"name": "key-auth", "config": {"key_names": ["apikey"], "hide_credentials": True}},
                    {
                        "name": "ai-proxy",
                        "config": {
                            "route_type": "llm/v1/chat",
                            "response_streaming": "deny",
                            "max_request_body_size": 8 * 1024 * 1024,
                            "auth": {"header_name": "Authorization", "header_value": "Bearer fixture-provider"},
                            "model": {
                                "provider": "openai",
                                "name": "fixture",
                                "options": {"upstream_url": f"http://127.0.0.1:{PROVIDER_PORT}/v1/chat/completions"},
                            },
                        },
                    },
                    {
                        "name": "watcher",
                        "config": bridge_config,
                    },
                ],
            }
        ],
        "consumers": [{"username": "fixture-client", "keyauth_credentials": [{"key": "fixture-client"}]}],
    }
    plain_path = "/no-ai-proxy/v1/chat/completions"
    if args.protocol:
        # This deliberately incomplete route proves refusal belongs to Watcher,
        # independent of errors from the required production ai-proxy plugin.
        config["services"].append(
            {
                "name": "upgrade-guard-fixture",
                "url": f"http://127.0.0.1:{PROVIDER_PORT}",
                "routes": [
                    {"name": "plain-chat", "paths": [f"~{plain_path}$"], "methods": ["POST"], "strip_path": False}
                ],
                "plugins": [
                    {"name": "key-auth", "config": {"key_names": ["apikey"], "hide_credentials": True}},
                    {"name": "watcher", "config": {**bridge_config, "chat_path": plain_path}},
                ],
            }
        )
    (root / "kong.yaml").write_text(json.dumps(config, indent=2))
    log = (root / "bridge.log").open("w")
    bridge = subprocess.Popen(
        [sys.executable, "-m", "watcher_kong_ai.bridge", "serve", "--port", str(BRIDGE_PORT)],
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_for_port(BRIDGE_PORT, time.monotonic() + 30)
        (root / "companion-ready").touch()
        url = f"http://127.0.0.1:{GATEWAY_PORT}/v1/chat/completions"
        # A listening socket does not prove the gateway has loaded its routes.
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                ready = httpx.get(url, timeout=0.5)
                if ready.status_code == 404 and ready.headers.get("server", "").startswith("kong/"):
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.1)
        else:
            raise TimeoutError("Kong did not serve its routing response")
        headers = {"apikey": "fixture-client"}
        body = {
            "model": "fixture",
            "messages": [{"role": "user", "content": case["token"]}],
            "tools": [{"type": "function", "function": {"name": "Write", "parameters": {"type": "object"}}}],
        }
        if args.protocol:
            for marker, expected in [
                ("allow", 200),
                ("deny", 403),
                ("escalate", 403),
                ("observe deny", 200),
                ("paused", 200),
            ]:
                body["messages"][0]["content"] = marker
                response = httpx.post(url, headers=headers, json=body, timeout=30)
                assert response.status_code == expected, response.text
                if marker == "allow":
                    assert response.json() == watcher_requests[-1]["response_body"], (
                        "Kong changed evaluated output before client delivery"
                    )
                results.append({"case": marker, "status": response.status_code, "body": response.json()})
            body["messages"][0]["content"] = "large-history:" + "x" * (64 * 1024)
            before = len(provider_requests)
            response = httpx.post(url, headers=headers, json=body, timeout=30)
            assert response.status_code == 200 and len(provider_requests) == before + 1, response.text
            assert provider_requests[-1]["messages"][0]["content"] == body["messages"][0]["content"]
            assert watcher_requests[-1]["request_body"] == body
            assert response.json() == watcher_requests[-1]["response_body"]
            results.append(
                {
                    "case": "large-spooled-history",
                    "request_bytes": len(json.dumps(body).encode()),
                    "status": response.status_code,
                }
            )
            body["messages"][0]["content"] = "malformed exchange"
            response = httpx.post(url, headers=headers, json=body, timeout=30)
            assert response.status_code == 403, response.text
            results.append({"case": "permanent-watcher-rejection", "status": response.status_code})
            body["messages"][0]["content"] = "identical prompt"
            first = httpx.post(url, headers=headers, json=body, timeout=30)
            second = httpx.post(url, headers={**headers, "X-Watcher-Conversation-Id": "spoof"}, json=body, timeout=30)
            ids = [first.headers["X-Watcher-Conversation-Id"], second.headers["X-Watcher-Conversation-Id"]]
            assert ids[0] != ids[1] and "spoof" not in ids
            results.append({"case": "distinct-identities", "ids": ids})
            before = len(provider_requests)
            response = httpx.post(url, headers=headers, json={**body, "stream": True}, timeout=30)
            assert response.status_code == 422 and len(provider_requests) == before, response.text
            results.append({"case": "stream-rejected-before-model", "status": response.status_code})
            assert (
                httpx.post(url.replace("/chat/completions", "/responses"), headers=headers, json=body).status_code
                == 404
            )
            assert httpx.post(url, headers={"apikey": "wrong"}, json=body).status_code == 401
            body["messages"][0]["content"] = "held deny"
            responses = []
            thread = threading.Thread(
                target=lambda: responses.append(httpx.post(url, headers=headers, json=body, timeout=30))
            )
            thread.start()
            assert held.wait(20)
            assert not responses
            release.set()
            thread.join(timeout=20)
            assert not thread.is_alive() and responses[0].status_code == 403
            results.append({"case": "pending-response-withheld", "status": responses[0].status_code})
            plain_url = f"http://127.0.0.1:{GATEWAY_PORT}{plain_path}"
            body["messages"][0]["content"] = "deny"
            before_provider, before_bridge = len(provider_requests), len(bridge_requests)
            plain = httpx.post(plain_url, headers=headers, json=body, timeout=30)
            assert plain.status_code == 403, plain.text
            assert len(provider_requests) == before_provider + 1
            assert [item["path"] for item in bridge_requests[before_bridge:]] == ["/validate", "/evaluate"]
            results.append({"case": "plain-fixture-route-is-gated", "status": plain.status_code})
            upgrade_results: list[dict[str, Any]] = []
            for route, target in [("ai-proxy", url), ("without-ai-proxy", plain_url)]:
                for name, upgrade_headers in [
                    ("websocket", [("Upgrade", "websocket"), ("Connection", "Upgrade")]),
                    ("mixed-case", [("uPgRaDe", "WeBsOcKeT"), ("cOnNeCtIoN", "uPgRaDe")]),
                    ("without-connection", [("Upgrade", "websocket")]),
                    ("other-protocol", [("Upgrade", "h2c"), ("Connection", "Upgrade")]),
                    ("duplicate-websocket-first", [("Upgrade", "websocket"), ("upgrade", "h2c")]),
                    ("duplicate-websocket-last", [("Upgrade", "h2c"), ("upgrade", "websocket")]),
                    ("comma-list", [("Upgrade", "websocket, h2c")]),
                    ("empty", [("Upgrade", "")]),
                ]:
                    sent_headers = [*headers.items(), *upgrade_headers]
                    before_provider, before_bridge = len(provider_requests), len(bridge_requests)
                    try:
                        response = httpx.post(target, headers=sent_headers, json=body, timeout=30)
                        wire = {
                            "status": response.status_code,
                            "response_headers": dict(response.headers),
                            "body": response.text,
                            "transport_error": None,
                        }
                    except httpx.RequestError as error:
                        wire = {
                            "status": None,
                            "response_headers": {},
                            "body": "",
                            "transport_error": f"{type(error).__name__}: {error}",
                        }
                    upgrade_results.append(
                        {
                            "case": f"upgrade-{route}-{name}",
                            "request_headers": sent_headers,
                            **wire,
                            "provider_requests": len(provider_requests) - before_provider,
                            "bridge_paths": [item["path"] for item in bridge_requests[before_bridge:]],
                        }
                    )
                    (root / "upgrade-results.json").write_text(json.dumps(upgrade_results, indent=2))
            for result in upgrade_results:
                assert result["status"] == 400, result
                assert json.loads(result["body"]) == {
                    "error": {"message": "Protocol upgrades are unsupported on this route"}
                }, result
                assert result["provider_requests"] == 0 and result["bridge_paths"] == [], result
                assert case["call_id"] not in result["body"] and "tool_calls" not in result["body"], result
                results.append(result)
            bridge.terminate()
            bridge.wait(timeout=10)
            assert httpx.post(url, headers=headers, json=body, timeout=15).status_code == 503
            results.append({"case": "bridge-outage-withheld", "status": 503})
        else:
            response = httpx.post(url, headers=headers, json=body, timeout=90)
            permitted = response.status_code == 200
            assert permitted is case["executes"], response.text
            final = response
            if permitted:
                message = response.json()["choices"][0]["message"]
                call = message["tool_calls"][0]
                arguments = json.loads(call["function"]["arguments"])
                assert call["id"] == case["call_id"]
                assert arguments["enabled"] is True and type(arguments["ratio"]) is float
                (root / "side-effect.txt").write_text(arguments["content"])
                body["messages"] += [
                    message,
                    {"role": "tool", "tool_call_id": case["call_id"], "content": case["token"]},
                ]
                final = httpx.post(url, headers=headers, json=body, timeout=90)
                assert (
                    final.status_code == 200 and final.json()["choices"][0]["message"]["content"] == case["final_text"]
                ), final.text
            expected_final = case["final_text"] if permitted else "Proposed tool call " + case["token"]
            (root / "expected-final.txt").write_text(expected_final)
            (root / "response.json").write_text(response.text)

            async def readback():
                async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key") as client:
                    initial = root / "decision-snapshot"
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
                        external_ids={"other": [final.headers["X-Watcher-Conversation-Id"]]},
                        final_text=expected_final,
                        decision_ids=set(),
                        evidence=root,
                    )

            asyncio.run(readback())
            results.append({"case": "real-watcher", "status": response.status_code, "executes": permitted})
    finally:
        release.set()
        bridge.terminate()
        try:
            bridge.wait(timeout=10)
        except subprocess.TimeoutExpired:
            bridge.kill()
            bridge.wait()
        log.close()
        for server in servers:
            server.shutdown()
            server.server_close()
        (root / "results.json").write_text(json.dumps(results, indent=2))
        (root / "provider-requests.json").write_text(json.dumps(provider_requests, indent=2))
        (root / "watcher-fixture-requests.json").write_text(json.dumps(watcher_requests, indent=2))
        (root / "bridge-requests.json").write_text(json.dumps(bridge_requests, indent=2))


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
