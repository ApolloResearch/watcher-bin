"""Submit complete Chat exchanges to Watcher and validate delivery decisions.

Provider-to-transcript conversion belongs to Watcher. This module inventories
only client-visible tool proposals so a call omitted by backend selection cannot
be released without a corresponding decision for its unique native ID.
"""

import asyncio
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import typer

from watcher_sdk import AsyncWatcherClient, WatcherAPIError

MAX_BODY = 8 * 1024 * 1024

# Every conversation ID the gateway plugin generates starts with this prefix
# (see gateway/kong/plugins/watcher/handler.lua). Watcher labels sessions whose ID carries a
# registered gateway prefix as Gateway, so the bridge refuses any other ID.
CONVERSATION_PREFIX = "kong:"


class UnsupportedExchange(ValueError):
    """The route cannot safely deliver the supplied request or response."""


def _object(pairs: list[tuple[str, Any]]) -> dict:
    """Reject duplicate JSON keys rather than reinterpret an ambiguous object."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise UnsupportedExchange("Duplicate JSON key")
        result[key] = value
    return result


def decode_json(value: str | bytes) -> Any:
    """Decode strict JSON without changing integers, floats, booleans or nulls."""

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


def validate_request(request: Any) -> None:
    """Check route coverage before provider invocation, without converting messages.

    The backend validates and converts message content. This route requires full
    supplied history, one choice and client function tools. The Kong plugin
    handles buffered JSON responses only, so all streaming requests are rejected.
    """
    if not isinstance(request, dict):
        raise UnsupportedExchange("Request must be an object")
    _string(request.get("model"), "model")
    if type(request.get("stream", False)) is not bool:
        raise UnsupportedExchange("stream must be a boolean")
    if request.get("stream"):
        raise UnsupportedExchange("Streaming is unavailable on this gateway route")
    if type(request.get("n", 1)) is not int or request.get("n", 1) != 1:
        raise UnsupportedExchange("Exactly one completion choice is required")
    for key in ("functions", "function_call", "previous_response_id", "conversation", "audio"):
        if request.get(key) is not None:
            raise UnsupportedExchange(f"Unsupported request option: {key}")
    tools = request.get("tools", [])
    if not isinstance(tools, list) or any(
        not isinstance(tool, dict) or tool.get("type") != "function" for tool in tools
    ):
        raise UnsupportedExchange("Only client function tools are supported")
    if not isinstance(request.get("messages"), list) or not request["messages"]:
        raise UnsupportedExchange("A complete messages list is required")


def client_calls(response: dict) -> dict[tuple[str | int, ...], str]:
    """Inventory exact response paths and native IDs independently of hook selection.

    No transcript or tool argument mapping is built. Reject incomplete responses,
    unknown executable formats, ambiguous arguments and duplicate native IDs.
    """
    choices = response.get("choices") if isinstance(response, dict) else None
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise UnsupportedExchange("Exactly one complete response choice is required")
    choice = choices[0]
    if type(choice.get("index")) is not int or choice["index"] != 0:
        raise UnsupportedExchange("Unexpected choice index")
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant" or message.get("function_call") is not None:
        raise UnsupportedExchange("Unsupported assistant response")
    calls = message.get("tool_calls") or []
    if not isinstance(calls, list):
        raise UnsupportedExchange("Invalid tool calls")
    if choice.get("finish_reason") != ("tool_calls" if calls else "stop"):
        raise UnsupportedExchange("Response is incomplete or has an unsupported finish reason")
    inventory = {}
    for index, call in enumerate(calls):
        if not isinstance(call, dict) or call.get("type") != "function":
            raise UnsupportedExchange("Only client function tools are supported")
        identifier = _string(call.get("id"), "tool call ID")
        if identifier in inventory.values():
            raise UnsupportedExchange("Duplicate tool call ID")
        function = call.get("function")
        if not isinstance(function, dict):
            raise UnsupportedExchange("Invalid tool function")
        _string(function.get("name"), "tool name")
        if not isinstance(function.get("arguments"), str) or not isinstance(decode_json(function["arguments"]), dict):
            raise UnsupportedExchange("Function arguments must be an unambiguous JSON object")
        inventory[("choices", 0, "message", "tool_calls", index)] = identifier
    return inventory


def _releasable(value: dict) -> bool:
    """Accept a consistent applied outcome for an independently matched named tool.

    A deferred acknowledgement cannot authorize a named call under enforcement.
    Valid grading-failure outcomes still follow the administrator's policy.
    """
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
    user_agent: str | None = None,
    provider: str = "gateway",
) -> bool:
    """Release only when every delivered call has an allowed decision for its unique native ID.

    Send the original provider bodies through the public raw hook; Watcher owns
    conversion, tool selection and policy. A gateway-generated exchange ID is
    supplied, and one without ``CONVERSATION_PREFIX`` is refused before Watcher
    is called. For Chat-Completions-compatible harness traffic, the backend may
    additionally group recognized native session IDs. No settings override or
    client-supplied grouping ID is used.
    """
    _conversation_id(conversation_id)
    validate_request(request)
    inventory = client_calls(response)
    outputs = await watcher.pre_tool_use_hook(
        request_body=request,
        response_body=response,
        url="/v1/chat/completions",
        provider=provider,
        user_agent=user_agent,
        external_ids={"other": conversation_id},
    )
    if not isinstance(outputs, list) or len(outputs) != len(inventory):
        return False
    remaining = set(inventory.values())
    for output in outputs:
        value = output.to_dict()
        identifier = value.get("tool_use_id")
        if not isinstance(identifier, str) or identifier not in remaining:
            return False
        remaining.remove(identifier)
        if "status_code" in value or not _releasable(value):
            return False
    return not remaining


def serve(host: str, port: int) -> None:
    """Start an authenticated gateway-only receiver; credentials remain server-side.

    Kong sends original JSON text in request_json and response_json so Lua's
    numeric conversions cannot change the arguments evaluated by Watcher.
    Bind on loopback or an explicitly isolated service network, never a public port.
    """
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
        """Validate bridge credentials and keep request content out of logs."""

        def log_message(self, format: str, *_args: Any) -> None:
            pass

        def do_POST(self) -> None:
            """Return the Kong plugin's verdict without exposing Watcher error content."""
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
                request = decode_json(body["request_json"])
                if not isinstance(request, dict):
                    raise UnsupportedExchange("Request must be a JSON object")
                if self.path == "/validate":
                    validate_request(request)
                    allowed = True
                else:
                    response = decode_json(body["response_json"])

                    async def run() -> bool:
                        async with AsyncWatcherClient(api_url, api_key=api_key) as watcher:
                            return await evaluate(
                                watcher,
                                request,
                                response,
                                conversation_id=_string(
                                    body.get("metadata", {}).get("watcher_conversation_id"), "gateway conversation ID"
                                ),
                                user_agent=body.get("user_agent"),
                                provider="kong",
                            )

                    allowed = asyncio.run(run())
                self._reply(200, {"verdict": allowed})
            except (ValueError, TypeError, KeyError):
                self._reply(200, {"verdict": False})
            except WatcherAPIError as error:
                # A rejected exchange will not recover by retrying it unchanged.
                permanent = 400 <= error.status_code < 500 and error.status_code not in (408, 429)
                self._reply(200 if permanent else 503, {"verdict": False})
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
    """Start the gateway-private Watcher bridge on the configured listener."""
    serve(host, port)


@app.command("help", hidden=True)
def help_command(context: typer.Context) -> None:
    """Display bridge command help."""
    typer.echo(context.parent.get_help() if context.parent else context.get_help())


def main() -> None:
    """Run the bridge CLI; the native gateway remains the client endpoint."""
    app()


if __name__ == "__main__":
    main()
