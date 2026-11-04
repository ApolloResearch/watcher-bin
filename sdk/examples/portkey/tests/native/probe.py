"""Exercise an installed gateway with a local model and a real or fixture Watcher.

Set WATCHER_URL to the isolated real Watcher relay and provide --case for backend
verification. Without it, --protocol runs only protocol fixtures and makes no
claim about Watcher persistence. No model-provider connection leaves loopback.

For Portkey, --protocol also drives denial continuation through the real
launcher: the provider fixture answers a refused proposal's continuation with
an alternative call, or with a question to the user when the continuation
forbids tool calls, and records the headers each request carried.
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
    fail immediately. A decision counts when the trajectory shows its call or
    lists it among the calls a gateway withheld in favour of one of its
    messages (``gateway_withheld_decisions``). An empty decision set supports paused/transcript-only runs;
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
                withheld = {decision["tool_use_id"] for decision in stored.get("gateway_withheld_decisions") or []}
                decided = stored["tool_call_decisions"].keys() | withheld
                if (has_final or final_text is None) and decision_ids <= decided:
                    return stored
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(
                "The exact final transcript and tool decisions did not become readable through the SDK"
            )
        await asyncio.sleep(0.05)


def user_text(messages: list[dict[str, Any]]) -> str:
    """The first user message's text: the fixtures' scenario markers live there.

    Portkey inserts Watcher's system notice ahead of it, so it is not always
    the first message.
    """
    return next(message["content"] for message in messages if message["role"] == "user")


def available_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return candidate.getsockname()[1]


def portkey_continuation(
    url: str,
    headers: dict[str, str],
    template: dict[str, Any],
    case: dict[str, Any],
    provider_requests: list[dict[str, Any]],
    provider_headers: list[dict[str, str]],
    watcher_requests: list[dict[str, Any]],
    watcher_recordings: list[dict[str, Any]],
    evidence: Path,
) -> list[dict[str, Any]]:
    """Drive notices, alternatives, the final question and the loopback marker through the real launcher.

    Each scenario counts what the provider and Watcher fixtures received for
    that one client request, so a nested pass graded twice, a missing
    continuation or a marker reaching the provider fails the run. The bridge
    records each composed reply in the background after delivering it; those
    recordings (the only Watcher requests naming withheld calls) are kept
    apart in ``watcher_recordings`` so they never shift the counts. The raw
    client-visible replies whose ``hook_results`` are checked are kept in
    ``evidence``.
    """
    from watcher_portkey.alternatives import ALTERNATIVE_HEADER, marker_key, sign_marker
    from watcher_portkey.system_notice import SYSTEM_NOTICE

    results: list[dict[str, Any]] = []
    notice = {"role": "system", "content": SYSTEM_NOTICE}
    # The fixture's final reply asks the user itself, so no stop notice follows it.
    final_question = "FINAL-QUESTION " + case["token"] + ": shall I skip the write?"

    def send(text: str) -> tuple[httpx.Response, list[dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]]:
        body = json.loads(json.dumps(template))
        body["messages"][0]["content"] = text
        before = (len(provider_requests), len(watcher_requests))
        response = httpx.post(url, headers=headers, json=body, timeout=60)
        assert response.status_code == 200, response.text
        return response, provider_requests[before[0] :], provider_headers[before[0] :], watcher_requests[before[1] :]

    def recording(response: httpx.Response) -> dict[str, Any]:
        """Wait for the background recording of ``response``'s composed reply, matched by conversation ID."""
        conversation = response.headers["X-Watcher-Conversation-Id"]
        for _ in range(200):
            found = [item for item in watcher_recordings if item["external_ids"]["other"] == conversation]
            if found:
                assert len(found) == 1, found
                return found[0]
            time.sleep(0.05)
        raise AssertionError("The composed reply was not recorded")

    def tool_ids(response: httpx.Response) -> list[str]:
        return [call["id"] for call in response.json()["choices"][0]["message"].get("tool_calls") or []]

    def check_hook_results(label: str, response: httpx.Response, conversation: list[dict[str, Any]]) -> None:
        """Keep the raw reply, then check Portkey's ``hook_results`` carry no request or response content.

        Both webhooks return ``transformedData``. Portkey applies it and drops
        it from each check's result, so the hook results hold only each
        webhook's verdict, timing and URL, never the conversation sent to the
        provider or the composed reply.
        """
        (evidence / f"hook-results-{label}.json").write_text(response.text)
        hooks = response.json()["hook_results"]
        serialized = json.dumps(hooks)
        assert hooks.keys() == {"before_request_hooks", "after_request_hooks"}, serialized
        checks = [check for stage in hooks.values() for item in stage for check in item["checks"]]
        assert len(checks) == 2 and all("transformedData" not in check for check in checks), serialized
        assert all(check["data"].get("responseData") is None for check in checks), serialized
        delivered = response.json()["choices"][0]["message"]["content"]
        texts = [delivered, SYSTEM_NOTICE, case["token"]]
        texts += [message["content"] for message in conversation if isinstance(message.get("content"), str)]
        assert not any(text and text in serialized for text in texts), serialized
        assert len(serialized) < 4096, len(serialized)

    # The notice reaches the provider and Watcher's snapshot ahead of the user's message.
    response, provider, _, watcher = send("allow notice " + str(uuid4()))
    assert provider[0]["messages"][0] == notice and watcher[0]["request_body"]["messages"][0] == notice
    assert tool_ids(response) == [case["call_id"]] and len(watcher) == 1
    check_hook_results("allowed", response, provider[0]["messages"])
    results.append({"case": "notice-inserted-upstream", "provider_messages": provider[0]["messages"]})

    # A denial is answered with the notice and an allowed alternative, generated through the gateway.
    response, provider, sent_headers, watcher = send("deny continue " + str(uuid4()))
    delivered = response.json()["choices"][0]["message"]
    assert tool_ids(response) == [case["call_id"] + "-alt1"], response.text
    assert delivered["content"].startswith(
        "Proposed tool call " + case["token"] + "\n\nWATCHER NOTICE (added by Watcher, not written by the assistant)"
    )
    assert delivered["content"].endswith("\n\nAlternative 1")
    assert response.json()["choices"][0]["finish_reason"] == "tool_calls"
    assert len(provider) == 2 and len(watcher) == 2
    continuation = provider[1]
    assert continuation["messages"].count(notice) == 1
    assert continuation["messages"][-1]["role"] == "tool"
    assert continuation["messages"][-1]["content"].startswith("WATCHER NOTICE: Watcher blocked this call.")
    assert "Continue the user's task another way" in continuation["messages"][-1]["content"]
    assert all(ALTERNATIVE_HEADER not in item for item in sent_headers)
    assert watcher[1]["request_body"]["messages"] == continuation["messages"]
    check_hook_results("alternative", response, continuation["messages"])
    # The alternative is graded in the client's own conversation, and every
    # exchange declares that refused calls are withheld.
    identities = [item["external_ids"]["other"] for item in watcher]
    assert identities == [response.headers["X-Watcher-Conversation-Id"]] * 2
    assert all(item["withholds_refused_calls"] is True for item in watcher)
    # The delivered reply is recorded with the refused call named as withheld;
    # its released call moves into history, so nothing is graded again.
    recorded = recording(response)
    assert recorded["withheld_tool_use_ids"] == [case["call_id"]]
    assert recorded["request_body"]["messages"][-1]["tool_calls"] == delivered["tool_calls"]
    assert recorded["response_body"]["choices"][0]["message"] == {"role": "assistant", "content": None}
    results.append({"case": "denial-alternative-delivered", "body": response.json(), "watcher_ids": identities})

    # An escalation stops at once: one final, tool-free generation asks the user.
    response, provider, _, watcher = send("escalate ask " + str(uuid4()))
    delivered = response.json()["choices"][0]["message"]
    assert tool_ids(response) == [] and len(watcher) == 1 and len(provider) == 2
    assert provider[1]["tool_choice"] == "none"
    assert "ask how to proceed with labelled options" in provider[1]["messages"][-1]["content"]
    assert "WATCHER ESCALATION (added by Watcher" in delivered["content"]
    assert delivered["content"].endswith(final_question)
    assert response.json()["choices"][0]["finish_reason"] == "stop"
    assert recording(response)["withheld_tool_use_ids"] == [case["call_id"]]
    results.append({"case": "escalation-final-question", "body": response.json()})

    # Three refused proposals, then the final generation: four model calls, three gradings.
    response, provider, _, watcher = send("deny-always " + str(uuid4()))
    delivered = response.json()["choices"][0]["message"]
    assert len(provider) == 4 and len(watcher) == 3
    assert [item.get("tool_choice") for item in provider] == [None, None, None, "none"]
    assert delivered["content"].count("WATCHER NOTICE (added by Watcher") == 3
    assert tool_ids(response) == [] and delivered["content"].endswith(final_question)
    # Every call of the three refused proposals is named; the final reply's text is the response.
    recorded = recording(response)
    assert recorded["withheld_tool_use_ids"] == [case["call_id"], case["call_id"] + "-alt1", case["call_id"] + "-alt2"]
    assert recorded["response_body"]["choices"][0]["message"]["content"] == delivered["content"]
    results.append({"case": "three-refusals-final", "body": response.json()})

    # A final generation that proposes a call anyway: withheld unevaluated, with the stop notice.
    response, provider, _, watcher = send("escalate disobey " + str(uuid4()))
    delivered = response.json()["choices"][0]["message"]
    assert len(watcher) == 1 and len(provider) == 2 and tool_ids(response) == []
    assert delivered["content"].endswith("C to ask an administrator to change the policy.")
    results.append({"case": "final-calls-withheld", "body": response.json()})

    # A final generation cut off mid-call: its text survives, the call is dropped undecoded.
    response, provider, _, watcher = send("escalate truncated-final " + str(uuid4()))
    delivered = response.json()["choices"][0]["message"]
    assert len(watcher) == 1 and len(provider) == 2 and tool_ids(response) == []
    assert "\n\nPartial question\n\n" in delivered["content"]
    assert delivered["content"].endswith("C to ask an administrator to change the policy.")
    assert response.json()["choices"][0]["finish_reason"] == "stop"
    results.append({"case": "truncated-final-normalized", "body": response.json()})

    # A refusal in a JSON-format reply is an explicit error, with no alternative generated.
    structured = json.loads(json.dumps(template))
    structured["messages"][0]["content"] = "deny structured " + str(uuid4())
    structured["response_format"] = {"type": "json_object"}
    before = (len(provider_requests), len(watcher_requests))
    refused = httpx.post(url, headers=headers, json=structured, timeout=60)
    assert refused.status_code == 403, refused.text
    assert refused.json() == {
        "error": {
            "message": "Watcher refused a tool call in this response, and its notice cannot be delivered "
            "inside the requested structured output format",
            "type": "watcher_withheld",
            "code": 403,
        }
    }
    assert refused.headers["X-Watcher-Conversation-Id"].startswith("portkey:")
    assert (len(provider_requests), len(watcher_requests)) == (before[0] + 1, before[1] + 1)
    assert provider_requests[-1]["response_format"] == {"type": "json_object"}
    results.append({"case": "structured-output-refusal-error", "status": refused.status_code})

    # Loopback marker: only an exact, unexpired, unused bridge signature skips the hooks.
    key = marker_key("fixture-bridge")  # the WATCHER_BRIDGE_TOKEN main() gives the launcher and bridge
    nested = json.loads(json.dumps(template))
    nested["messages"][0]["content"] = "allow nested " + str(uuid4())
    raw = json.dumps(nested).encode()
    expiry = int(time.time()) + 60
    marked = {**headers, "content-type": "application/json"}
    genuine = sign_marker(key, raw, expiry)
    stamp, nonce, mac = genuine.split(".")
    attempts = {
        "forged": f"{expiry}.{'0' * 32}.{'0' * 64}",
        "unsigned-nonce": f"{expiry}.{mac}",
        "uppercase": f"{stamp}.{nonce.upper()}.{mac}",
        "malformed": "not-a-marker",
        "expired": sign_marker(key, raw, int(time.time()) - 5),
        "other-body": sign_marker(key, raw + b" ", expiry),
        "leading-zero": "0" + sign_marker(key, raw, expiry),
    }
    for label, marker in attempts.items():
        before = (len(provider_requests), len(watcher_requests))
        rejected = httpx.post(url, headers={**marked, ALTERNATIVE_HEADER: marker}, content=raw, timeout=30)
        assert rejected.status_code == 403, (label, rejected.text)
        assert (len(provider_requests), len(watcher_requests)) == before
        results.append({"case": "marker-rejected-" + label, "status": rejected.status_code})
    # Two markers for the same body and expiry differ only by nonce: each is accepted once.
    twins = [genuine, sign_marker(key, raw, expiry)]
    assert twins[0] != twins[1]
    before = (len(provider_requests), len(watcher_requests))
    unauthenticated = httpx.post(
        url, headers={"content-type": "application/json", ALTERNATIVE_HEADER: twins[0]}, content=raw, timeout=30
    )
    assert unauthenticated.status_code == 401
    for valid in twins:
        accepted = httpx.post(url, headers={**marked, ALTERNATIVE_HEADER: valid}, content=raw, timeout=30)
        assert accepted.status_code == 200, accepted.text
        assert provider_requests[-1]["messages"] == nested["messages"]
        assert ALTERNATIVE_HEADER not in provider_headers[-1]
        assert "hook_results" not in accepted.json()
    assert len(provider_requests) == before[0] + 2 and len(watcher_requests) == before[1]
    for valid in twins:
        replayed = httpx.post(url, headers={**marked, ALTERNATIVE_HEADER: valid}, content=raw, timeout=30)
        assert replayed.status_code == 403
    assert len(provider_requests) == before[0] + 2
    results.append({"case": "marker-accepted-once-ungraded", "status": 200})

    # Two identical refused requests in the same second produce byte-identical
    # continuations; both must still recover.
    twin_text = "deny twin " + str(uuid4())
    for _ in range(2):
        response, provider, _, watcher = send(twin_text)
        assert tool_ids(response) == [case["call_id"] + "-alt1"], response.text
        assert len(provider) == 2 and len(watcher) == 2
    assert provider_requests[-1] == provider_requests[-3]
    results.append({"case": "identical-continuations-both-recover"})
    return results


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
    provider_headers: list[dict[str, str]] = []
    watcher_requests = []
    watcher_recordings: list[dict[str, Any]] = []
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
                (watcher_recordings if "withheld_tool_use_ids" in body else watcher_requests).append(body)
                assert body["format"] == "raw"
                assert body["user_agent"] == "watcher-local-fixture/1"
                assert body["provider"] == "openai"
                text = user_text(body["request_body"]["messages"])
                if "held" in text:
                    held.set()
                    if not release.wait(20):
                        raise RuntimeError("Held fixture was not released")
                mode = "observe" if "observe" in text else "paused" if "paused" in text else "enforce"

                def judge(call: dict[str, Any]) -> str:
                    # Alternatives carry "alternative" in their content and are
                    # allowed unless the scenario refuses every proposal.
                    content = json.loads(call["function"]["arguments"])["content"]
                    if content.startswith("alternative") and "deny-always" not in text:
                        return "allow"
                    if "deny" in text or mode == "observe":
                        return "deny"
                    return "escalate" if "escalate" in text else "allow"

                data = [
                    {
                        "decision": "deferred" if mode != "enforce" else judge(call),
                        "judged_decision": judge(call) if mode != "paused" else None,
                        "decision_source": "bypass" if mode == "paused" else "rule",
                        "enforcement_mode": mode,
                        "tool_use_id": call["id"],
                        "verdict": {"explanation": "Fixture policy refuses this write"},
                        "latency_ms": 1,
                    }
                    for call in body["response_body"]["choices"][0]["message"].get("tool_calls") or []
                ]
            else:
                provider_requests.append(body)
                provider_headers.append({key.lower(): value for key, value in self.headers.items()})
                results_so_far = [message for message in body["messages"] if message["role"] == "tool"]
                continuation = bool(results_so_far) and results_so_far[-1]["content"].startswith(
                    ("WATCHER", "This call did not run")
                )
                proposals = [message for message in body["messages"] if message.get("tool_calls")]
                if "truncated-text" in user_text(body["messages"]):
                    message = {"role": "assistant", "content": "Partial text " + case["token"]}
                    finish = "length"
                elif args.protocol and continuation and body.get("tool_choice") == "none":
                    message = {
                        "role": "assistant",
                        "content": "FINAL-QUESTION " + case["token"] + ": shall I skip the write?",
                    }
                    finish = "stop"
                    if "disobey" in user_text(body["messages"]):
                        message["tool_calls"] = [
                            {
                                "id": case["call_id"] + "-disobeyed",
                                "type": "function",
                                "function": {"name": "Write", "arguments": json.dumps({"content": "disobeyed"})},
                            }
                        ]
                        finish = "tool_calls"
                    if "truncated-final" in user_text(body["messages"]):
                        message["content"] = "Partial question"
                        message["tool_calls"] = [
                            {
                                "id": case["call_id"] + "-cut",
                                "type": "function",
                                "function": {"name": "Write", "arguments": '{"file_path":'},
                            }
                        ]
                        finish = "length"
                elif args.protocol and continuation:
                    attempt = sum(1 for message in body["messages"] if message.get("tool_calls"))
                    message = {
                        "role": "assistant",
                        "content": f"Alternative {attempt}",
                        "tool_calls": [
                            {
                                "id": f"{case['call_id']}-alt{attempt}",
                                "type": "function",
                                "function": {
                                    "name": "Write",
                                    "arguments": json.dumps(
                                        {"file_path": "sentinel.txt", "content": f"alternative-{attempt}"}
                                    ),
                                },
                            }
                        ],
                    }
                    finish = "tool_calls"
                elif case.get("repeat_id") and continuation and len(proposals) == 1:
                    # The withheld case's first alternative repeats the refused Write
                    # under a new ID beside a new Read, so the bridge refuses it itself.
                    repeated = json.loads(json.dumps(proposals[0]["tool_calls"][0]))
                    repeated["id"] = case["repeat_id"]
                    message = {
                        "role": "assistant",
                        "content": "Trying the write again",
                        "tool_calls": [
                            repeated,
                            {
                                "id": case["repeat_sibling_id"],
                                "type": "function",
                                "function": {"name": "Read", "arguments": json.dumps({"file_path": "other.txt"})},
                            },
                        ],
                    }
                    finish = "tool_calls"
                elif case.get("alternative_id") and continuation:
                    # The withheld case's alternative: a Read the policy allows.
                    message = {
                        "role": "assistant",
                        "content": "Reading instead",
                        "tool_calls": [
                            {
                                "id": case["alternative_id"],
                                "type": "function",
                                "function": {"name": "Read", "arguments": json.dumps({"file_path": "sentinel.txt"})},
                            }
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
                        # The withheld case proposes an allowed Read beside the refused Write.
                        message["tool_calls"].append(
                            {
                                "id": case["sibling_id"],
                                "type": "function",
                                "function": {"name": "Read", "arguments": json.dumps({"file_path": "notes.txt"})},
                            }
                        )
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
        if args.protocol and args.gateway == "portkey":
            results.extend(
                portkey_continuation(
                    url,
                    headers,
                    body,
                    case,
                    provider_requests,
                    provider_headers,
                    watcher_requests,
                    watcher_recordings,
                    evidence,
                )
            )
        if args.protocol:
            for marker, expected in [
                ("allow", True),
                ("deny", args.gateway == "portkey"),
                ("escalate", args.gateway == "portkey"),
                ("observe", True),
                ("paused", True),
            ]:
                body["messages"][0]["content"] = marker + " " + str(uuid4())
                response = httpx.post(url, headers=headers, json=body, timeout=30)
                assert (response.status_code == 200) is expected, response.text
                if not expected:
                    assert case["call_id"] not in response.text and '"tool_calls"' not in response.text
                elif marker in {"deny", "escalate"}:
                    # Portkey answers a refusal with notices, never the refused call.
                    delivered = response.json()["choices"][0]["message"]
                    assert case["call_id"] not in [call["id"] for call in delivered.get("tool_calls") or []]
                    assert "(added by Watcher, not written by the assistant)" in delivered["content"]
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
            if args.gateway == "portkey":
                # The caller's hook override was discarded: the call was graded and withheld.
                delivered = response.json()["choices"][0]["message"]
                assert response.status_code == 200 and "WATCHER NOTICE" in delivered["content"]
                assert case["call_id"] not in [call["id"] for call in delivered.get("tool_calls") or []]
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
            if case.get("sibling_id"):
                # A refused Write beside an allowed Read, then an allowed alternative:
                # the client receives only the alternative's call, and the stored
                # session is read back once the delivered reply is recorded.
                response = httpx.post(url, headers=headers, json=body, timeout=90)
                assert response.status_code == 200, response.text
                (evidence / "response.json").write_text(response.text)
                delivered = response.json()["choices"][0]["message"]
                assert [call["id"] for call in delivered["tool_calls"]] == [case["alternative_id"]], response.text

                async def read_delivered():
                    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key") as client:
                        await wait_for_conversation(
                            client,
                            external_ids={"other": [response.headers["X-Watcher-Conversation-Id"]]},
                            final_text=delivered["content"],
                            decision_ids={case["alternative_id"]},
                            evidence=evidence,
                        )

                asyncio.run(read_delivered())
                results.append({"case": "real-backend-withheld-calls", "body": response.json()})
                return
            response = httpx.post(url, headers=headers, json=body, timeout=90)
            permitted = response.status_code == 200
            if args.gateway == "portkey":
                # Portkey answers a refusal with HTTP 200, Watcher's notices and no refused call.
                assert permitted, response.text
                delivered = response.json()["choices"][0]["message"]
                permitted = case["call_id"] in [call["id"] for call in delivered.get("tool_calls") or []]
                assert permitted or "(added by Watcher, not written by the assistant)" in delivered["content"]
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
            if args.gateway == "portkey" and not permitted:
                # The bridge records the composed reply it delivered, which becomes
                # the session's latest branch; the refused call is listed as withheld.
                expected_final = response.json()["choices"][0]["message"]["content"]
            (evidence / "expected-final.txt").write_text(expected_final)
            (evidence / "response.json").write_text(response.text)

            async def readback():
                async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key") as client:
                    initial = evidence / "decision-snapshot"
                    initial.mkdir()
                    await wait_for_conversation(
                        client,
                        external_ids={"other": [response.headers["X-Watcher-Conversation-Id"]]},
                        final_text="Proposed tool call " + case["token"] if permitted else expected_final,
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
