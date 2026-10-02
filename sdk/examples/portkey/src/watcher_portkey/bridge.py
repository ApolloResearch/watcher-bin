"""Validate gateway delivery and send original provider exchanges to Watcher."""

import asyncio
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import typer

from watcher_sdk import AsyncWatcherClient

MAX_BODY = 8 * 1024 * 1024

# Every conversation ID the gateway plugin generates starts with this prefix
# (see gateway/server.mjs). Watcher labels sessions whose ID carries a
# registered gateway prefix as Gateway, so the bridge refuses any other ID.
CONVERSATION_PREFIX = "portkey:"


class UnsupportedExchange(ValueError):
    """The gateway cannot safely deliver this request or response."""


def _object(pairs: list[tuple[str, Any]]) -> dict:
    """Reject duplicate JSON keys rather than interpreting an ambiguous envelope."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise UnsupportedExchange("Duplicate JSON key")
        result[key] = value
    return result


def decode_json(value: str | bytes) -> Any:
    """Decode gateway envelopes and argument syntax without rewriting their bodies."""

    def invalid_constant(value: str) -> None:
        raise UnsupportedExchange("Non-finite JSON number")

    return json.loads(value, object_pairs_hook=_object, parse_constant=invalid_constant)


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise UnsupportedExchange(f"Missing or invalid {label}")
    return value


def _conversation_id(value: Any) -> str:
    """Require the gateway's documented prefix followed by a nonempty identifier."""
    identity = _string(value, "gateway conversation ID")
    if not identity.startswith(CONVERSATION_PREFIX) or identity == CONVERSATION_PREFIX:
        raise UnsupportedExchange("Gateway conversation ID lacks the documented prefix")
    return identity


def validate_request(request: Any, *, allow_stream: bool = False) -> None:
    """Check this deployment's native delivery limits before provider invocation.

    Watcher performs transcript conversion. This guard limits the example to one
    Chat Completions choice, complete client-provided history and function tools.
    Stream=true needs the native plugin's complete-response buffering path.
    """
    if not isinstance(request, dict):
        raise UnsupportedExchange("Request must be an object")
    _string(request.get("model"), "model")
    if type(request.get("stream", False)) is not bool:
        raise UnsupportedExchange("stream must be a boolean")
    if request.get("stream") and not allow_stream:
        raise UnsupportedExchange("Streaming is unavailable on this gateway route")
    if type(request.get("n", 1)) is not int or request.get("n", 1) != 1:
        raise UnsupportedExchange("Exactly one completion choice is required")
    for key in ("functions", "function_call", "previous_response_id", "conversation", "audio"):
        if request.get(key) is not None:
            raise UnsupportedExchange(f"Unsupported request option: {key}")
    if "audio" in (request.get("modalities") or []):
        raise UnsupportedExchange("Audio output is unsupported")
    tools = request.get("tools", [])
    if not isinstance(tools, list) or any(
        not isinstance(tool, dict) or tool.get("type") != "function" for tool in tools
    ):
        raise UnsupportedExchange("Only client function tools are supported")
    messages = request.get("messages")
    if not isinstance(messages, list) or not messages or any(not isinstance(message, dict) for message in messages):
        raise UnsupportedExchange("A complete messages list is required")


def client_calls(response: Any) -> dict[tuple[str | int, ...], str]:
    """Inventory every executable proposal in the body the client would receive.

    This does not select calls for grading or convert the transcript. A call the
    backend skips as superseded context still needs a decision before a gateway
    releases it. Unique native IDs bind decisions to the calls being delivered.
    """
    choices = response.get("choices") if isinstance(response, dict) else None
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise UnsupportedExchange("One complete response choice is required")
    choice = choices[0]
    if type(choice.get("index")) is not int or choice["index"] != 0:
        raise UnsupportedExchange("Unexpected choice index")
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise UnsupportedExchange("Response must contain an assistant message")
    if message.get("function_call") is not None or message.get("audio") is not None:
        raise UnsupportedExchange("Unsupported executable or audio output")
    calls = message.get("tool_calls", [])
    if calls is None:
        calls = []
    if not isinstance(calls, list):
        raise UnsupportedExchange("Invalid tool proposals")
    reason = choice.get("finish_reason")
    if reason not in ("stop", "tool_calls", "length", "content_filter"):
        raise UnsupportedExchange("Unsupported completion finish reason")
    if calls and reason not in ("stop", "tool_calls"):
        raise UnsupportedExchange("Incomplete executable response")
    paths: dict[tuple[str | int, ...], str] = {}
    seen = set()
    for index, call in enumerate(calls):
        if not isinstance(call, dict) or call.get("type") != "function":
            raise UnsupportedExchange("Unsupported client tool type")
        identifier = _string(call.get("id"), "native call ID")
        if identifier in seen:
            raise UnsupportedExchange("Duplicate native call ID")
        seen.add(identifier)
        function = call.get("function")
        if not isinstance(function, dict) or not isinstance(function.get("arguments"), str):
            raise UnsupportedExchange("Invalid function proposal")
        _string(function.get("name"), "function name")
        if not isinstance(decode_json(function["arguments"]), dict):
            raise UnsupportedExchange("Function arguments must be a JSON object")
        paths[("choices", 0, "message", "tool_calls", index)] = identifier
    return paths


def releasable(value: dict) -> bool:
    """Accept consistent applied allow/deferred; malformed provenance never grants release."""
    decision, mode, source = value.get("decision"), value.get("enforcement_mode"), value.get("decision_source")
    failure = value.get("grading_error")
    if source == "grading_error":
        if (
            not isinstance(failure, dict)
            or failure.get("code")
            not in {"timeout", "at_capacity", "allowance_exhausted", "grader_failed", "no_result"}
            or not isinstance(failure.get("message"), str)
        ):
            return False
    elif failure is not None:
        return False
    if mode == "paused":
        return decision == "deferred" and source == "bypass" and value.get("judged_decision") is None
    if source not in {"threshold", "rule", "triage", "policy_gateway", "grading_error"}:
        return False
    if mode == "observe":
        return decision == "deferred" and value.get("judged_decision") in {"allow", "deny", "escalate"}
    return mode == "enforce" and decision == "allow" and value.get("judged_decision") == "allow"


async def evaluate(
    watcher: AsyncWatcherClient,
    request: dict,
    response: dict,
    *,
    conversation_id: str,
    allow_stream: bool = False,
    url: str = "/v1/chat/completions",
    provider: str = "openai",
    user_agent: str | None = None,
) -> bool:
    """Send the original exchange to Watcher; release only calls with matching native IDs.

    No settings override is sent. Backend conversion and call selection are
    authoritative for grading; the independent delivery inventory prevents a
    skipped proposal reaching the client without permission. Empty results admit
    text-only output, never an uncovered client tool. Ingestion remains asynchronous.
    A conversation ID without ``CONVERSATION_PREFIX`` is refused before Watcher is called.
    """
    _conversation_id(conversation_id)
    validate_request(request, allow_stream=allow_stream)
    expected = set(client_calls(response).values())
    if user_agent is not None and not isinstance(user_agent, str):
        raise UnsupportedExchange("Invalid client User-Agent")
    outcomes = await watcher.pre_tool_use_hook(
        request_body=request,
        response_body=response,
        url=_string(url, "client-facing URL"),
        provider=_string(provider, "provider"),
        user_agent=user_agent,
        external_ids={"other": conversation_id},
    )
    if not isinstance(outcomes, list):
        return False
    released = set()
    for outcome in outcomes:
        serialize = getattr(outcome, "to_dict", None)
        if not callable(serialize):
            return False
        value = serialize()
        identifier = value.get("tool_use_id")
        if (
            not isinstance(identifier, str)
            or identifier not in expected
            or identifier in released
            or not releasable(value)
        ):
            return False
        released.add(identifier)
    return released == expected


def serve(host: str, port: int, *, allow_stream: bool = False) -> None:
    """Start an authenticated, gateway-private bridge using the public Watcher SDK."""
    token = _string(os.environ.get("WATCHER_BRIDGE_TOKEN"), "bridge token")
    api_url = _string(os.environ.get("WATCHER_BASE_URL"), "Watcher URL")
    api_key = _string(os.environ.get("WATCHER_API_KEY"), "Watcher API key")

    async def check_ingestion() -> None:
        async with AsyncWatcherClient(api_url, api_key=api_key) as watcher:
            permission = await watcher.check_permissions(["sessions:ingest"])
            if permission.granted is not True or permission.missing:
                raise PermissionError("Watcher credential requires sessions:ingest")

    asyncio.run(check_ingestion())

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
                    validate_request(request, allow_stream=allow_stream)
                    allowed = True
                else:
                    response = body.get("response")
                    if isinstance(response, dict) and "json" in response:
                        response = response["json"]
                    metadata = body.get("metadata", {})

                    async def run() -> bool:
                        async with AsyncWatcherClient(api_url, api_key=api_key) as watcher:
                            return await evaluate(
                                watcher,
                                request,
                                response,
                                conversation_id=_string(
                                    metadata.get("watcher_conversation_id"), "gateway conversation ID"
                                ),
                                allow_stream=allow_stream,
                                url=metadata.get("watcher_url"),
                                provider=metadata.get("watcher_provider"),
                                user_agent=metadata.get("watcher_user_agent"),
                            )

                    allowed = asyncio.run(run())
                self._reply(200, {"verdict": allowed})
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
def serve_command(host: str = "127.0.0.1", port: int = 8765, allow_buffered_stream: bool = False) -> None:
    """Run the gateway-private bridge on the configured listener."""
    serve(host, port, allow_stream=allow_buffered_stream)


@app.command("help", hidden=True)
def help_command(context: typer.Context) -> None:
    typer.echo(context.parent.get_help() if context.parent else context.get_help())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
