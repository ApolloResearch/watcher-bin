"""Receive OpenRouter Broadcast traces and submit observed transcripts to Watcher.

Broadcast is a post-request export. This receiver cannot enforce decisions or
prevent tool execution. It accepts complete textual Chat data in the documented
generation-span attributes and rejects missing or unsupported transcript content.
"""

import asyncio
import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast

import typer
from pydantic import BaseModel

from watcher_openrouter.chat import UnsupportedExchange, decode_json, exchange_messages
from watcher_sdk import AsyncWatcherClient

MAX_BODY = 8 * 1024 * 1024


class Snapshot(BaseModel):
    """A validated complete generation ready for a transcript-only submission."""

    conversation_id: str
    messages: list[dict[str, Any]]


class BroadcastBatch(BaseModel):
    """Separate content-bearing generations from non-generation trace spans."""

    snapshots: list[Snapshot]
    ignored_spans: int


class SubmissionReceipt(BaseModel):
    """Report accepted submissions and skipped spans, without claiming durable storage."""

    submitted: int
    ignored_spans: int
    conversation_ids: list[str]


def _objects(value: object, label: str) -> list[dict]:
    """Require bounded arrays of objects at the external OTLP envelope boundary."""
    if not isinstance(value, list) or len(value) > 10000:
        raise UnsupportedExchange(f"Invalid {label} array")
    objects: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            raise UnsupportedExchange(f"Invalid {label} array")
        objects.append(item)
    return objects


def _attributes(span: dict) -> dict:
    """Read OTLP string attributes, refusing duplicate keys rather than choosing one."""
    result = {}
    for attribute in _objects(span.get("attributes", []), "attributes"):
        name = attribute["key"]
        if not isinstance(name, str) or name in result:
            raise UnsupportedExchange("Invalid or duplicate OTLP attribute")
        result[name] = attribute["value"]
    return result


def _content(attributes: dict, name: str) -> object:
    value = attributes[name]
    if not isinstance(value, dict) or not isinstance(value.get("stringValue"), str):
        raise UnsupportedExchange("Transcript attribute must be an OTLP string value")
    return decode_json(value["stringValue"])


def prepare(payload: object, *, namespace: str) -> BroadcastBatch:
    """Validate an entire OTLP batch before submitting any of its generations.

    Content comes from gen_ai.prompt/gen_ai.completion, or span.input/span.output.
    Values must be JSON-encoded Chat request/response objects or message arrays.
    These are explicit supported payload shapes; hosted emission and other
    encodings require a captured sample before they can be claimed as supported.
    Caller-controlled session IDs are not used to group different requests.
    """
    if not namespace.strip() or not isinstance(payload, dict):
        raise UnsupportedExchange("A receiver namespace and OTLP object are required")
    resources = cast(dict[str, object], payload).get("resourceSpans")
    if not isinstance(resources, list):
        raise UnsupportedExchange("resourceSpans must be an array")
    snapshots, ignored = [], 0
    for resource in _objects(resources, "resourceSpans"):
        for scope in _objects(resource.get("scopeSpans", []), "scopeSpans"):
            for span in _objects(scope.get("spans", []), "spans"):
                attributes = _attributes(span)
                if "gen_ai.prompt" in attributes or "gen_ai.completion" in attributes:
                    keys = ("gen_ai.prompt", "gen_ai.completion")
                elif "span.input" in attributes or "span.output" in attributes:
                    keys = ("span.input", "span.output")
                elif "gen_ai.request.model" in attributes:
                    raise UnsupportedExchange("Generation content is missing; check Broadcast privacy settings")
                else:
                    ignored += 1
                    continue
                if not all(name in attributes for name in keys):
                    raise UnsupportedExchange("Both request and response content are required")
                request, response = (_content(attributes, name) for name in keys)
                if isinstance(request, list):
                    model_value = attributes.get("gen_ai.request.model", {}).get("stringValue")
                    request = {"model": model_value, "messages": request}
                if isinstance(response, list):
                    if len(response) != 1 or not isinstance(response[0], dict):
                        raise UnsupportedExchange("Exactly one completed assistant message is required")
                    message = cast(dict[str, object], response[0])
                    response = {
                        "choices": [
                            {
                                "index": 0,
                                "message": message,
                                "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
                            }
                        ]
                    }
                messages = exchange_messages(request, response)
                # Include timestamps, trace/span IDs and contents so a shared
                # client-supplied session.id never aliases independent requests.
                if not isinstance(span.get("spanId"), str) or not span["spanId"]:
                    raise UnsupportedExchange("A generation span ID is required")
                encoded = json.dumps(span, sort_keys=True, separators=(",", ":")).encode()
                identifier = "openrouter:" + hashlib.sha256(namespace.encode() + b"\0" + encoded).hexdigest()
                snapshots.append(Snapshot(conversation_id=identifier, messages=messages))
                if len(snapshots) > 1000:
                    raise UnsupportedExchange("Too many generations in one webhook")
    return BroadcastBatch(snapshots=snapshots, ignored_spans=ignored)


async def submit(client: AsyncWatcherClient, payload: object, *, namespace: str) -> SubmissionReceipt:
    """Submit complete observations without applying retrospective enforcement decisions.

    The hook's null input records transcripts without pre-tool grading. Content
    already reached the gateway's client, so this receiver cannot enforce policy.
    All source shapes are validated first; a later transport failure may still
    leave earlier snapshots submitted. Retain the delivery when retrying.
    """
    batch = prepare(payload, namespace=namespace)
    permission = await client.check_permissions(["sessions:ingest"])
    if permission.granted is not True or permission.missing:
        raise PermissionError("Watcher sessions:ingest permission is required")
    for snapshot in batch.snapshots:
        result = await client.pre_tool_use_hook(
            messages=snapshot.messages, external_ids={"other": snapshot.conversation_id}
        )
        if result != []:
            raise UnsupportedExchange("Unexpected transcript submission response")
    return SubmissionReceipt(
        submitted=len(batch.snapshots),
        ignored_spans=batch.ignored_spans,
        conversation_ids=[snapshot.conversation_id for snapshot in batch.snapshots],
    )


def serve(host: str, port: int, *, namespace: str) -> None:
    """Receive authenticated POST/PUT Broadcast deliveries behind the operator's TLS ingress."""
    token = os.environ["OPENROUTER_WEBHOOK_TOKEN"].encode()
    if not token:
        raise ValueError("A nonempty webhook token is required")
    api_url, api_key = os.environ["WATCHER_BASE_URL"], os.environ["WATCHER_API_KEY"]

    class Handler(BaseHTTPRequestHandler):
        """Bound incoming data and keep transcript content out of server logs."""

        def log_message(self, format: str, *_args: Any) -> None:
            pass

        def do_POST(self) -> None:
            self.receive()

        def do_PUT(self) -> None:
            self.receive()

        def receive(self) -> None:
            supplied = self.headers.get("Authorization", "").encode()
            if not hmac.compare_digest(supplied, b"Bearer " + token):
                self.reply(401, {"error": "Webhook authentication required"})
                return
            if self.path != "/v1/traces":
                self.reply(404, {"error": "Unknown endpoint"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY or self.headers.get("Transfer-Encoding"):
                    raise ValueError("Invalid body size")
                payload = decode_json(self.rfile.read(length))
                if self.headers.get("X-Test-Connection", "").lower() == "true" and payload in (
                    {},
                    {"resourceSpans": []},
                ):
                    self.reply(200, {"submitted": 0, "ignored_spans": 0})
                    return
                prepare(payload, namespace=namespace)

                async def run() -> SubmissionReceipt:
                    async with AsyncWatcherClient(api_url, api_key=api_key) as client:
                        return await submit(client, payload, namespace=namespace)

                self.reply(200, asyncio.run(run()).model_dump())
            except (ValueError, TypeError, KeyError):
                self.reply(422, {"error": "Missing or unsupported generation content"})
            except Exception:
                self.reply(503, {"error": "Watcher submission failed"})

        def reply(self, status: int, payload: dict) -> None:
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    ThreadingHTTPServer((host, port), Handler).serve_forever()


app = typer.Typer(invoke_without_command=True, no_args_is_help=True, pretty_exceptions_enable=False)


@app.command("serve")
def serve_command(namespace: str, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Start a receiver for one operator-defined OpenRouter account namespace."""
    serve(host, port, namespace=namespace)


@app.command("help", hidden=True)
def help_command(context: typer.Context) -> None:
    """Show receiver command help."""
    typer.echo(context.parent.get_help() if context.parent else context.get_help())


def main() -> None:
    """Run the receiver without configuring or contacting the hosted gateway."""
    app()
