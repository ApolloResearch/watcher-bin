"""Run ordinary clients through an installed LiteLLM proxy and its Watcher callback.

Run inside a network-disabled fixture container with only loopback services.
--protocol supplies local Watcher replies; --case uses the real Watcher relay.
Neither mode connects to a model provider outside the local namespace.
Client requests supply x-watcher-session-id, the callback's explicit grouping
contract. Tool execution follows the delivered response body: a refused call
arrives as an ordinary text response with every tool call removed.
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
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
from litellm.types.utils import ModelResponseStream
from watcher_litellm.callback import SESSION_PREFIX
from watcher_litellm.streams import assemble

from watcher_sdk import AsyncWatcherClient, TrajectoryView

PROVIDER_PORT = 11866
GATEWAY_PORT = 11867
WATCHER_PORT = 11864


def wait_for_port(port: int, deadline: float) -> None:
    """Wait for a private fixture listener, bounded by a monotonic deadline."""
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"Listener {port} did not become ready")


def stream_events(response: httpx.Response) -> list[dict[str, Any]]:
    """Read the actual client-visible SSE events, rejecting a hidden error tail."""
    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line[6:] != "[DONE]"
    ]
    assert events and not any("error" in event for event in events), response.text
    assert "data: [DONE]" in response.text, response.text
    return events


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
            "final_text": "Completed LiteLLM test " + str(uuid4()),
            "executes": True,
        }
    )
    provider_requests, watcher_requests, client_requests, results = [], [], [], []
    client_request_headers, client_responses = [], []
    held, release = threading.Event(), threading.Event()

    class Fixture(BaseHTTPRequestHandler):
        """Provide a local model and, only for protocol tests, scripted hook replies."""

        server: ThreadingHTTPServer

        def log_message(self, format: str, *_args: Any) -> None:
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
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
                request_token = (
                    request["messages"][0]["content"] if case.get("harness_identity_probe") else case["token"]
                )
                if any(message["role"] == "tool" for message in request["messages"]):
                    message = {"role": "assistant", "content": case["final_text"]}
                    finish = "stop"
                else:
                    message = {
                        "role": "assistant",
                        "content": "Proposed tool call " + request_token,
                        "tool_calls": [
                            {
                                "id": case["call_id"],
                                "type": "function",
                                "function": {
                                    "name": "Write",
                                    "arguments": json.dumps(
                                        {
                                            "file_path": "sentinel.txt",
                                            "content": request_token,
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
                if request.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    delta: dict[str, Any] = dict(message)
                    calls = delta.get("tool_calls")
                    if calls:
                        calls[0]["index"] = 0
                        arguments = calls[0]["function"]["arguments"]
                        calls[0]["function"]["arguments"] = arguments[:8]
                        pieces = [delta, {"tool_calls": [{"index": 0, "function": {"arguments": arguments[8:]}}]}]
                    else:
                        pieces = [delta]
                    for piece in pieces:
                        chunk = {
                            **{key: value for key, value in payload.items() if key != "usage"},
                            "object": "chat.completion.chunk",
                            "choices": [{"index": 0, "delta": piece, "finish_reason": None}],
                        }
                        self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                        self.wfile.flush()
                    chunk = {
                        **{key: value for key, value in payload.items() if key != "usage"},
                        "object": "chat.completion.chunk",
                        "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                    }
                    self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                    if request.get("stream_options", {}).get("include_usage"):
                        usage_chunk = {**payload, "object": "chat.completion.chunk", "choices": []}
                        self.wfile.write(("data: " + json.dumps(usage_chunk) + "\n\n").encode())
                    self.wfile.write(b"data: [DONE]\n\n")
                    return
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    servers = []
    for port in [PROVIDER_PORT] + ([WATCHER_PORT] if args.protocol else []):
        server = ThreadingHTTPServer(("127.0.0.1", port), Fixture)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
    env = dict(
        os.environ,
        WATCHER_API_URL=f"http://127.0.0.1:{WATCHER_PORT}" if args.protocol else os.environ["WATCHER_URL"],
        WATCHER_API_KEY="fixture-key",
        LITELLM_MODE="PRODUCTION",
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        DO_NOT_TRACK="1",
    )
    config = {
        "model_list": [
            {
                "model_name": "fixture",
                "litellm_params": {
                    "model": "openai/fixture",
                    "api_key": "fixture-provider",
                    "api_base": f"http://127.0.0.1:{PROVIDER_PORT}/v1",
                },
            }
        ],
        "litellm_settings": {"callbacks": "watcher_litellm.callback.watcher_callback", "telemetry": False},
        "general_settings": {"master_key": "sk-fixture-client", "disable_spend_logs": True},
    }
    (root / "litellm.yaml").write_text(json.dumps(config, indent=2))
    log = (root / "gateway.log").open("w")
    gateway = subprocess.Popen(
        [
            str(Path(sys.executable).parent / "litellm"),
            "--config",
            str(root / "litellm.yaml"),
            "--host",
            "127.0.0.1",
            "--port",
            str(GATEWAY_PORT),
        ],
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_for_port(GATEWAY_PORT, time.monotonic() + 60)
        url = f"http://127.0.0.1:{GATEWAY_PORT}/v1/chat/completions"
        client_session_id = str(uuid4())
        headers = {"Authorization": "Bearer sk-fixture-client", "X-Watcher-Session-Id": client_session_id}
        body: dict[str, Any] = {
            "model": "fixture",
            "messages": [{"role": "user", "content": case["token"]}],
            "tools": [{"type": "function", "function": {"name": "Write", "parameters": {"type": "object"}}}],
        }

        def post_client(target, *, headers, json, timeout=30):
            """Retain exactly what the ordinary client supplied before proxy mutation."""
            payload = deepcopy(json)
            if target == url:
                client_requests.append(payload)
            response = httpx.post(target, headers=headers, json=payload, timeout=timeout)
            if target == url:
                client_request_headers.append(dict(response.request.headers))
                client_responses.append(
                    {"status": response.status_code, "headers": dict(response.headers), "body": response.text}
                )
            return response

        if args.protocol:
            for marker, released in [
                ("allow", True),
                ("deny", False),
                ("escalate", False),
                ("observe deny", True),
                ("paused", True),
            ]:
                body["messages"][0]["content"] = marker
                response = post_client(url, headers=headers, json=body, timeout=30)
                assert response.status_code == 200, response.text
                message = response.json()["choices"][0]["message"]
                assert bool(message.get("tool_calls")) is released, response.text
                if not released:
                    assert "Watcher withheld the proposed tool call" in message["content"]
                results.append({"case": marker, "status": response.status_code, "body": response.json()})
            body["messages"][0]["content"] = "identical prompt"
            ids = [str(uuid4()), str(uuid4())]
            for session_id in ids:
                response = post_client(
                    url, headers={**headers, "X-Watcher-Session-Id": session_id}, json=body, timeout=30
                )
                assert response.status_code == 200, response.text
                assert watcher_requests[-1]["external_ids"] == {"other": SESSION_PREFIX + session_id}
                assert watcher_requests[-1]["request_body"] == {
                    **body,
                    "litellm_session_id": session_id,
                    "litellm_trace_id": session_id,
                }
            results.append({"case": "explicit-session-identities", "ids": ids})
            body["messages"][0]["content"] = "no session header"
            before = len(watcher_requests)
            response = post_client(url, headers={"Authorization": "Bearer sk-fixture-client"}, json=body, timeout=30)
            assert response.status_code == 200, response.text
            assert response.json()["choices"][0]["message"]["tool_calls"][0]["id"] == case["call_id"]
            assert "x-watcher-session-id" not in client_request_headers[-1]
            assert len(watcher_requests) == before + 1
            assert watcher_requests[-1]["request_body"] == client_requests[-1]
            assert "external_ids" not in watcher_requests[-1]
            results.append({"case": "no-session-header", "status": response.status_code})
            for marker in ("allow", "deny", "escalate", "observe deny", "paused"):
                body["messages"][0]["content"] = marker
                response = post_client(url, headers=headers, json={**body, "stream": True}, timeout=30)
                released = marker in ("allow", "observe deny", "paused")
                events = stream_events(response)
                calls = [
                    call
                    for event in events
                    for choice in event.get("choices") or []
                    for call in choice.get("delta", {}).get("tool_calls") or []
                ]
                assert bool(calls) is released, response.text
                if released:
                    assert {call["id"] for call in calls} == {case["call_id"]}
                    assert any(
                        choice["finish_reason"] == "tool_calls" for event in events for choice in event["choices"]
                    )
                else:
                    assert "Watcher withheld the proposed tool call" in response.text
                results.append({"case": marker + "-stream", "status": response.status_code, "body": response.text})
            body["messages"][0]["content"] = "allow usage"
            usage_body = {**body, "stream": True, "stream_options": {"include_usage": True}}
            response = post_client(url, headers=headers, json=usage_body, timeout=30)
            assert response.status_code == 200, response.text
            events = [
                json.loads(line[6:])
                for line in response.text.splitlines()
                if line.startswith("data: ") and line[6:] != "[DONE]"
            ]
            expected_usage = {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15}
            assert events and "usage" in events[-1], response.text
            for key, value in expected_usage.items():
                assert events[-1]["usage"][key] == watcher_requests[-1]["response_body"]["usage"][key] == value
            results.append({"case": "stream-final-usage", "status": response.status_code, "body": response.text})
            body["messages"][0]["content"] = "malformed exchange"
            response = post_client(url, headers=headers, json=body, timeout=30)
            assert response.status_code == 422, response.text
            results.append({"case": "permanent-watcher-rejection", "status": response.status_code})
            before = (len(provider_requests), len(watcher_requests))
            rejected = post_client(url, headers={"Authorization": "Bearer wrong"}, json=body)
            assert rejected.status_code in (400, 401, 403), rejected.text
            assert (len(provider_requests), len(watcher_requests)) == before
            results.append({"case": "invalid-client-key", "status": rejected.status_code})
            body["messages"][0]["content"] = "held deny"
            responses = []
            thread = threading.Thread(
                target=lambda: responses.append(post_client(url, headers=headers, json=body, timeout=30))
            )
            thread.start()
            assert held.wait(20)
            assert not responses
            release.set()
            thread.join(timeout=20)
            assert not thread.is_alive() and responses[0].status_code == 200
            held_message = responses[0].json()["choices"][0]["message"]
            assert not held_message.get("tool_calls")
            assert "Watcher withheld the proposed tool call" in held_message["content"]
            results.append({"case": "pending-response-withheld", "status": responses[0].status_code})
            for submitted in watcher_requests:
                actual = submitted["request_body"]
                assert actual["model"] == "fixture", actual
                # LiteLLM 1.101 copies x-watcher-session-id through its generic
                # vendor-session-header scan and requests usage for every stream.
                # Derive expected additions only from what the client sent.
                candidates = []
                for sent, sent_headers in zip(client_requests, client_request_headers, strict=True):
                    expected = dict(sent)
                    if "x-watcher-session-id" in sent_headers:
                        session_id = sent_headers["x-watcher-session-id"]
                        expected.update(litellm_session_id=session_id, litellm_trace_id=session_id)
                    if sent.get("stream") and "stream_options" not in sent:
                        expected.update(stream_options={"include_usage": True}, _litellm_strip_stream_usage=True)
                    candidates.append(expected)
                assert actual in candidates, actual
            results.append({"case": "client-request-keys-and-alias", "checked": len(watcher_requests)})
            servers[-1].shutdown()
            servers[-1].server_close()
            assert post_client(url, headers=headers, json=body, timeout=15).status_code == 503
            results.append({"case": "watcher-outage-withheld", "status": 503})
        elif case.get("harness_identity_probe"):
            native_id = str(UUID(case["native_thread_id"]))
            headers["User-Agent"] = "codex-tui/1.0"
            body["client_metadata"] = {"thread_id": native_id}
            client_session_ids, session_ids, stored_other_ids, client_markers = [], [], [], []

            async def inspect_harness_grouping():
                """Wait for each distinct client transcript before reading its selected session."""
                async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key") as client:
                    for index in range(2):
                        request = deepcopy(body)
                        marker = f"{case['token']}:client:{index}"
                        request["messages"][0]["content"] = marker
                        explicit_id = str(uuid4())
                        response = post_client(
                            url, headers={**headers, "X-Watcher-Session-Id": explicit_id}, json=request, timeout=90
                        )
                        assert response.status_code == 200, response.text
                        client_session_ids.append(explicit_id)
                        client_markers.append(marker)
                        target = root / f"identity-{index}"
                        target.mkdir()
                        await wait_for_conversation(
                            client,
                            external_ids={"openai-codex": [native_id]},
                            final_text="Proposed tool call " + marker,
                            decision_ids=set(),
                            evidence=target,
                        )
                        sessions = json.loads((target / "sessions.json").read_text())["sessions"]
                        assert len(sessions) == 1
                        session_ids.append(sessions[0]["session_id"])
                        stored_other_ids.append(sessions[0]["external_ids"].get("other"))

            asyncio.run(inspect_harness_grouping())
            proof = {
                "native_thread_id": native_id,
                "client_session_ids": client_session_ids,
                "session_ids": session_ids,
                "stored_other_ids": stored_other_ids,
                "client_markers": client_markers,
            }
            (root / "identity-proof.json").write_text(json.dumps(proof, indent=2))
            assert len(set(client_session_ids)) == 2 and len(set(session_ids)) == 1, proof
            assert not (root / "side-effect.txt").exists()
            results.append({"case": "recognized-harness-grouping", **proof})
        else:
            streamed = bool(case.get("stream"))
            if streamed:
                body.update(stream=True, stream_options={"include_usage": True})
            initial_request = deepcopy(body)
            response = post_client(url, headers=headers, json=body, timeout=90)
            assert response.status_code == 200, response.text
            if streamed:
                events = stream_events(response)
                initial_response = assemble("chat_completions", [ModelResponseStream(**event) for event in events])
                (root / "response.sse").write_text(response.text)
                (root / "stream-events.json").write_text(json.dumps(events, indent=2))
                (root / "assembled-response.json").write_text(json.dumps(initial_response, indent=2))
                expected_usage = {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15}
                for name, value in expected_usage.items():
                    assert events[-1]["usage"][name] == initial_response["usage"][name] == value
            else:
                initial_response = response.json()
            message = initial_response["choices"][0]["message"]
            permitted = bool(message.get("tool_calls"))
            assert permitted is case["executes"], response.text
            final = response
            if permitted:
                assert isinstance(initial_response, dict)
                call = message["tool_calls"][0]
                arguments = json.loads(call["function"]["arguments"])
                assert call["id"] == case["call_id"]
                assert arguments["enabled"] is True and type(arguments["ratio"]) is float
                (root / "side-effect.txt").write_text(arguments["content"])
                body["messages"] += [
                    message,
                    {"role": "tool", "tool_call_id": case["call_id"], "content": case["token"]},
                ]
                final = post_client(url, headers=headers, json=body, timeout=90)
                assert final.status_code == 200, final.text
                final_body = (
                    assemble("chat_completions", [ModelResponseStream(**event) for event in stream_events(final)])
                    if streamed
                    else final.json()
                )
                assert final_body["choices"][0]["message"]["content"] == case["final_text"], final.text
            else:
                assert "Watcher withheld the proposed tool call" in message["content"]
            expected_final = case["final_text"] if permitted else "Proposed tool call " + case["token"]
            (root / "expected-final.txt").write_text(expected_final)
            (root / "response.json").write_text(
                json.dumps(initial_response, indent=2) if streamed and permitted else response.text
            )

            async def readback():
                async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key") as client:
                    initial = root / "decision-snapshot"
                    initial.mkdir()
                    await wait_for_conversation(
                        client,
                        external_ids={"other": [SESSION_PREFIX + client_session_id]},
                        final_text="Proposed tool call " + case["token"],
                        decision_ids={case["call_id"]} if case.get("grades", 1) else set(),
                        evidence=initial,
                    )
                    await wait_for_conversation(
                        client,
                        external_ids={"other": [SESSION_PREFIX + client_session_id]},
                        final_text=expected_final,
                        decision_ids=set(),
                        evidence=root,
                    )
                    if case.get("direct_assembly_probe"):
                        assert streamed and permitted and initial_response is not None
                        direct_ids = {"other": "litellm-direct:" + str(uuid4())}
                        arguments = {
                            "request_body": initial_request,
                            "response_body": initial_response,
                            "url": "/v1/chat/completions",
                            "provider": "litellm-direct-assembly",
                            "external_ids": direct_ids,
                            "ephemeral": True,
                            "force_regrade": True,
                        }
                        (root / "direct-assembly-sdk-arguments.json").write_text(json.dumps(arguments, indent=2))
                        outputs = await client.pre_tool_use_hook(
                            request_body=initial_request,
                            response_body=initial_response,
                            url="/v1/chat/completions",
                            provider="litellm-direct-assembly",
                            external_ids=direct_ids,
                            ephemeral=True,
                            force_regrade=True,
                        )
                        outcomes = [output.to_dict() for output in outputs]
                        (root / "direct-assembly-response.json").write_text(json.dumps(outcomes, indent=2))
                        assert len(outcomes) == 1
                        assert outcomes[0]["tool_use_id"] == case["call_id"] and outcomes[0]["decision"] == "allow"

            asyncio.run(readback())
            results.append({"case": "real-watcher", "status": response.status_code, "executes": permitted})
    finally:
        release.set()
        gateway.terminate()
        try:
            gateway.wait(timeout=10)
        except subprocess.TimeoutExpired:
            gateway.kill()
            gateway.wait()
        log.close()
        for server in servers:
            server.shutdown()
            server.server_close()
        (root / "results.json").write_text(json.dumps(results, indent=2))
        (root / "provider-requests.json").write_text(json.dumps(provider_requests, indent=2))
        (root / "watcher-fixture-requests.json").write_text(json.dumps(watcher_requests, indent=2))
        (root / "client-requests.json").write_text(json.dumps(client_requests, indent=2))
        (root / "client-request-headers.json").write_text(json.dumps(client_request_headers, indent=2))
        (root / "client-responses.json").write_text(json.dumps(client_responses, indent=2))


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
