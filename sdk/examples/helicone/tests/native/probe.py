"""Exercise the installed Helicone receiver with source-format fixtures and real Watcher storage.

This runs no Helicone platform. A local fixture signs the exact current webhook
JSON shape and sends it over verified TLS to the installed receiver CLI. Original
bodies, rejection results, full-body fetches and public SDK readback are retained.
"""

import asyncio
import hashlib
import hmac
import json
import os
import socket
import ssl
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from _test_support.readback import preserves_source_fields, wait_for_conversation

from watcher_sdk import AsyncWatcherClient

ROOT = Path("/evidence")
TRUNCATED = "Body too large for webhook, please fetch the full request and response from Helicone"


def free_port() -> int:
    """Choose an unused loopback port within this fixture's exclusive network namespace."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


async def verify_storage(identifier: str, expected: list[dict], destination: Path, final_text: str) -> dict:
    """Wait for exact transcript fields, then reject fabricated retrospective decisions."""
    destination.mkdir(exist_ok=True)
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key", max_retries=0) as client:
        stored = await wait_for_conversation(
            client,
            external_ids={"other": ["helicone:" + identifier]},
            final_text=final_text,
            expected_messages=expected,
            decision_ids=set(),
            evidence=destination,
            timeout=30,
        )
        assert preserves_source_fields(stored["messages"], expected)
        assert stored["tool_call_decisions"] == {}
        return stored


async def verify_absence(identifier: str, destination: Path) -> None:
    """Check the rejected event's exact external ID through the actual public API."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key", max_retries=0) as client:
        sessions = (await client.search_sessions(external_ids={"other": ["helicone:" + identifier]})).to_dict()
    destination.write_text(json.dumps(sessions, indent=2))
    assert sessions["total"] == 0 and sessions["sessions"] == []


def main() -> None:
    """Retain actual receiver HTTP behavior independently from the expected transcript."""
    config = json.loads((ROOT / "input.json").read_text())
    certificate, private_key = ROOT / "receiver.crt", ROOT / "receiver.key"
    with (ROOT / "certificate.log").open("w") as output:
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(private_key),
                "-out",
                str(certificate),
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=IP:127.0.0.1,DNS:localhost",
            ],
            stdout=output,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=30,
        )
    arguments = {"file_path": "fixture.txt", "count": 0, "enabled": False, "ratio": 1.0, "empty": None}
    prompt = "Observe this café transcript " + config["token"]
    tool_result = "Actual fixture result " + config["token"]
    request = {
        "model": "fixture-model",
        "messages": [
            {"role": "user", "content": prompt},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": config["call_id"],
                        "type": "function",
                        "function": {"name": "Read", "arguments": json.dumps(arguments)},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": config["call_id"], "content": tool_result},
        ],
    }
    response = {
        "id": "fixture-completion",
        "object": "chat.completion",
        "model": "fixture-model",
        "created": 1,
        "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": config["final_text"]}}
        ],
    }
    expected = [
        {"role": "user", "content": prompt},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": config["call_id"], "type": "function", "function": "Read", "arguments": arguments}],
        },
        {"role": "tool", "tool_call_id": config["call_id"], "content": tool_result},
        {"role": "assistant", "content": config["final_text"]},
    ]
    secret = "local-webhook-" + config["token"]
    storage_requests = []

    class Storage(BaseHTTPRequestHandler):
        """Serve only the fixture's complete original JSON pair without authentication."""

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_GET(self) -> None:
            assert self.path == "/body?signature=fixture"
            storage_requests.append({"path": self.path, "headers": dict(self.headers)})
            assert self.headers.get("Authorization") is None and self.headers.get("Cookie") is None
            assert self.headers.get("Helicone-Signature") is None
            assert self.headers.get("Accept-Encoding") == "identity"
            payload = json.dumps({"request": json.dumps(request), "response": json.dumps(response)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    storage = ThreadingHTTPServer(("127.0.0.1", 0), Storage)
    thread = threading.Thread(target=storage.serve_forever, daemon=True)
    thread.start()
    storage_origin = f"http://127.0.0.1:{storage.server_port}"
    port = free_port()
    command = [
        sys.executable,
        "-m",
        "watcher_helicone.receiver",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--body-origin",
        storage_origin,
        "--certfile",
        str(certificate),
        "--keyfile",
        str(private_key),
    ]
    (ROOT / "receiver-command.json").write_text(json.dumps(command, indent=2))
    logs = (ROOT / "receiver.log").open("w")
    process = subprocess.Popen(
        command,
        env={
            **os.environ,
            "WATCHER_BASE_URL": os.environ["WATCHER_URL"],
            "WATCHER_API_KEY": "fixture-key",
            "HELICONE_WEBHOOK_SECRET": secret,
        },
        stdout=logs,
        stderr=subprocess.STDOUT,
    )
    receipts = []
    try:
        tls = ssl.create_default_context(cafile=str(certificate))
        url = f"https://127.0.0.1:{port}/webhook"
        with httpx.Client(verify=tls, trust_env=False, timeout=65) as http:
            deadline = time.monotonic() + 30
            while True:
                assert process.poll() is None, (ROOT / "receiver.log").read_text()
                try:
                    ready = http.post(url, content=b"{}")
                    assert ready.status_code == 401
                    break
                except httpx.ConnectError:
                    assert time.monotonic() < deadline, "Receiver did not become ready"
                    time.sleep(0.05)

            def submit(event: dict, valid_signature: bool = True) -> httpx.Response:
                body = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode()
                signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest() if valid_signature else "0" * 64
                index = len(receipts)
                (ROOT / f"event-{index}.json").write_bytes(body)
                reply = http.post(
                    url, content=body, headers={"Content-Type": "application/json", "Helicone-Signature": signature}
                )
                receipts.append(
                    {
                        "request_id": event["request_id"],
                        "valid_signature": valid_signature,
                        "request_headers": dict(reply.request.headers),
                        "status": reply.status_code,
                        "response": reply.json(),
                        "body_sha256": hashlib.sha256(body).hexdigest(),
                    }
                )
                return reply

            rejected = str(uuid4())
            truncated = {
                "request_id": rejected,
                "request_body": TRUNCATED,
                "response_body": TRUNCATED,
                "request_response_url": storage_origin + "/body?signature=fixture",
                "model": "fixture-model",
                "provider": "openai",
            }
            assert submit(truncated, False).status_code == 401
            assert storage_requests == []
            asyncio.run(verify_absence(rejected, ROOT / "rejected-sessions.json"))
            identifier = str(uuid4())
            event = {
                "request_id": identifier,
                "request_body": json.dumps(request, ensure_ascii=False),
                "response_body": json.dumps(response),
                "model": "fixture-model",
                "provider": "openai",
                "metadata": {"promptTokens": 3, "completionTokens": 2, "totalTokens": 5, "latencyMs": 1},
            }
            accepted = submit(event)
            assert accepted.status_code == 200 and accepted.json() == {
                "accepted": True,
                "conversation_id": "helicone:" + identifier,
            }
            assert storage_requests == []
            asyncio.run(verify_storage(identifier, expected, ROOT, config["final_text"]))
            assert submit(event).status_code == 200
            asyncio.run(verify_storage(identifier, expected, ROOT / "redelivery", config["final_text"]))
            full_id = str(uuid4())
            truncated["request_id"] = full_id
            assert submit(truncated).status_code == 200
            assert len(storage_requests) == 1
            asyncio.run(verify_storage(full_id, expected, ROOT / "full-body", config["final_text"]))
        (ROOT / "expected-transcript.json").write_text(json.dumps(expected, indent=2))
        (ROOT / "scope.json").write_text(
            json.dumps(
                {
                    "evidence_kind": "contract-local-api",
                    "source": "synthetic completion webhook matching Helicone revision 067d9290acb4f1fc9320e902fc67b4b399b50363",
                    "receiver": "installed current example CLI with TLS and HMAC",
                    "destination": "real Watcher API and migrated PostgreSQL",
                    "native_platform_verified": False,
                    "platform_image_started": False,
                },
                indent=2,
            )
        )
    finally:
        (ROOT / "receiver-http.json").write_text(json.dumps(receipts, indent=2))
        (ROOT / "storage-http.json").write_text(json.dumps(storage_requests, indent=2))
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        logs.close()
        storage.shutdown()
        storage.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
