"""Gateway-private webhook service: add Watcher's notice, grade responses and recover from refusals.

The launcher (``gateway/server.mjs``) installs two Portkey ``default.webhook``
guardrails on every client request. ``/validate`` runs before the provider
call: it rejects requests outside this deployment's delivery limits and
returns the request with Watcher's fixed system notice added, which Portkey
sends to the provider and keeps for the response hook. ``/evaluate`` runs on
the buffered provider response: it releases an allowed response unchanged,
or, after a refusal, returns the composed reply (notices plus an approved
alternative or the model's final question to the user) as Portkey's
transformed response. A refusal in a reply the client asked to receive as
JSON is denied with ``STRUCTURED_OUTPUT_DENIAL``, which the launcher turns into
an explicit HTTP 403 error. Every failure to verify a decision withholds the
response, which Portkey reports as its hook-denied HTTP 446 error. After a
composed reply is returned, a background thread records it in Watcher with
the calls withheld in its favour; that recording never delays or fails the
reply.
"""

import asyncio
import hmac
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import typer

from watcher_portkey.alternatives import (
    Delivery,
    Gateway,
    StructuredOutputRefused,
    marker_key,
    record_delivery,
    respond,
)
from watcher_portkey.exchange import UnsupportedExchange, decode_json, string, validate_request
from watcher_portkey.system_notice import with_system_notice
from watcher_sdk import AsyncWatcherClient

MAX_BODY = 8 * 1024 * 1024
# One deadline for the original decision, every alternative and the final
# generation. It stays below the launcher's webhook timeout (290 s) and below
# the 300 s that Node's built-in fetch waits for response headers by default,
# so the bridge always answers before Portkey abandons the webhook.
DEADLINE_SECONDS = 280.0
# Returned in a refused webhook reply's ``data``; Portkey copies it into the
# 446 body's hook results, where the launcher (gateway/server.mjs) finds it and
# answers the client with an explicit structured-output error instead.
STRUCTURED_OUTPUT_DENIAL = {"watcher_withheld": "structured_output"}
# Bounds recording a composed reply, which runs after the reply was returned.
RECORDING_SECONDS = 60.0


def gateway_url() -> str:
    """The launcher's own Chat Completions URL, from the listener settings it reads too.

    A wildcard listen address is reached through loopback.
    """
    host = os.environ.get("GATEWAY_HOST") or "127.0.0.1"
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    port = int(os.environ.get("GATEWAY_PORT") or 8787)
    return f"http://{f'[{host}]' if ':' in host else host}:{port}/v1/chat/completions"


def serve(host: str, port: int) -> None:
    """Start an authenticated, gateway-private bridge using the public Watcher SDK.

    Requires ``WATCHER_BRIDGE_TOKEN``, ``WATCHER_BASE_URL`` and a
    ``WATCHER_API_KEY`` with ``sessions:ingest`` (checked first), then
    ``GATEWAY_API_KEY`` for generating alternatives through the launcher at
    ``gateway_url()``.
    """
    token = string(os.environ.get("WATCHER_BRIDGE_TOKEN"), "bridge token")
    api_url = string(os.environ.get("WATCHER_BASE_URL"), "Watcher URL")
    api_key = string(os.environ.get("WATCHER_API_KEY"), "Watcher API key")

    async def check_ingestion() -> None:
        async with AsyncWatcherClient(api_url, api_key=api_key) as watcher:
            permission = await watcher.check_permissions(["sessions:ingest"])
            if permission.granted is not True or permission.missing:
                raise PermissionError("Watcher credential requires sessions:ingest")

    asyncio.run(check_ingestion())
    gateway = Gateway(
        url=gateway_url(),
        client_key=string(os.environ.get("GATEWAY_API_KEY"), "gateway API key"),
        marker_key=marker_key(token),
        max_body=MAX_BODY,
    )

    def evaluate(request: Any, response: Any, metadata: Any) -> dict:
        """Answer the response webhook: release unchanged, or substitute the composed reply."""
        if not isinstance(metadata, dict):
            raise UnsupportedExchange("Missing gateway metadata")

        exchange = {
            "conversation_id": metadata.get("watcher_conversation_id"),
            "url": metadata.get("watcher_url"),
            "provider": metadata.get("watcher_provider"),
            "user_agent": metadata.get("watcher_user_agent"),
        }

        async def run() -> Delivery | None:
            deadline = asyncio.get_running_loop().time() + DEADLINE_SECONDS
            async with AsyncWatcherClient(api_url, api_key=api_key) as watcher:
                return await respond(watcher, gateway, request, response, **exchange, deadline=deadline)

        async def record(delivery: Delivery) -> None:
            async with AsyncWatcherClient(api_url, api_key=api_key) as watcher:
                await record_delivery(watcher, request, delivery, **exchange, timeout=RECORDING_SECONDS)

        delivery = asyncio.run(run())
        if delivery is None:
            return {"verdict": True}
        threading.Thread(target=asyncio.run, args=(record(delivery),), daemon=True).start()
        return {"verdict": True, "transformedData": {"response": {"json": delivery.response}}}

    class Handler(BaseHTTPRequestHandler):
        """Validate bridge credentials without logging native transcript content."""

        def log_message(self, format: str, *_args: Any) -> None:
            pass

        def do_POST(self) -> None:
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self._reply(401, {"verdict": False})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY or self.headers.get("Transfer-Encoding"):
                    raise UnsupportedExchange("Invalid body length")
                body = decode_json(self.rfile.read(length))
                if self.path not in ("/validate", "/evaluate") or not isinstance(body, dict):
                    raise UnsupportedExchange("Unknown bridge endpoint")
                request = body.get("request")
                if isinstance(request, dict) and "json" in request:
                    request = request["json"]
                if self.path == "/validate":
                    validate_request(request)
                    noticed = with_system_notice(request)
                    reply: dict[str, object] = {"verdict": True}
                    if noticed is not None:
                        reply["transformedData"] = {"request": {"json": noticed}}
                else:
                    response = body.get("response")
                    if isinstance(response, dict) and "json" in response:
                        response = response["json"]
                    reply = evaluate(request, response, body.get("metadata"))
                self._reply(200, reply)
            except StructuredOutputRefused:
                self._reply(200, {"verdict": False, "data": STRUCTURED_OUTPUT_DENIAL})
            except (ValueError, TypeError, KeyError):
                self._reply(200, {"verdict": False})
            except Exception:
                self._reply(503, {"verdict": False})

        def _reply(self, status: int, payload: dict) -> None:
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    ThreadingHTTPServer((host, port), Handler).serve_forever()


app = typer.Typer(invoke_without_command=True, no_args_is_help=True, pretty_exceptions_enable=False)


@app.command("serve")
def serve_command(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run the gateway-private bridge on the configured listener."""
    serve(host, port)


@app.command("help", hidden=True)
def help_command(context: typer.Context) -> None:
    typer.echo(context.parent.get_help() if context.parent else context.get_help())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
