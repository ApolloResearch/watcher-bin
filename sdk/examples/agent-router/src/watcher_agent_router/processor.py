"""Envoy external processor that gates Agent Router responses on Watcher decisions.

Agent Router runs on Envoy Gateway, which attaches extra external processors
to a Gateway through an ``EnvoyExtensionPolicy``. Envoy streams each HTTP
request to this server as a sequence of processing messages and waits for one
reply per message. With buffered body modes the sequence for one exchange is:

1. request headers: require the gateway client key, reject anything but
   ``POST /v1/chat/completions``, mint the ``agent-router:`` conversation ID,
   and drop the client key and ``Accept-Encoding`` so neither reaches the
   provider and its response arrives uncompressed;
2. request body: validate the Chat Completions request before the provider is
   called;
3. response headers: refuse provider redirects, note the status and encoding,
   and add the ``X-Watcher-Conversation-Id`` header;
4. response body: submit the exchange to Watcher and release the body
   unchanged, replace refused calls with an explanation and, when a gateway
   URL is configured, an approved alternative (``alternatives.py``), or
   replace the whole response with an HTTP error when nothing can be verified.

A ``stream: true`` request whose provider answers with server-sent events is
switched to streamed body processing at step 3 (``mode_override``). Text then
reaches the client as it arrives; from the first tool-call event on, events are
held until the provider finishes and Watcher has decided (``streaming.py``). A
refusal ends the stream normally with the explanation; the response has already
started by then, so a technical failure ends it with an SSE error event
instead of an HTTP status.

Agent Router's own processor runs before this one on the request path and
after it on the response path, so step 4 sees the provider's response before
Agent Router translates it. The supplied configuration therefore routes only
to backends with the OpenAI schema, whose responses are already Chat
Completions bodies.
"""

import asyncio
import hmac
import json
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import grpc
import httpx
import structlog
import typer
from envoy.config.core.v3.base_pb2 import HeaderValue, HeaderValueOption
from envoy.extensions.filters.http.ext_proc.v3.processing_mode_pb2 import ProcessingMode
from envoy.service.ext_proc.v3 import external_processor_pb2 as ext_proc
from envoy.service.ext_proc.v3 import external_processor_pb2_grpc as ext_proc_grpc
from envoy.type.v3.http_status_pb2 import HttpStatus
from pydantic import BaseModel, ConfigDict

from watcher_agent_router.alternatives import (
    ALTERNATIVE_HEADER,
    Gateway,
    Recovery,
    marker_key,
    recover,
    verify_marker,
)
from watcher_agent_router.exchange import (
    CHAT_COMPLETIONS_PATH,
    CONVERSATION_PREFIX,
    Evaluation,
    UnsupportedExchange,
    compose,
    decode_json,
    evaluate,
    validate_request,
    withheld_notice,
)
from watcher_agent_router.streaming import StreamGate, error_event
from watcher_sdk import AsyncWatcherClient, WatcherAPIError

# Matches the 8 MiB connection buffer limit in gateway/agent-router.yaml; Envoy
# answers 413 before a larger body reaches the processor.
MAX_BODY = 8 * 1024 * 1024
# gRPC's 4 MiB default would refuse a full buffered body plus its framing.
_GRPC_MESSAGE_LIMIT = MAX_BODY + 1024 * 1024
# Room left for the protobuf envelope around a replacement body.
_REPLY_HEADROOM = 64 * 1024
# Total time allowed for one response's decision, including any alternatives
# generated and graded after a refusal. The SDK's own 420-second hook timeout
# applies per HTTP phase (connect, write, read), so it is not a total deadline;
# this one is, and it stays below the 450-second Envoy message timeout in
# gateway/agent-router.yaml so the processor answers before Envoy gives up.
WATCHER_DEADLINE_SECONDS = 420.0

CONVERSATION_HEADER = "x-watcher-conversation-id"
# Clients authenticate to the gateway with this header; the provider key stays in Agent Router.
CLIENT_KEY_HEADER = "x-api-key"

logger = structlog.get_logger(__name__)
UNCOVERED_PATH = "Only POST /v1/chat/completions is available on this monitored gateway"


class _Exchange(BaseModel):
    """What one HTTP exchange has revealed so far; one instance per processing stream.

    ``gate`` is set only when the response is being streamed, and
    ``stream_ended`` once a streamed response has been cut off, after which
    every remaining provider byte is dropped. ``marker`` holds a received
    alternative marker until the body can be checked against it;
    ``passthrough`` is set for the processor's own alternative requests, which
    the requesting pass grades instead.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    conversation_id: str = ""
    user_agent: str | None = None
    request: dict | None = None
    status: str = ""
    gate: StreamGate | None = None
    stream_ended: bool = False
    marker: str | None = None
    passthrough: bool = False


class _Refusal(BaseModel):
    """Why a response may not be released, as reported to the client and the log."""

    status: int
    reason: str
    detail: dict[str, str | int] = {}


def _headers(message: ext_proc.HttpHeaders) -> dict[str, str]:
    """Flatten Envoy's header list; Envoy sends values in ``raw_value`` or ``value``."""
    return {
        header.key.lower(): header.raw_value.decode("utf-8", "replace") if header.raw_value else header.value
        for header in message.headers.headers
    }


def _header(name: str, value: str) -> HeaderValueOption:
    return HeaderValueOption(header=HeaderValue(key=name, raw_value=value.encode()))


def _reject(status: int, message: str, conversation_id: str = "", **detail: str | int) -> ext_proc.ProcessingResponse:
    """Replace the whole response with an OpenAI-style error that names no request content.

    Every refusal is logged once with its status, the client-facing reason and
    any ``detail`` (a Watcher status or error type). Reasons are fixed text or
    name a failed check, never request or response content.
    """
    _log_refusal(status, message, conversation_id, **detail)
    headers = [_header("content-type", "application/json")]
    if conversation_id:
        headers.append(_header(CONVERSATION_HEADER, conversation_id))
    body = json.dumps({"error": {"message": message, "type": "watcher_withheld", "code": status}})
    return ext_proc.ProcessingResponse(
        immediate_response=ext_proc.ImmediateResponse(
            status=HttpStatus(code=status),
            headers=ext_proc.HeaderMutation(set_headers=headers),
            body=body.encode(),
        )
    )


def _log_refusal(status: int, message: str, conversation_id: str, **detail: str | int) -> None:
    logger.warning(
        "exchange_withheld", status=status, reason=message, conversation_id=conversation_id or None, **detail
    )


def _replace_body(data: bytes) -> ext_proc.ProcessingResponse:
    """Replace a whole buffered response body; its headers have not been sent yet."""
    common = ext_proc.CommonResponse(
        body_mutation=ext_proc.BodyMutation(body=data),
        header_mutation=ext_proc.HeaderMutation(set_headers=[_header("content-length", str(len(data)))]),
    )
    return ext_proc.ProcessingResponse(response_body=ext_proc.BodyResponse(response=common))


_TOO_LARGE = " The approved alternative was too large to deliver."


def _short_notice(response: dict, evaluation: Evaluation, recovery: Recovery) -> str:
    """A count-only notice that always fits, for when the full reply would exceed its size budget."""
    notice = withheld_notice(response, evaluation, compact=True)
    return notice + _TOO_LARGE if recovery.alternative is not None else notice


def _denied_body(response: dict, evaluation: Evaluation, recovery: Recovery) -> bytes:
    """The rewritten response for a refusal, kept within ``MAX_BODY``.

    Echoed fields are already shortened, but the provider's own text, an
    alternative and nested JSON escaping can still grow the body, so an
    oversized result falls back to a short count-only notice that always fits.
    """
    body = _compact(compose(response, "\n\n".join(recovery.notices), recovery.alternative))
    if len(body) <= MAX_BODY:
        return body
    message = {"role": "assistant", "content": _short_notice(response, evaluation, recovery)}
    compact = {
        "id": str(response.get("id", ""))[:256],
        "object": "chat.completion",
        "created": response.get("created") if type(response.get("created")) is int else 0,
        "model": str(response.get("model", ""))[:256],
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
    }
    return _compact(compact)


def _compact(value: object) -> bytes:
    """Serialize synthesized JSON without padding or escapes, so it is no larger than needed."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _log_denials(exchange: "_Exchange", evaluation: Evaluation) -> None:
    logger.info(
        "tool_calls_withheld",
        conversation_id=exchange.conversation_id,
        denied=len(evaluation.denials),
        escalated=sum(denial.is_escalation for denial in evaluation.denials),
    )


def _replace_chunk(data: bytes) -> ext_proc.ProcessingResponse:
    """Deliver ``data`` in place of the streamed chunk Envoy just sent; empty data holds it back."""
    mutation = ext_proc.BodyMutation(body=data) if data else ext_proc.BodyMutation(clear_body=True)
    return ext_proc.ProcessingResponse(
        response_body=ext_proc.BodyResponse(response=ext_proc.CommonResponse(body_mutation=mutation))
    )


def _continue_body(field: str) -> ext_proc.ProcessingResponse:
    return ext_proc.ProcessingResponse(**{field: ext_proc.BodyResponse()})


class WatcherProcessor(ext_proc_grpc.ExternalProcessorServicer):
    """Answer Envoy's processing messages for each exchange using one shared Watcher client."""

    def __init__(
        self,
        watcher: AsyncWatcherClient,
        client_key: str | None,
        *,
        marker: bytes | None = None,
        gateway: Gateway | None = None,
    ) -> None:
        """Configure authentication and alternatives.

        ``client_key`` is the gateway key clients must send; None leaves
        authentication to the Gateway. ``marker`` is the key alternative
        requests are signed with (None refuses every marked request), and
        ``gateway`` generates alternatives (None delivers refusals alone).
        """
        self._watcher = watcher
        self._client_key = client_key
        self._marker = marker
        self._gateway = gateway

    async def Process(  # noqa: N802  # gRPC method name fixed by the Envoy service definition
        self,
        request_iterator: AsyncIterator[ext_proc.ProcessingRequest],
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[ext_proc.ProcessingResponse]:
        """Reply to every message in order; an immediate response ends the exchange."""
        exchange = _Exchange()
        async for message in request_iterator:
            reply = await self.handle(exchange, message)
            yield reply
            if reply.HasField("immediate_response"):
                return

    async def handle(self, exchange: _Exchange, message: ext_proc.ProcessingRequest) -> ext_proc.ProcessingResponse:
        """Dispatch one processing message; unexpected phases withhold the response."""
        phase = message.WhichOneof("request")
        if phase == "request_headers":
            return self._request_headers(exchange, message.request_headers)
        if phase == "request_body":
            return self._request_body(exchange, message.request_body)
        if phase == "response_headers":
            return self._response_headers(exchange, message.response_headers)
        if phase == "response_body":
            return await self._response_body(exchange, message.response_body)
        return _reject(500, "Unexpected gateway processing phase", exchange.conversation_id)

    def _request_headers(self, exchange: _Exchange, message: ext_proc.HttpHeaders) -> ext_proc.ProcessingResponse:
        headers = _headers(message)
        if self._client_key is not None and not hmac.compare_digest(
            headers.get(CLIENT_KEY_HEADER, "").encode(), self._client_key.encode()
        ):
            return _reject(401, "A valid gateway key is required in the x-api-key header")
        path = headers.get(":path", "").split("?", 1)[0]
        if headers.get(":method") != "POST" or path != CHAT_COMPLETIONS_PATH:
            return _reject(404, UNCOVERED_PATH)
        if message.end_of_stream:
            return _reject(400, "A request body is required")
        exchange.conversation_id = f"{CONVERSATION_PREFIX}{uuid4()}"
        exchange.user_agent = headers.get("user-agent")
        exchange.marker = headers.get(ALTERNATIVE_HEADER)
        mutation = ext_proc.HeaderMutation(remove_headers=[CLIENT_KEY_HEADER, "accept-encoding", ALTERNATIVE_HEADER])
        return ext_proc.ProcessingResponse(
            request_headers=ext_proc.HeadersResponse(response=ext_proc.CommonResponse(header_mutation=mutation))
        )

    def _request_body(self, exchange: _Exchange, message: ext_proc.HttpBody) -> ext_proc.ProcessingResponse:
        try:
            if not message.end_of_stream or len(message.body) > MAX_BODY:
                raise UnsupportedExchange("The request body must be complete and within the size limit")
            request = decode_json(message.body)
            validate_request(request)
        except UnsupportedExchange as error:
            return _reject(400, str(error), exchange.conversation_id)
        if exchange.marker is not None:
            if self._marker is None or not verify_marker(self._marker, exchange.marker, message.body):
                return _reject(403, "Invalid alternative marker", exchange.conversation_id)
            exchange.passthrough = True
        exchange.request = request
        return _continue_body("request_body")

    def _response_headers(self, exchange: _Exchange, message: ext_proc.HttpHeaders) -> ext_proc.ProcessingResponse:
        """Record what the body phase needs; a redirect is replaced here, before Envoy forwards it.

        OpenAI clients follow 307 and 308 redirects with the original POST, so
        a released redirect would fetch a completion from outside the gateway.
        A header-only redirect never reaches the body phase, so it must be
        refused at this point.
        """
        headers = _headers(message)
        exchange.status = headers.get(":status", "")
        if exchange.request is None:
            # Agent Router answered without this processor seeing a request, as
            # it does for GET /v1/models and for its own routing errors.
            if exchange.status[:1] in ("4", "5"):
                return ext_proc.ProcessingResponse(response_headers=ext_proc.HeadersResponse())
            return _reject(404, UNCOVERED_PATH)
        if exchange.status.startswith("3"):
            return _reject(502, "The provider redirected this request", exchange.conversation_id)
        if message.end_of_stream and exchange.status[:1] not in ("4", "5"):
            # No body phase follows, so the response could never be submitted to Watcher.
            return _reject(502, "The provider returned no completion", exchange.conversation_id)
        encoding = headers.get("content-encoding", "identity").strip().lower()
        if encoding != "identity" and exchange.status[:1] not in ("4", "5"):
            # Refused before these headers go downstream: a body rewritten later
            # would no longer match the Content-Encoding the client was told.
            return _reject(
                403,
                "The gateway cannot verify this response",
                exchange.conversation_id,
                check="Compressed provider responses are unsupported",
            )
        if exchange.passthrough:
            # The requesting pass grades this alternative itself, but the checks
            # above still apply: Agent Router decodes a compressed body in full
            # after this processor, and a redirect must never be followed.
            return ext_proc.ProcessingResponse(response_headers=ext_proc.HeadersResponse())
        mutation = ext_proc.HeaderMutation(set_headers=[_header(CONVERSATION_HEADER, exchange.conversation_id)])
        reply = ext_proc.ProcessingResponse(
            response_headers=ext_proc.HeadersResponse(response=ext_proc.CommonResponse(header_mutation=mutation))
        )
        streamed = headers.get("content-type", "").split(";", 1)[0].strip().lower() == "text/event-stream"
        if exchange.request.get("stream") is True and exchange.status.startswith("2") and streamed:
            exchange.gate = StreamGate(MAX_BODY)
            reply.mode_override.CopyFrom(ProcessingMode(response_body_mode=ProcessingMode.STREAMED))
        return reply

    async def _response_body(self, exchange: _Exchange, message: ext_proc.HttpBody) -> ext_proc.ProcessingResponse:
        """Release the provider body only when Watcher allows every tool call it carries.

        Provider errors (4xx and 5xx) carry no completion and pass through;
        every other status is treated as a possible completion. Bodies that
        cannot be read in full, or that Watcher permanently refuses, are
        withheld with 403; transient Watcher failures return 503.
        """
        if exchange.gate is not None:
            return await self._stream_body(exchange, exchange.gate, message)
        if exchange.status[:1] in ("4", "5") or exchange.passthrough:
            return _continue_body("response_body")
        deadline = asyncio.get_running_loop().time() + WATCHER_DEADLINE_SECONDS
        try:
            if exchange.request is None or not message.end_of_stream or len(message.body) > MAX_BODY:
                raise UnsupportedExchange("The response must be complete and within the size limit")
            response = decode_json(message.body)
            if not isinstance(response, dict):
                raise UnsupportedExchange("Response must be a JSON object")
        except UnsupportedExchange as error:
            # The messages name the failed check, never request or response content.
            return _reject(403, "The gateway cannot verify this response", exchange.conversation_id, check=str(error))
        outcome = await self._decide(exchange, exchange.request, response, deadline)
        if isinstance(outcome, _Refusal):
            return _reject(outcome.status, outcome.reason, exchange.conversation_id, **outcome.detail)
        if outcome.denials:
            recovery = await self._recover(exchange, exchange.request, response, outcome, deadline)
            return _replace_body(_denied_body(response, outcome, recovery))
        return _continue_body("response_body")

    async def _stream_body(
        self, exchange: _Exchange, gate: StreamGate, message: ext_proc.HttpBody
    ) -> ext_proc.ProcessingResponse:
        """Release streamed text at once and held tool-call events only after Watcher allows them.

        Each reply replaces the chunk Envoy sent with the bytes that may reach
        the client now. A refusal replaces the held events with the
        explanation and any approved alternative; a technical failure replaces
        the rest of the stream with one SSE error event. Text-only streams are
        still submitted, at the end, so the whole conversation is recorded.
        """
        if exchange.stream_ended:
            return _replace_chunk(b"")
        try:
            released = gate.feed(message.body, final=message.end_of_stream)
            if not message.end_of_stream:
                return _replace_chunk(released)
            deadline = asyncio.get_running_loop().time() + WATCHER_DEADLINE_SECONDS
            completion = gate.completion()
        except UnsupportedExchange as error:
            refusal = _Refusal(
                status=403, reason="The gateway cannot verify this response", detail={"check": str(error)}
            )
            return self._end_stream(exchange, refusal)
        except Exception as error:
            # Provider bytes are untrusted; any parsing failure must still end the
            # stream with a refusal rather than abort the processing stream.
            refusal = _Refusal(
                status=403,
                reason="The gateway cannot verify this response",
                detail={"error_type": type(error).__name__},
            )
            return self._end_stream(exchange, refusal)
        assert exchange.request is not None  # a gate is only created for a validated request
        outcome = await self._decide(exchange, exchange.request, completion, deadline)
        if isinstance(outcome, _Refusal):
            return self._end_stream(exchange, outcome, released)
        if outcome.denials:
            recovery = await self._recover(exchange, exchange.request, completion, outcome, deadline)
            events = gate.denial_events("\n\n".join(recovery.notices), recovery.alternative)
            if len(released) + len(events) > _GRPC_MESSAGE_LIMIT - _REPLY_HEADROOM:
                events = gate.denial_events(_short_notice(completion, outcome, recovery))
            return _replace_chunk(released + events)
        return _replace_chunk(released + gate.release_held())

    def _end_stream(self, exchange: _Exchange, refusal: _Refusal, released: bytes = b"") -> ext_proc.ProcessingResponse:
        """Drop held events and the rest of the stream, ending it with an error the client raises."""
        _log_refusal(refusal.status, refusal.reason, exchange.conversation_id, streamed=1, **refusal.detail)
        exchange.stream_ended = True
        return _replace_chunk(released + error_event(refusal.reason, exchange.conversation_id, refusal.status))

    async def _recover(
        self, exchange: _Exchange, request: dict, response: dict, evaluation: Evaluation, deadline: float
    ) -> Recovery:
        """Log the refusal, then look for an approved alternative in the time left."""
        _log_denials(exchange, evaluation)
        return await recover(
            self._watcher,
            self._gateway,
            request,
            response,
            evaluation,
            conversation_id=exchange.conversation_id,
            user_agent=exchange.user_agent,
            deadline=deadline,
        )

    async def _decide(
        self, exchange: _Exchange, request: dict, response: dict, deadline: float
    ) -> "_Refusal | Evaluation":
        """Ask Watcher about a complete response before ``deadline`` (event loop clock).

        A ``_Refusal`` means nothing may be released (a technical failure or
        unmatched decisions). An ``Evaluation`` lists any calls Watcher refused,
        which the caller withholds while still delivering a normal response.
        """
        try:
            async with asyncio.timeout_at(deadline):
                evaluation = await evaluate(
                    self._watcher,
                    request,
                    response,
                    conversation_id=exchange.conversation_id,
                    user_agent=exchange.user_agent,
                )
        except UnsupportedExchange as error:
            return _Refusal(status=403, reason="The gateway cannot verify this response", detail={"check": str(error)})
        except WatcherAPIError as error:
            # A rejected exchange will not recover by retrying it unchanged.
            permanent = 400 <= error.status_code < 500 and error.status_code not in (408, 429)
            return _Refusal(
                status=403 if permanent else 503,
                reason="Watcher did not accept this exchange",
                detail={"watcher_status": error.status_code},
            )
        except Exception as error:
            return _Refusal(status=503, reason="Watcher is unavailable", detail={"error_type": type(error).__name__})
        if not evaluation.verified:
            return _Refusal(status=403, reason="Watcher's decisions do not match this response")
        return evaluation


async def _check_ingestion(watcher: AsyncWatcherClient) -> None:
    permission = await watcher.check_permissions(["sessions:ingest"])
    if permission.granted is not True or permission.missing:
        raise PermissionError("Watcher credential requires sessions:ingest")


async def _serve(
    address: str,
    api_url: str,
    api_key: str,
    client_key: str | None,
    ready: asyncio.Event,
    gateway_url: str | None = None,
) -> None:
    """Check the credential, then serve Envoy until cancelled; ``ready`` is set once listening.

    With ``gateway_url`` (which requires ``client_key``), refused proposals are
    followed by alternatives generated through that Agent Router listener.
    """
    # The total deadline bounds each alternative request, so httpx adds none.
    async with (
        AsyncWatcherClient(api_url, api_key=api_key) as watcher,
        httpx.AsyncClient(base_url=gateway_url or "http://gateway.invalid", timeout=None) as http,
    ):
        await _check_ingestion(watcher)
        key = marker_key(api_key)
        gateway = (
            Gateway(client=http, client_key=client_key, marker_key=key, max_body=MAX_BODY)
            if gateway_url and client_key
            else None
        )
        server = grpc.aio.server(
            options=[
                ("grpc.max_receive_message_length", _GRPC_MESSAGE_LIMIT),
                ("grpc.max_send_message_length", _GRPC_MESSAGE_LIMIT),
            ]
        )
        ext_proc_grpc.add_ExternalProcessorServicer_to_server(
            WatcherProcessor(watcher, client_key, marker=key, gateway=gateway), server
        )
        server.add_insecure_port(address)
        await server.start()
        typer.echo(f"Watcher external processor listening on {address}", err=True)
        ready.set()
        try:
            await server.wait_for_termination()
        finally:
            await server.stop(grace=5)


app = typer.Typer(invoke_without_command=True, no_args_is_help=True, pretty_exceptions_enable=False)


@app.command("serve")
def serve_command(
    address: str = typer.Option(
        "127.0.0.1:50051", help="gRPC listen address for Envoy, such as 127.0.0.1:50051 or unix:/path/to.sock."
    ),
    allow_unauthenticated_clients: bool = typer.Option(
        False, help="Skip the gateway key check; only when a Gateway SecurityPolicy already authenticates clients."
    ),
) -> None:
    """Serve the external processor; reads WATCHER_BASE_URL, WATCHER_API_KEY, GATEWAY_API_KEY and GATEWAY_URL."""
    api_url = os.environ.get("WATCHER_BASE_URL")
    api_key = os.environ.get("WATCHER_API_KEY")
    if not api_url or not api_key:
        raise typer.BadParameter("Set WATCHER_BASE_URL and WATCHER_API_KEY")
    client_key = None if allow_unauthenticated_clients else os.environ.get("GATEWAY_API_KEY") or None
    if client_key is None and not allow_unauthenticated_clients:
        # Agent Router injects the provider key, so an open gateway spends the operator's account.
        raise typer.BadParameter("Set GATEWAY_API_KEY, or pass --allow-unauthenticated-clients")
    gateway_url = os.environ.get("GATEWAY_URL") or None
    if gateway_url and client_key is None:
        # Alternatives are requested from the listener as a client, with the gateway key.
        raise typer.BadParameter("GATEWAY_URL requires GATEWAY_API_KEY")
    if gateway_url is None:
        typer.echo("GATEWAY_URL is not set: refused proposals are explained without alternatives", err=True)
    asyncio.run(_serve(address, api_url, api_key, client_key, asyncio.Event(), gateway_url))


@app.command("help", hidden=True)
def help_command(context: typer.Context) -> None:
    """Display processor command help."""
    typer.echo(context.parent.get_help() if context.parent else context.get_help())


def main() -> None:
    """Run the processor CLI; Agent Router remains the client endpoint."""
    app()


if __name__ == "__main__":
    main()
