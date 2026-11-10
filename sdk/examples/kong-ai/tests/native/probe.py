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
from watcher_kong_ai.alternatives import _TOO_LARGE, ALTERNATIVE_HEADER, marker_key, sign_marker
from watcher_kong_ai.notices import ALTERNATIVE_FAILED, SYSTEM_NOTICE

from watcher_sdk import AsyncWatcherClient, TrajectoryView

PROVIDER_PORT = 11866
BRIDGE_PORT = 11865
GATEWAY_PORT = 11867
WATCHER_PORT = 11864
BRIDGE_RECORDER_PORT = 11863
TYPED_PATH = "/typed/v1/chat/completions"
# A route whose plugin admits bodies up to LIMITED_BODY_BYTES: room for a
# noticed request and its continuation (the system notice alone is ~1.5 KB),
# but not for a reply that adds Watcher's notices to a near-limit response.
LIMITED_PATH = "/limited/v1/chat/completions"
LIMITED_BODY_BYTES = 16384
# Scripted responses for the size cases are this many bytes under the limit,
# so each fits on its own and only the composed replacement can exceed it.
LIMIT_MARGIN = 16
FINAL_TEXT = "Watcher stopped this. How should I proceed? A. skip it, B. do something else, C. ask an administrator."


def first_user_text(request: dict) -> str:
    """The client's scripted case marker; the gateway puts its system notice before it."""
    return next(message["content"] for message in request["messages"] if message["role"] == "user")


def is_continuation(request: dict) -> bool:
    """Whether the bridge built this request: its last tool result is a Watcher notice, not a client result."""
    last = request["messages"][-1]
    return last["role"] == "tool" and last["content"].startswith(("WATCHER", "This call did not run"))


def fill_to(payload: dict, size: int) -> None:
    """Lengthen ``payload``'s message text so its JSON encoding is exactly ``size`` bytes.

    Pads with ASCII, one byte per character, and leaves every other field as
    the ordinary fixture reply has it.
    """
    message = payload["choices"][0]["message"]
    missing = size - len(json.dumps(payload).encode())
    assert missing >= 0, missing
    message["content"] += "y" * missing


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
    # Hook requests that record a delivered replacement (they name withheld calls),
    # which the bridge sends after answering Kong, so they arrive at no fixed point.
    recordings: list[dict[str, Any]] = []
    # While set, the fixture Watcher holds each recording open until released.
    recording_hold, recording_release = threading.Event(), threading.Event()
    # Set while a held recording handler is waiting, so the main thread can tell it never timed out.
    recording_waiting = threading.Event()
    provider_headers: list[dict[str, str]] = []
    provider_response_bytes: list[int] = []
    held, release = threading.Event(), threading.Event()

    class Fixture(BaseHTTPRequestHandler):
        """Provide a local model and, only for protocol tests, scripted hook replies."""

        server: ThreadingHTTPServer

        def log_message(self, format: str, *_args: Any) -> None:
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.server.server_port == BRIDGE_RECORDER_PORT:
                exchange = {"path": self.path, "body": request}
                bridge_requests.append(exchange)
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
                # The bridge's reply is what the plugin checks, e.g. against its body limit.
                exchange["reply"] = data.decode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if self.server.server_port == WATCHER_PORT:
                if self.path == "/v1/auth/check-permissions":
                    payload = {"granted": True, "missing": []}
                elif request.get("withheld_tool_use_ids"):
                    if recording_hold.is_set():
                        recording_waiting.set()
                    recordings.append(request)
                    if recording_waiting.is_set():
                        recording_release.wait(20)
                        recording_waiting.clear()
                    payload = []
                else:
                    watcher_requests.append(request)
                    marker = first_user_text(request["request_body"])
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
                    refusal = "deny" if "deny" in marker else "escalate" if "escalate" in marker else "allow"
                    payload = []
                    for call in request["response_body"]["choices"][0]["message"].get("tool_calls") or []:
                        # The fixture policy refuses Write calls (every call for deny-all)
                        # and allows the Read alternative the provider fixture offers.
                        refused = call["function"]["name"] == "Write" or "deny-all" in marker
                        judgment = refusal if refused else "allow"
                        payload.append(
                            {
                                "tool_use_id": call["id"],
                                "decision_source": "bypass" if mode == "paused" else "rule",
                                "decision": "deferred" if mode != "enforce" else judgment,
                                "judged_decision": None if mode == "paused" else judgment,
                                "enforcement_mode": mode,
                                "verdict": {"explanation": "Fixture policy refuses this call"},
                                "latency_ms": 1,
                            }
                        )
            else:
                provider_requests.append(request)
                provider_headers.append({key.lower(): value for key, value in self.headers.items()})
                if is_continuation(request):
                    attempt = sum(message["role"] == "assistant" for message in request["messages"])
                    # Against the real Watcher the fixture answers a refusal with text only,
                    # so the backend suite grades exactly the client's original call.
                    if case.get("repeat_call_id") and attempt == 1:
                        # The refused Write again under a new ID: the bridge refuses it
                        # locally, without Watcher, and asks once more.
                        message = {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{**original_write(case), "id": case["repeat_call_id"]}],
                        }
                        finish = "tool_calls"
                    elif request.get("tool_choice") == "none" or not (
                        args.protocol or case.get("oversized_alternative")
                    ):
                        message = {"role": "assistant", "content": FINAL_TEXT}
                        finish = "stop"
                    else:
                        deny_all = "deny-all" in first_user_text(request)
                        message = {
                            "role": "assistant",
                            "content": f"Alternative {attempt}",
                            "tool_calls": [
                                {
                                    "id": f"{case['call_id']}-alternative-{attempt}",
                                    "type": "function",
                                    "function": {
                                        "name": "Write" if deny_all else "Read",
                                        "arguments": json.dumps({"file_path": f"attempt-{attempt}.txt"}),
                                    },
                                }
                            ],
                        }
                        finish = "tool_calls"
                elif any(message["role"] == "tool" for message in request["messages"]):
                    message = {"role": "assistant", "content": case["final_text"]}
                    finish = "stop"
                else:
                    message = {
                        "role": "assistant",
                        "content": "Proposed tool call " + case["token"],
                        "tool_calls": [original_write(case)],
                    }
                    if case.get("sibling_call_id"):
                        # A second call in the same proposal, withheld with the refused Write.
                        message["tool_calls"].append(
                            {
                                "id": case["sibling_call_id"],
                                "type": "function",
                                "function": {"name": "Read", "arguments": json.dumps({"file_path": "sibling.txt"})},
                            }
                        )
                    finish = "tool_calls"
                payload = {
                    "id": "completion-fixture",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "fixture",
                    "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
                    "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                }
                marker = first_user_text(request)
                oversized = "oversized-alternative" in marker or case.get("oversized_alternative")
                if (oversized and is_continuation(request)) or (
                    "oversized-original" in marker and not is_continuation(request)
                ):
                    fill_to(payload, LIMITED_BODY_BYTES - LIMIT_MARGIN)
            data = json.dumps(payload).encode()
            if self.server.server_port == PROVIDER_PORT:
                provider_response_bytes.append(len(data))
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
        # Two more ai-proxy routes on the same path, chosen by Host or by a
        # header predicate, each with its own provider key. An alternative
        # must return to the route (and so the provider key) the client used.
        for name, route in [
            ("tenant-host", {"hosts": ["tenant-b.test"]}),
            ("tenant-header", {"headers": {"x-tenant": ["c"]}}),
        ]:
            service = json.loads(json.dumps(config["services"][0]))
            service["name"] = name
            service["routes"][0] = {**service["routes"][0], "name": name, **route}
            service["plugins"][1]["config"]["auth"]["header_value"] = f"Bearer fixture-provider-{name}"
            config["services"].append(service)
        # A route reachable only with a JSON Content-Type: alternatives must
        # satisfy the predicate, and ordinary outcomes must not depend on it.
        typed = json.loads(json.dumps(config["services"][0]))
        typed["name"] = "typed-route"
        typed["routes"][0] = {
            **typed["routes"][0],
            "name": "typed-route",
            "paths": [f"~{TYPED_PATH}$"],
            "headers": {"content-type": ["application/json"]},
        }
        typed["plugins"][1]["config"]["auth"]["header_value"] = "Bearer fixture-provider-typed-route"
        typed["plugins"][2]["config"] = {**bridge_config, "chat_path": TYPED_PATH}
        config["services"].append(typed)
    if args.protocol or case.get("oversized_alternative"):
        # A route with a reduced plugin body limit, for replacements that would exceed it.
        limited = json.loads(json.dumps(config["services"][0]))
        limited["name"] = "limited-route"
        limited["routes"][0] = {**limited["routes"][0], "name": "limited-route", "paths": [f"~{LIMITED_PATH}$"]}
        limited["plugins"][1]["config"]["auth"]["header_value"] = "Bearer fixture-provider-limited-route"
        limited["plugins"][2]["config"] = {
            **bridge_config,
            "chat_path": LIMITED_PATH,
            "max_body_bytes": LIMITED_BODY_BYTES,
        }
        config["services"].append(limited)
    (root / "kong.yaml").write_text(json.dumps(config, indent=2))
    log = (root / "bridge.log").open("w")
    bridge = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "watcher_kong_ai.bridge",
            "serve",
            "--port",
            str(BRIDGE_PORT),
            "--gateway-url",
            f"http://127.0.0.1:{GATEWAY_PORT}",
        ],
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
        body: dict[str, Any] = {
            "model": "fixture",
            "messages": [{"role": "user", "content": case["token"]}],
            "tools": [
                {"type": "function", "function": {"name": "Write", "parameters": {"type": "object"}}},
                {"type": "function", "function": {"name": "Read", "parameters": {"type": "object"}}},
            ],
        }
        if args.protocol:
            notice = {"role": "system", "content": SYSTEM_NOTICE}
            typed_url = f"http://127.0.0.1:{GATEWAY_PORT}{TYPED_PATH}"
            for target, marker in [
                (target, marker) for target in (url, typed_url) for marker in ["allow", "observe deny", "paused"]
            ]:
                body["messages"][0]["content"] = marker
                before_provider, before_watcher = len(provider_requests), len(watcher_requests)
                response = httpx.post(target, headers=headers, json=body, timeout=30)
                assert response.status_code == 200, response.text
                assert len(watcher_requests) == before_watcher + 1
                expected_key = "Bearer fixture-provider" + ("-typed-route" if target == typed_url else "")
                assert provider_headers[-1]["authorization"] == expected_key
                assert response.json() == watcher_requests[-1]["response_body"], (
                    "Kong changed evaluated output before client delivery"
                )
                # The system notice reaches the provider through ai-proxy and Watcher's snapshot.
                assert len(provider_requests) == before_provider + 1
                assert provider_requests[-1]["messages"] == [notice, *body["messages"]]
                assert watcher_requests[-1]["request_body"] == {**body, "messages": [notice, *body["messages"]]}
                case_name = marker if target == url else f"typed-route-{marker}"
                results.append({"case": case_name, "status": response.status_code, "body": response.json()})

            def wait_for_recording(identity: str) -> dict[str, Any]:
                """The bridge's recording of the reply it delivered for ``identity``, once it arrives."""
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    matches = [item for item in recordings if item["external_ids"] == {"other": identity}]
                    if matches:
                        assert len(matches) == 1, matches
                        return matches[0]
                    time.sleep(0.05)
                raise AssertionError("The bridge did not record the delivered reply")

            def continuation_case(
                marker: str,
                provider_calls: int,
                graded: int,
                route_headers: dict[str, str] | None = None,
                provider_key: str = "Bearer fixture-provider",
                target: str = url,
            ) -> httpx.Response:
                """Send one refused request and check the nested requests went through Kong unmarked and ungraded.

                ``route_headers`` select a route sharing the path; every provider
                call, original and nested, must carry that route's ``provider_key``.
                """
                body["messages"][0]["content"] = marker
                before_provider, before_watcher, before_bridge = (
                    len(provider_requests),
                    len(watcher_requests),
                    len(bridge_requests),
                )
                response = httpx.post(target, headers={**headers, **(route_headers or {})}, json=body, timeout=60)
                assert response.status_code == 200, response.text
                assert provider_headers[before_provider]["authorization"] == provider_key
                assert response.headers["X-Watcher-Conversation-Id"].startswith("kong:")
                assert len(provider_requests) == before_provider + provider_calls, provider_requests[before_provider:]
                assert len(watcher_requests) == before_watcher + graded
                identity = response.headers["X-Watcher-Conversation-Id"]
                # Alternatives are graded in the client request's own session, declaring withheld refusals.
                for request in watcher_requests[before_watcher:]:
                    assert request["external_ids"] == {"other": identity}, request["external_ids"]
                    assert request["withholds_refused_calls"] is True
                recorded = wait_for_recording(identity)
                delivered_ids = {
                    call["id"] for call in response.json()["choices"][0]["message"].get("tool_calls") or []
                }
                assert recorded["withholds_refused_calls"] is True and recorded["withheld_tool_use_ids"]
                assert not delivered_ids & set(recorded["withheld_tool_use_ids"]), recorded["withheld_tool_use_ids"]
                paths = [item["path"] for item in bridge_requests[before_bridge:]]
                # One outer validate and evaluate; each nested pass only validates its marker.
                assert paths == ["/validate", "/evaluate"] + ["/validate"] * (provider_calls - 1), paths
                for item in bridge_requests[before_bridge + 2 :]:
                    assert "alternative_marker" in item["body"]
                for request, sent in zip(
                    provider_requests[before_provider + 1 :], provider_headers[before_provider + 1 :], strict=True
                ):
                    assert is_continuation(request)
                    assert ALTERNATIVE_HEADER not in sent and "apikey" not in sent, sent
                    # ai-proxy added the provider key and key-auth identified the original client.
                    assert sent["authorization"] == provider_key
                    assert sent["x-consumer-username"] == "fixture-client"
                    assert request["messages"].count(notice) == 1 and request["messages"][0] == notice
                return response

            # The client's reply completes while the bridge's recording of it is still held open.
            recording_hold.set()
            response = continuation_case("deny", provider_calls=2, graded=2)
            assert recording_waiting.is_set(), "the recording finished or timed out before the reply completed"
            recording_release.set()
            recording_hold.clear()
            message = response.json()["choices"][0]["message"]
            assert message["content"].startswith("Proposed tool call ")
            assert (
                "WATCHER NOTICE (added by Watcher, not written by the assistant): Watcher blocked `Write"
                in (message["content"])
            )
            assert [call["function"]["name"] for call in message["tool_calls"]] == ["Read"]
            assert response.json()["choices"][0]["finish_reason"] == "tool_calls"
            assert "Continue the user's task another way" in provider_requests[-1]["messages"][-1]["content"]
            assert provider_requests[-1].get("tool_choice") is None
            results.append({"case": "deny-then-alternative", "status": 200, "body": response.json()})

            response = continuation_case("escalate", provider_calls=2, graded=1)
            choice = response.json()["choices"][0]
            assert provider_requests[-1]["tool_choice"] == "none"
            assert "tool_calls" not in choice["message"] and choice["finish_reason"] == "stop"
            assert choice["message"]["content"].endswith(FINAL_TEXT)
            assert "WATCHER ESCALATION (added by Watcher" in choice["message"]["content"]
            assert "A. skip it, B. do something else" in provider_requests[-1]["messages"][-1]["content"]
            results.append({"case": "escalate-then-final-question", "status": 200, "body": response.json()})

            response = continuation_case("deny-all", provider_calls=4, graded=3)
            choice = response.json()["choices"][0]
            assert [request.get("tool_choice") for request in provider_requests[-4:]] == [None, None, None, "none"]
            assert "tool_calls" not in choice["message"] and choice["finish_reason"] == "stop"
            assert choice["message"]["content"].count("WATCHER NOTICE") == 3
            assert choice["message"]["content"].endswith(FINAL_TEXT)
            results.append({"case": "three-refusals-then-final-question", "status": 200, "body": response.json()})

            for name, selector in [("tenant-host", {"Host": "tenant-b.test"}), ("tenant-header", {"X-Tenant": "c"})]:
                response = continuation_case(
                    "deny",
                    provider_calls=2,
                    graded=2,
                    route_headers=selector,
                    provider_key=f"Bearer fixture-provider-{name}",
                )
                calls = response.json()["choices"][0]["message"]["tool_calls"]
                assert [call["function"]["name"] for call in calls] == ["Read"]
                results.append({"case": f"alternative-keeps-route-{name}", "status": 200})

            # The JSON Content-Type predicate is satisfied by the continuation too.
            response = continuation_case(
                "deny", provider_calls=2, graded=2, provider_key="Bearer fixture-provider-typed-route", target=typed_url
            )
            assert [call["function"]["name"] for call in response.json()["choices"][0]["message"]["tool_calls"]] == [
                "Read"
            ]
            results.append({"case": "alternative-keeps-route-typed-route", "status": 200})

            # A refusal inside requested structured output is an explicit error, with no alternative.
            body["messages"][0]["content"] = "deny"
            before_provider, before_watcher, before_bridge = (
                len(provider_requests),
                len(watcher_requests),
                len(bridge_requests),
            )
            response = httpx.post(
                url, headers=headers, json={**body, "response_format": {"type": "json_object"}}, timeout=30
            )
            assert response.status_code == 403, response.text
            assert response.json()["error"]["type"] == "watcher_withheld"
            assert response.headers["X-Watcher-Conversation-Id"].startswith("kong:")
            assert len(provider_requests) == before_provider + 1 and len(watcher_requests) == before_watcher + 1
            assert [item["path"] for item in bridge_requests[before_bridge:]] == ["/validate", "/evaluate"]
            results.append({"case": "structured-output-refusal", "status": 403, "body": response.json()})

            def sizes(exchanges: list[dict[str, Any]]) -> dict[str, int]:
                """Byte lengths of one limited-route exchange as the plugin measured them.

                The outer ``/evaluate`` holds the noticed request, the original
                response and the bridge's replacement; a later ``/validate``
                holds a continuation request exactly as Kong read it.
                """
                evaluate = next(item for item in exchanges if item["path"] == "/evaluate")
                assert evaluate["body"]["max_body_bytes"] == LIMITED_BODY_BYTES
                measured = {
                    "noticed_request": len(evaluate["body"]["request_json"].encode()),
                    "original_response": len(evaluate["body"]["response_json"].encode()),
                    "replacement": len(json.loads(evaluate["reply"])["response_json"].encode()),
                }
                for item in exchanges:
                    if "alternative_marker" in item["body"]:
                        measured["continuation_request"] = len(item["body"]["request_json"].encode())
                return measured

            # Each response fits the limited route, but the original's text, the
            # notice and the approved alternative together do not: the bridge
            # replaces them with the short notice and the fixed question.
            limited_url = f"http://127.0.0.1:{GATEWAY_PORT}{LIMITED_PATH}"
            before_bridge = len(bridge_requests)
            response = continuation_case(
                "deny oversized-alternative",
                provider_calls=2,
                graded=2,
                provider_key="Bearer fixture-provider-limited-route",
                target=limited_url,
            )
            measured = {
                **sizes(bridge_requests[before_bridge:]),
                "alternative_response": provider_response_bytes[-1],
                "limit": LIMITED_BODY_BYTES,
            }
            assert measured["alternative_response"] == LIMITED_BODY_BYTES - LIMIT_MARGIN, measured
            assert all(value <= LIMITED_BODY_BYTES for value in measured.values()), measured
            choice = response.json()["choices"][0]
            assert "tool_calls" not in choice["message"] and choice["finish_reason"] == "stop"
            assert choice["message"]["content"] == (
                f"Proposed tool call {case['token']}\n\n{_TOO_LARGE}\n\n{ALTERNATIVE_FAILED}"
            )
            assert len(response.content) <= LIMITED_BODY_BYTES
            results.append({"case": "oversized-reply-shortened-to-question", "status": 200, "bytes": measured})

            # A near-limit original keeps its text even in the short replacement,
            # so the plugin withholds the response whole. Its continuation (which
            # repeats that text) exceeds the limit too, so Kong refuses it before
            # the provider: one provider call and one Watcher submission.
            body["messages"][0]["content"] = "deny oversized-original"
            before_provider, before_watcher, before_bridge, before_recordings = (
                len(provider_requests),
                len(watcher_requests),
                len(bridge_requests),
                len(recordings),
            )
            response = httpx.post(limited_url, headers=headers, json=body, timeout=30)
            assert response.status_code == 403, response.text
            # The client never received the replacement, so the bridge does not record it as
            # delivered. A recording would follow the bridge's reply within milliseconds.
            time.sleep(2)
            assert len(recordings) == before_recordings, recordings[before_recordings:]
            assert response.json() == {"error": {"message": "Response withheld by Watcher"}}
            assert len(provider_requests) == before_provider + 1 and len(watcher_requests) == before_watcher + 1
            exchanges = bridge_requests[before_bridge:]
            assert [item["path"] for item in exchanges] == ["/validate", "/evaluate"]
            measured = {
                **sizes(exchanges),
                "original_sent": provider_response_bytes[-1],
                "limit": LIMITED_BODY_BYTES,
            }
            assert measured["original_sent"] == LIMITED_BODY_BYTES - LIMIT_MARGIN, measured
            assert measured["noticed_request"] <= LIMITED_BODY_BYTES, measured
            assert measured["original_response"] <= LIMITED_BODY_BYTES < measured["replacement"], measured
            # The bridge delivered a replacement, so the 403 is the plugin's size check, not a refusal.
            assert json.loads(exchanges[1]["reply"])["verdict"] is True
            original_text = json.loads(exchanges[1]["body"]["response_json"])["choices"][0]["message"]["content"]
            replacement = json.loads(json.loads(exchanges[1]["reply"])["response_json"])
            assert replacement["choices"][0]["message"]["content"] == (
                f"{original_text}\n\n{_TOO_LARGE}\n\n{ALTERNATIVE_FAILED}"
            )
            assert case["token"] not in response.text and case["call_id"] not in response.text
            results.append({"case": "oversized-replacement-withheld", "status": 403, "bytes": measured})

            body["messages"][0]["content"] = "deny"
            raw = json.dumps(body).encode()
            for name, forged in [
                ("malformed", "123.abc"),
                ("wrong-key", sign_marker(marker_key("not-the-watcher-key"), raw, int(time.time()) + 60)),
                ("expired", sign_marker(marker_key("fixture-key"), raw, int(time.time()) - 5)),
            ]:
                before_provider, before_watcher = len(provider_requests), len(watcher_requests)
                response = httpx.post(
                    url,
                    headers={**headers, "Content-Type": "application/json", ALTERNATIVE_HEADER: forged},
                    content=raw,
                    timeout=30,
                )
                assert response.status_code == 403, response.text
                assert response.json() == {"error": {"message": "Invalid Watcher alternative marker"}}
                assert len(provider_requests) == before_provider and len(watcher_requests) == before_watcher
                results.append({"case": f"forged-marker-{name}", "status": response.status_code})

            body["messages"][0]["content"] = "large-history:" + "x" * (64 * 1024)
            before = len(provider_requests)
            response = httpx.post(url, headers=headers, json=body, timeout=30)
            assert response.status_code == 200 and len(provider_requests) == before + 1, response.text
            assert provider_requests[-1]["messages"] == [notice, *body["messages"]]
            assert watcher_requests[-1]["request_body"] == {**body, "messages": [notice, *body["messages"]]}
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
            assert not thread.is_alive() and responses[0].status_code == 200
            # The held proposal never reached the client; only the approved alternative did.
            held_calls = responses[0].json()["choices"][0]["message"]["tool_calls"]
            assert [call["function"]["name"] for call in held_calls] == ["Read"]
            results.append({"case": "pending-response-withheld", "status": responses[0].status_code})
            plain_url = f"http://127.0.0.1:{GATEWAY_PORT}{plain_path}"
            body["messages"][0]["content"] = "deny"
            before_provider, before_bridge = len(provider_requests), len(bridge_requests)
            plain = httpx.post(plain_url, headers=headers, json=body, timeout=30)
            assert plain.status_code == 200, plain.text
            assert [call["function"]["name"] for call in plain.json()["choices"][0]["message"]["tool_calls"]] == [
                "Read"
            ]
            assert len(provider_requests) == before_provider + 2
            # The alternative went back through this same route, not the ai-proxy route.
            assert "authorization" not in provider_headers[-1]
            assert [item["path"] for item in bridge_requests[before_bridge:]] == ["/validate", "/evaluate", "/validate"]
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
            # An approved alternative near the limited route's limit makes the composed reply too
            # large, so the bridge drops it for the short notice and names its call as withheld.
            target = f"http://127.0.0.1:{GATEWAY_PORT}{LIMITED_PATH}" if case.get("oversized_alternative") else url
            response = httpx.post(target, headers=headers, json=body, timeout=90)
            assert response.status_code == 200, response.text
            # A refusal is delivered as Watcher's notice and the model's text, without the call.
            permitted = bool(response.json()["choices"][0]["message"].get("tool_calls"))
            assert permitted is case["executes"], response.text
            if not permitted:
                content = response.json()["choices"][0]["message"]["content"]
                assert content.startswith("Proposed tool call " + case["token"] + "\n\nWATCHER "), content
                assert content.endswith(ALTERNATIVE_FAILED if case.get("oversized_alternative") else FINAL_TEXT), (
                    content
                )
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
            # A refusal's delivered reply is recorded by the bridge after it answers
            # Kong, naming every withheld call, so readback waits for that reply.
            expected_final = case["final_text"] if permitted else response.json()["choices"][0]["message"]["content"]
            withheld = {case["call_id"], *([case["sibling_call_id"]] if case.get("sibling_call_id") else [])}
            if case.get("oversized_alternative"):
                withheld.add(f"{case['call_id']}-alternative-1")
            (root / "expected-final.txt").write_text(expected_final)
            (root / "response.json").write_text(response.text)

            async def readback():
                async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key") as client:
                    initial = root / "decision-snapshot"
                    initial.mkdir()
                    # A refused proposal stays in the gateway, so its judgment is stored on a
                    # proposal branch beside the reply the client actually received.
                    await wait_for_conversation(
                        client,
                        external_ids={"other": [response.headers["X-Watcher-Conversation-Id"]]},
                        final_text="Proposed tool call " + case["token"],
                        decision_ids={case["call_id"]} if case.get("grades", 1) else set(),
                        evidence=initial,
                        includes_branches=True,
                    )
                    await wait_for_conversation(
                        client,
                        external_ids={"other": [final.headers["X-Watcher-Conversation-Id"]]},
                        final_text=expected_final,
                        decision_ids=set(),
                        evidence=root,
                        withheld_ids=set() if permitted else withheld,
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
        (root / "provider-headers.json").write_text(json.dumps(provider_headers, indent=2))
        (root / "watcher-fixture-requests.json").write_text(json.dumps(watcher_requests, indent=2))
        (root / "watcher-fixture-recordings.json").write_text(json.dumps(recordings, indent=2))
        (root / "bridge-requests.json").write_text(json.dumps(bridge_requests, indent=2))


def original_write(case: dict[str, Any]) -> dict[str, Any]:
    """The client's original Write proposal, the call every refusal case is about."""
    arguments = {"file_path": "sentinel.txt", "content": case["token"], "enabled": True, "ratio": 1.0}
    return {
        "id": case["call_id"],
        "type": "function",
        "function": {"name": "Write", "arguments": json.dumps(arguments)},
    }


async def wait_for_conversation(
    client: AsyncWatcherClient,
    *,
    external_ids: dict[str, list[str]],
    final_text: str | None,
    decision_ids: set[str],
    evidence: Path,
    withheld_ids: frozenset[str] | set[str] = frozenset(),
    includes_branches: bool = False,
    timeout: float = 15,
) -> dict[str, Any]:
    """Return one exact stored session's extended trajectory, or fail by deadline.

    Only the session's latest trajectory is considered unless ``includes_branches``
    is set; then any of its trajectories may match, such as a proposal branch the
    gateway recorded before replacing a refused call.

    External ID filters must identify one native conversation. Ambiguous matches
    fail immediately. An empty decision set supports paused/transcript-only runs;
    it does not claim they produced tool judgments. A null final_text is for an aborted native run with no final answer; it asserts only the selected decisions. ``withheld_ids`` must all be listed as calls a gateway withheld in favor of a message on the trajectory. Callers separately compare
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
            if includes_branches:
                listed = await client.list_trajectories(item["session_id"])
                trajectory_ids = [trajectory.trajectory_id for trajectory in listed.trajectories]
            else:
                trajectory_ids = [item["latest_trajectory_id"]] if item["latest_trajectory_id"] is not None else []
            for trajectory_id in trajectory_ids:
                response = await client.get_trajectory(item["session_id"], trajectory_id, view=TrajectoryView.EXTENDED)
                stored = response.to_dict()
                (evidence / "trajectory.json").write_text(json.dumps(stored, indent=2))
                has_final = any(
                    message.get("role") == "assistant" and message.get("content") == final_text
                    for message in stored["messages"]
                )
                withheld = {entry["tool_use_id"] for entry in stored.get("gateway_withheld_decisions") or []}
                if (
                    (has_final or final_text is None)
                    and decision_ids <= stored["tool_call_decisions"].keys()
                    and withheld_ids <= withheld
                ):
                    return stored
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(
                "The exact final transcript and tool decisions did not become readable through the SDK"
            )
        await asyncio.sleep(0.05)


if __name__ == "__main__":
    main()
