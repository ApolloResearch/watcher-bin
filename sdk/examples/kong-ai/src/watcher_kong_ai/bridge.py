"""The gateway-private HTTP bridge between the Kong Watcher plugin and the public Watcher SDK.

The plugin calls two endpoints, authenticated with a shared bearer token:

- ``/validate`` before the provider is called. For a client request it checks
  route coverage and returns the request with Watcher's fixed system notice
  added, which the plugin sends upstream. For an alternative the bridge itself
  requested (``alternative_marker`` present) it verifies the marker against
  the exact body instead, so the plugin can pass that exchange through.
- ``/evaluate`` with the buffered provider response. It submits the exchange
  to Watcher and either releases it unchanged, returns a replacement
  response (refusal notices plus an approved alternative or the model's
  question to the user; see ``alternatives``), or withholds it. After it has
  answered the plugin, it records a replacement in the client's Watcher
  session, naming the calls it withheld (``withheld_tool_use_ids``); that
  recording never delays or changes what the client receives.

Kong sends original JSON text in ``request_json`` and ``response_json`` so
Lua's numeric conversions cannot change the arguments evaluated by Watcher.
Request and response content and the client credential are never logged.
"""

import asyncio
import hmac
import json
import os
import re
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

import httpx
import structlog
import typer

from watcher_kong_ai.alternatives import ALTERNATIVE_HEADER, Gateway, marker_key, recover, verify_marker
from watcher_kong_ai.exchange import (
    MAX_BODY,
    UnsupportedExchange,
    check_conversation_id,
    decode_json,
    evaluate,
    string,
    submit,
    validate_request,
)
from watcher_kong_ai.notices import with_system_notice
from watcher_sdk import AsyncWatcherClient, WatcherAPIError

# The Kong route path the plugin reports, used to send alternatives back to
# the same route. Only plain absolute paths are accepted.
_ROUTE_PATH = re.compile(r"/[A-Za-z0-9._~/-]{0,255}")
_HEADER_NAME = re.compile(r"[A-Za-z0-9-]{1,64}")
# A Host header value: a name or IP literal with an optional port.
_HOST = re.compile(r"[A-Za-z0-9.:\[\]-]{1,255}")
# Header values sent on to Kong: visible ASCII and spaces, so no header splitting.
_HEADER_VALUE = re.compile(r"[\x20-\x7e]{1,4096}")
# Route header predicates the bridge forwards, at most this many.
_MAX_ROUTE_HEADERS = 16
# Headers the bridge sets itself, which neither a configured credential header
# nor a forwarded route header predicate may replace.
_RESERVED_HEADERS = {
    ALTERNATIVE_HEADER,
    "content-type",
    "content-length",
    "accept-encoding",
    "host",
    "transfer-encoding",
    "connection",
}

# A notice is text, so it cannot be delivered inside JSON the client asked for.
_STRUCTURED_FORMATS = {"json_object", "json_schema"}
STRUCTURED_REFUSAL = {
    "error": {
        "message": (
            "Watcher refused a tool call in this response, and its notice cannot be delivered "
            "inside the requested structured output format"
        ),
        "type": "watcher_withheld",
        "code": 403,
    }
}

logger = structlog.get_logger(__name__)


class _Withheld(Exception):
    """Watcher's decisions could not be matched to the response; nothing may be delivered."""


@dataclass(frozen=True)
class _Recording:
    """A delivered replacement to record in the client's Watcher session once the plugin has it.

    ``request`` and ``response`` are the exchange as the client sees it (see
    ``recorded_exchange``); ``withheld_ids`` names the calls it replaced.
    """

    request: dict
    response: dict
    conversation_id: str
    user_agent: str | None
    withheld_ids: list[str]


def recorded_exchange(request: dict, delivered: dict) -> tuple[dict, dict]:
    """The exchange that records ``delivered`` as the reply to ``request`` without grading anything again.

    Watcher evaluates the calls in a response. Calls an approved alternative
    carries were graded when it was proposed, so they move into the request
    as the assistant's last message (they have no results yet), and the
    response is an empty assistant message. A reply without calls is recorded
    as it is. Watcher attaches withheld call IDs to the delivered message,
    which is the last stored message or the one before an empty reply.
    """
    choice = delivered["choices"][0]
    if not choice["message"].get("tool_calls"):
        return request, delivered
    history = {**request, "messages": [*request["messages"], choice["message"]]}
    empty = {"role": "assistant", "content": None}
    return history, {**delivered, "choices": [{**choice, "message": empty, "finish_reason": "stop"}]}


def _credential(body: dict) -> tuple[str, str] | None:
    """The client's own authentication header from the plugin, or None when the client sent none."""
    value = body.get("credential")
    if value is None:
        return None
    name = string(body.get("credential_header"), "credential header")
    if not _HEADER_NAME.fullmatch(name) or name.lower() in _RESERVED_HEADERS:
        raise UnsupportedExchange("Invalid credential header")
    return name, string(value, "client credential")


def _routing_headers(body: dict, credential: tuple[str, str] | None) -> dict[str, str]:
    """The headers Kong's router used to pick the client's route: its Host and the route's header predicates.

    The plugin sends the client's raw Host header and, for each header name
    the matched route requires, the client's value; no other client header is
    forwarded. Names that would replace a header the bridge sets itself,
    including the credential header, and values that could split a header
    are refused.
    """
    headers: dict[str, str] = {}
    host = body.get("route_host")
    if host is not None:
        if not isinstance(host, str) or not _HOST.fullmatch(host):
            raise UnsupportedExchange("Invalid route host")
        headers["host"] = host
    predicates = body.get("route_headers")
    if predicates is None:
        return headers
    if not isinstance(predicates, dict) or len(predicates) > _MAX_ROUTE_HEADERS:
        raise UnsupportedExchange("Invalid route headers")
    reserved = _RESERVED_HEADERS | ({credential[0].lower()} if credential else set())
    for name, value in predicates.items():
        if not _HEADER_NAME.fullmatch(name) or not isinstance(value, str) or not _HEADER_VALUE.fullmatch(value):
            raise UnsupportedExchange("Invalid route header")
        # A Content-Type predicate the JSON continuation satisfies is sent as
        # the client sent it, so the route still matches.
        if name.lower() == "content-type" and value.split(";")[0].strip().lower() == "application/json":
            headers["content-type"] = value
            continue
        if name.lower() in reserved:
            raise UnsupportedExchange("Route header cannot be sent with an alternative")
        headers[name.lower()] = value
    return headers


def _gateway_route(gateway_url: str, body: dict) -> tuple[str, tuple[str, str] | None, dict[str, str]]:
    """The client's route URL, credential and routing headers, for requesting alternatives."""
    credential = _credential(body)
    return _route_url(gateway_url, body), credential, _routing_headers(body, credential)


def _route_url(gateway_url: str, body: dict) -> str:
    """The URL of the Kong route that served the client, from the configured gateway base URL."""
    path = string(body.get("route_path"), "route path")
    if not _ROUTE_PATH.fullmatch(path) or "/../" in path + "/":
        raise UnsupportedExchange("Invalid route path")
    return gateway_url.rstrip("/") + path


def serve(host: str, port: int, *, gateway_url: str | None, deadline_seconds: float) -> None:
    """Start an authenticated gateway-only receiver; credentials remain server-side.

    ``gateway_url`` is the base URL at which the bridge reaches Kong's proxy
    listener to request alternatives; it is required, and checked after the
    Watcher credential so a wrong credential is reported first.
    ``deadline_seconds`` bounds the original decision plus every alternative
    and the final generation for one client request; keep it below the
    plugin's ``timeout_ms``. Bind on loopback or an explicitly isolated
    service network, never a public port.
    """
    token = string(os.environ.get("WATCHER_BRIDGE_TOKEN"), "bridge token")
    api_url = string(os.environ.get("WATCHER_BASE_URL"), "Watcher URL")
    api_key = string(os.environ.get("WATCHER_API_KEY"), "Watcher API key")
    if deadline_seconds <= 0:
        raise ValueError("The deadline must be positive")
    key = marker_key(api_key)

    async def check_ingestion() -> None:
        async with AsyncWatcherClient(api_url, api_key=api_key) as watcher:
            permission = await watcher.check_permissions(["sessions:ingest"])
            if permission.granted is not True or permission.missing:
                raise PermissionError("Watcher credential requires sessions:ingest")

    asyncio.run(check_ingestion())
    if not gateway_url or urlsplit(gateway_url).scheme not in {"http", "https"} or not urlsplit(gateway_url).netloc:
        raise ValueError("--gateway-url must be the absolute http(s) URL of Kong's proxy listener")
    gateway: str = gateway_url

    def validate(body: dict) -> dict:
        """Verify an alternative's marker, or add the system notice to a client request."""
        raw = string(body.get("request_json"), "request")
        request = decode_json(raw)
        validate_request(request)
        if "alternative_marker" in body:
            marker = body["alternative_marker"]
            valid = isinstance(marker, str) and verify_marker(key, marker, raw.encode())
            if not valid:
                logger.warning("alternative_marker_rejected")
            return {"verdict": valid}
        noticed = with_system_notice(request)
        if noticed is None:
            return {"verdict": True, "request_json": raw}
        encoded = json.dumps(noticed, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode()) > MAX_BODY:
            raise UnsupportedExchange("Request is too large to carry the Watcher notice")
        return {"verdict": True, "request_json": encoded}

    async def deliver(body: dict) -> tuple[dict, _Recording | None]:
        """Release, replace or withhold one buffered response within the request's deadline.

        Returns the plugin's verdict and, for a replacement, the recording to
        make once the plugin has received it.
        """
        deadline = asyncio.get_running_loop().time() + deadline_seconds
        request = decode_json(string(body.get("request_json"), "request"))
        response = decode_json(string(body.get("response_json"), "response"))
        metadata = body.get("metadata")
        identity = check_conversation_id(
            metadata.get("watcher_conversation_id") if isinstance(metadata, dict) else None
        )
        user_agent = body.get("user_agent") if isinstance(body.get("user_agent"), str) else None
        # The plugin's configured body limit, which a replacement must also respect.
        max_body = body.get("max_body_bytes", MAX_BODY)
        if type(max_body) is not int or not 1024 <= max_body <= MAX_BODY:
            raise UnsupportedExchange("Invalid body limit")
        async with AsyncWatcherClient(api_url, api_key=api_key) as watcher:
            async with asyncio.timeout_at(deadline):
                evaluation = await evaluate(
                    watcher, request, response, conversation_id=identity, user_agent=user_agent, provider="kong"
                )
            if not evaluation.verified:
                raise _Withheld
            if not evaluation.denials:
                return {"verdict": True}, None
            logger.info(
                "proposal_refused",
                conversation_id=identity,
                denied=len(evaluation.denials),
                escalated=any(denial.is_escalation for denial in evaluation.denials),
            )
            response_format = request.get("response_format")
            if isinstance(response_format, dict) and response_format.get("type") in _STRUCTURED_FORMATS:
                # Text notices would make the requested JSON unparseable, so the
                # refusal is an explicit error and no alternative is generated.
                logger.info("structured_output_refusal", conversation_id=identity)
                return {"verdict": True, "status": 403, "response_json": json.dumps(STRUCTURED_REFUSAL)}, None
            # Route context matters only for alternatives, so a route the bridge
            # cannot send one to still gets every ordinary decision and delivery.
            try:
                url, credential, routing = _gateway_route(gateway, body)
            except UnsupportedExchange as error:
                logger.warning("alternative_route_unusable", conversation_id=identity, check=str(error))
                url, credential, routing = None, None, {}
            async with httpx.AsyncClient() as client:
                delivered, withheld_ids = await recover(
                    watcher,
                    None
                    if url is None
                    else Gateway(client=client, url=url, marker_key=key, credential=credential, routing=routing),
                    request,
                    response,
                    evaluation.denials,
                    conversation_id=identity,
                    user_agent=user_agent,
                    deadline=deadline,
                    max_body=max_body,
                )
        encoded = json.dumps(delivered, ensure_ascii=False)
        if len(encoded.encode()) > max_body:
            # The plugin refuses a reply over its limit (HTTP 403), so the client
            # never receives this one and it is not recorded as delivered.
            return {"verdict": True, "response_json": encoded}, None
        recorded_request, recorded_response = recorded_exchange(request, delivered)
        recording = _Recording(recorded_request, recorded_response, identity, user_agent, withheld_ids)
        return {"verdict": True, "response_json": encoded}, recording

    async def record(recording: _Recording) -> None:
        """Record a delivered replacement; a failure is logged and never reaches the client."""
        try:
            async with AsyncWatcherClient(api_url, api_key=api_key) as watcher:
                async with asyncio.timeout(deadline_seconds):
                    await submit(
                        watcher,
                        recording.request,
                        recording.response,
                        conversation_id=recording.conversation_id,
                        user_agent=recording.user_agent,
                        provider="kong",
                        withheld_ids=recording.withheld_ids,
                    )
        except WatcherAPIError as error:
            logger.warning(
                "delivered_reply_not_recorded",
                conversation_id=recording.conversation_id,
                watcher_status=error.status_code,
            )
        except Exception as error:
            logger.warning(
                "delivered_reply_not_recorded",
                conversation_id=recording.conversation_id,
                error_type=type(error).__name__,
            )

    class Handler(BaseHTTPRequestHandler):
        """Validate bridge credentials and keep request content out of logs."""

        def log_message(self, format: str, *_args: Any) -> None:
            pass

        def do_POST(self) -> None:
            """Return the Kong plugin's verdict without exposing Watcher error content."""
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self._reply(401, {"verdict": False})
                return
            recording = None
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY or self.headers.get("Transfer-Encoding"):
                    raise UnsupportedExchange("Invalid body length")
                body = decode_json(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise UnsupportedExchange("Bridge body must be an object")
                if self.path == "/validate":
                    result = validate(body)
                elif self.path == "/evaluate":
                    result, recording = asyncio.run(deliver(body))
                else:
                    raise UnsupportedExchange("Unknown bridge endpoint")
                self._reply(200, result)
            except (ValueError, TypeError, KeyError, RecursionError, _Withheld):
                self._reply(200, {"verdict": False})
            except WatcherAPIError as error:
                # A rejected exchange will not recover by retrying it unchanged.
                permanent = 400 <= error.status_code < 500 and error.status_code not in (408, 429)
                self._reply(200 if permanent else 503, {"verdict": False})
            except Exception as error:
                logger.warning("bridge_request_failed", path=self.path, error_type=type(error).__name__)
                self._reply(503, {"verdict": False})
            if recording is not None:
                # The plugin already has the full reply (it reads Content-Length
                # bytes), so recording here adds nothing to the client's wait.
                asyncio.run(record(recording))

        def _reply(self, status: int, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    ThreadingHTTPServer((host, port), Handler).serve_forever()


app = typer.Typer(invoke_without_command=True, no_args_is_help=True, pretty_exceptions_enable=False)


@app.command("serve")
def serve_command(
    gateway_url: str | None = typer.Option(
        None, help="Required: base URL of Kong's proxy listener, used to request alternatives."
    ),
    host: str = "127.0.0.1",
    port: int = 8765,
    deadline_seconds: float = typer.Option(
        300.0, help="Time for the decision and all alternatives; keep below the plugin's timeout_ms."
    ),
) -> None:
    """Start the gateway-private Watcher bridge on the configured listener."""
    serve(host, port, gateway_url=gateway_url, deadline_seconds=deadline_seconds)


@app.command("help", hidden=True)
def help_command(context: typer.Context) -> None:
    """Display bridge command help."""
    typer.echo(context.parent.get_help() if context.parent else context.get_help())


def main() -> None:
    """Run the bridge CLI; the native gateway remains the client endpoint."""
    app()


if __name__ == "__main__":
    main()
