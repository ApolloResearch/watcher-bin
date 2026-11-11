"""Native Copilot CLI admission around LiteLLM's ordinary provider routes.

Serve ``app`` with uvicorn and load ``authenticate`` as LiteLLM custom auth.
Discovery and selection use LiteLLM's configured pass-throughs. Inference on
the Responses, Anthropic Messages and Chat Completions routes uses the ordinary
provider and the separately registered Watcher callback. GitHub's verified
numeric account ID selects an operator-provisioned Watcher email. The request
context holds credentials only in memory, outside request metadata and Watcher
recordings. This supports github.com accounts, not GHE hosts.
"""

import gzip
import io
import json
import os
import re
import zlib
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple
from uuid import UUID

import asyncpg
import httpx
import litellm
import structlog
import yaml
import zstandard
from fastapi import HTTPException
from litellm.integrations.custom_logger import CustomLogger
from litellm.llms.github_copilot.per_user_auth import GithubCopilotUserSession
from litellm.proxy._types import UserAPIKeyAuth
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from watcher_litellm.copilot_sessions import Conversation, register_task
from watcher_litellm.proxy_auth import account_email

# Native protocol identity and selection headers only. The client cannot set
# provider routing, Watcher identity or LiteLLM's internal callback metadata.
_PROVIDER_HEADERS = frozenset(
    {
        "copilot-integration-id",
        "editor-version",
        "editor-plugin-version",
        "user-agent",
        "x-github-api-version",
        "openai-intent",
        "copilot-harness-id",
        "x-client-session-id",
        "x-agent-task-id",
        "x-parent-agent-id",
        "copilot-session-token",
        "x-request-id",
    }
)
_RESPONSE_FIELDS = frozenset(
    {
        "model",
        "input",
        "instructions",
        "tools",
        "tool_choice",
        "parallel_tool_calls",
        "stream",
        "stream_options",
        "temperature",
        "top_p",
        "max_output_tokens",
        "reasoning",
        "text",
        "store",
        "include",
        "prompt_cache_key",
        "prompt_cache_retention",
        "truncation",
        "service_tier",
        "safety_identifier",
        "user",
        "metadata",
    }
)
_MESSAGES_FIELDS = frozenset(
    {
        "model",
        "messages",
        "system",
        "max_tokens",
        "stream",
        "temperature",
        "top_p",
        "top_k",
        "stop_sequences",
        "tools",
        "tool_choice",
        "thinking",
        "output_config",
        "service_tier",
        "metadata",
    }
)
_CHAT_FIELDS = frozenset(
    {
        "model",
        "messages",
        "tools",
        "tool_choice",
        "parallel_tool_calls",
        "stream",
        "stream_options",
        "temperature",
        "top_p",
        "max_tokens",
        "max_completion_tokens",
        "stop",
        "presence_penalty",
        "frequency_penalty",
        "seed",
        "response_format",
        "reasoning_effort",
        "snippy",
        "user",
        "metadata",
    }
)


class _Inference(NamedTuple):
    """One native inference route and what its untrusted request may contain.

    ``target`` is the LiteLLM route that serves it. ``fields`` are the accepted
    top-level body keys. ``tool_types`` are the client tool types the Watcher
    callback can hold, with ``None`` for a tool that has no type; a
    provider-hosted tool would run before Watcher sees the response. On
    Responses, a ``namespace`` groups client tools whose definitions load on
    demand, and ``tool_search`` lets GitHub load only those supplied definitions.
    ``headers`` are the client headers sent on to GitHub.
    """

    target: str
    fields: frozenset[str]
    tool_types: frozenset[str | None]
    headers: frozenset[str] = _PROVIDER_HEADERS


_INFERENCE = {
    "/copilot/responses": _Inference(
        "/responses", _RESPONSE_FIELDS, frozenset({"function", "custom", "namespace", "tool_search"})
    ),
    # LiteLLM sets X-Initiator from the message roles on Responses and Chat
    # Completions, but not on Messages, so only Messages forwards the client's.
    "/copilot/v1/messages": _Inference(
        "/v1/messages",
        _MESSAGES_FIELDS,
        frozenset({"custom", None}),
        _PROVIDER_HEADERS | {"anthropic-beta", "x-initiator"},
    ),
    "/copilot/chat/completions": _Inference("/chat/completions", _CHAT_FIELDS, frozenset({"function"})),
}
_DISCOVERY = frozenset({"/copilot/meta", "/copilot/models", "/copilot/auto"})
_HEALTH = frozenset({"/health/liveliness", "/health/readiness"})
_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_NAMESPACED_TOOL_TYPES: frozenset[str | None] = frozenset({"function", "custom"})
# Loaded tool groups can appear as namespaces; their inner tools are still checked.
_LOADED_TOOL_TYPES: frozenset[str | None] = frozenset({"function", "custom", "namespace"})
_MAX_BODY = 32 * 1024 * 1024
logger = structlog.get_logger(__name__)


class _GithubAccount(BaseModel):
    """Require the immutable numeric ID in GitHub's external user response."""

    id: int = Field(strict=True, gt=0)


class NativeRequest(BaseModel):
    """Verified account, durable conversation and secret provider-only context."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    user_id: str
    user_email: str
    conversation: Conversation
    provider_session: GithubCopilotUserSession = Field(repr=False, exclude=True)
    provider_headers: dict[str, str] = Field(repr=False, exclude=True)


current_request: ContextVar[NativeRequest | None] = ContextVar("copilot_request", default=None)


async def authenticate(request: Request, api_key: str) -> UserAPIKeyAuth:
    """Accept only middleware-admitted inference and health checks.

    Discovery has its own fixed pass-through configuration. No master-key
    exception opens another inference route on the native-only gateway.
    """
    identity = current_request.get()
    if identity is not None:
        return UserAPIKeyAuth(user_id=identity.user_id, user_email=identity.user_email, user_role="internal_user")
    if request.url.path in _HEALTH | _DISCOVERY:
        return UserAPIKeyAuth()
    raise HTTPException(401, "Use the native Copilot gateway endpoint")


class NativeProviderCallback(CustomLogger):
    """Supply credentials to GitHub's provider without replacing Watcher hooks.

    Register this instance and the original Watcher callback separately: LiteLLM
    checks hooks declared on each concrete callback class. Subclassing the
    Watcher callback can silently skip its inherited enforcement hooks.
    """

    async def async_pre_call_deployment_hook(
        self, kwargs: dict[str, Any], call_type: str | None = None
    ) -> dict[str, Any]:
        """Attach native credentials and register GPT Responses mode before provider selection."""
        identity = current_request.get()
        if identity is not None:
            # Responses and Messages calls name the provider; Chat Completions
            # calls reach this hook before LiteLLM derives it from the model's
            # ``provider/`` prefix, so read that prefix when no name is set.
            provider = kwargs.get("custom_llm_provider") or str(kwargs.get("model", "")).partition("/")[0]
            if provider != "github_copilot":
                raise HTTPException(400, "Native Copilot models must use the GitHub Copilot provider")
            if call_type == "aresponses":
                model = str(kwargs["model"]).removeprefix("github_copilot/")
                if model.startswith("gpt-"):
                    litellm.register_model(
                        {f"github_copilot/{model}": {"mode": "responses", "litellm_provider": "github_copilot"}},
                        persist_across_reloads=False,
                        custom_llm_provider="github_copilot",
                    )
            kwargs["github_copilot_user_session"] = identity.provider_session
            headers = identity.provider_headers.copy()
            if "x-initiator" in headers and _returns_tool_results(kwargs.get("messages")):
                headers["x-initiator"] = "agent"
            kwargs["extra_headers"] = headers
        return kwargs


def _returns_tool_results(messages: object) -> bool:
    """Whether Messages input ends in tool results only, which Copilot sends as agent-initiated."""
    if not isinstance(messages, list) or not messages or not isinstance(messages[-1], dict):
        return False
    content = messages[-1].get("content")
    return (
        messages[-1].get("role") == "user"
        and isinstance(content, list)
        and bool(content)
        and all(isinstance(block, dict) and block.get("type") == "tool_result" for block in content)
    )


provider_callback = NativeProviderCallback()


class CopilotGateway:
    """Validate native identity before passing inference into LiteLLM.

    ``users`` maps immutable GitHub numeric IDs to Watcher email identities.
    Only fixed discovery, the three inference routes and health are exposed.
    The entire untrusted body is validated before any provider request; routing
    overrides are refused. Compressed bodies are bounded after decompression as well.
    An HTTP client can be supplied for offline GitHub-boundary tests.
    """

    def __init__(self, downstream: ASGIApp, users: dict[str, str], github: httpx.AsyncClient | None = None) -> None:
        self.downstream = downstream
        self.users = users
        self.github = github
        for user_id, email in users.items():
            if not user_id.isdecimal():
                raise ValueError("Copilot users must be keyed by numeric GitHub account ID")
            account_email(UserAPIKeyAuth(user_id="github:" + user_id, user_email=email))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http" or scope["path"] in _HEALTH:
            await self.downstream(scope, receive, send)
            return
        path = scope["path"]
        inference = _INFERENCE.get(path)
        if path not in _DISCOVERY and inference is None:
            await JSONResponse({"error": "Unknown native Copilot route"}, status_code=404)(scope, receive, send)
            return
        request = Request(scope, receive)
        if request.method != ("GET" if path in {"/copilot/meta", "/copilot/models"} else "POST"):
            await JSONResponse({"error": "Method not allowed"}, status_code=405)(scope, receive, send)
            return
        try:
            token = request.headers.get("authorization", "")
            if not token.startswith("Bearer ") or not token[7:] or any(not "!" <= char <= "~" for char in token[7:]):
                raise HTTPException(401, "GitHub bearer credential required")
            # Verify before reading or expanding input. Both inference and stock
            # pass-throughs can parse JSON into a much larger object graph.
            user = await self._user(token)
            body = await _body(request)
            if inference is None:
                if request.method == "GET" and body:
                    raise _refused("Discovery GET requests must not contain a body")
                identity = None
                clean_scope = {**scope, "headers": self._headers(request, len(body))}
            else:
                try:
                    payload = json.loads(body)
                except (ValueError, RecursionError) as error:
                    raise _refused("Invalid native Copilot request") from error
                identity = await self._identity(request, token, payload, user, inference)
                # Provider labels are not trusted Watcher identity or LiteLLM routing metadata.
                payload.pop("metadata", None)
                payload.pop("user", None)
                body = json.dumps(payload).encode()
                clean_scope = {
                    **scope,
                    "path": inference.target,
                    "raw_path": inference.target.encode(),
                    "query_string": b"",
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        (b"user-agent", request.headers.get("user-agent", "GitHubCopilotCLI").encode()),
                    ],
                }
        except HTTPException as error:
            await JSONResponse({"error": error.detail}, status_code=error.status_code)(scope, receive, send)
            return

        reset = current_request.set(identity)
        try:
            await self.downstream(clean_scope, _body_receiver(body, receive), send)
        finally:
            current_request.reset(reset)

    async def _identity(
        self, request: Request, token: str, payload: Any, user: UserAPIKeyAuth, inference: _Inference
    ) -> NativeRequest:
        """Register validated client IDs for an already verified GitHub account.

        Only parsing of client-controlled data returns 400. Storage failures
        are classified separately from client errors and account verification.
        """
        session_id = _uuid_header(request, "x-client-session-id")
        task_id = _uuid_header(request, "x-agent-task-id")
        parent_id = _uuid_header(request, "x-parent-agent-id") if request.headers.get("x-parent-agent-id") else None
        if not isinstance(payload, dict) or not isinstance(payload.get("model"), str):
            raise _refused("Native inference requires a model and object body")
        # LiteLLM's proxy runs a comma-separated Chat Completions model as one
        # paid generation per name. A wildcard route matches only the start of a
        # name, so "claude-x\nanything" would be served as claude-x while Watcher
        # records the whole string as the model.
        if not _MODEL_NAME.fullmatch(payload["model"]):
            raise _refused("Unsupported native model name")
        if unsupported := payload.keys() - inference.fields:
            raise _refused("Unsupported native request fields", unsupported)
        tools = payload.get("tools", [])
        if not isinstance(tools, list):
            raise _refused("Native tools must be a list")
        refused = _refused_tool_types(tools, inference.tool_types) + _refused_loaded_tool_types(payload.get("input"))
        if refused:
            raise _refused("Unsupported native tool types", refused)
        try:
            conversation = await register_task(user, session_id, task_id, parent_id, payload)
        except (asyncpg.PostgresError, OSError, KeyError, ValueError) as error:
            logger.warning("copilot_session_storage_unavailable", error_type=type(error).__name__)
            raise HTTPException(503, "Copilot session storage unavailable") from error
        return NativeRequest(
            user_id=user.user_id,
            user_email=account_email(user),
            conversation=conversation,
            provider_session=GithubCopilotUserSession(
                token=token.removeprefix("Bearer "), api_base="https://api.githubcopilot.com"
            ),
            provider_headers={key: value for key, value in request.headers.items() if key in inference.headers},
        )

    async def _user(self, authorization: str) -> UserAPIKeyAuth:
        """Verify on GitHub, retaining neither tokens nor a stale authorization cache."""
        try:
            if self.github is not None:
                response = await self.github.get(
                    "https://api.github.com/user", headers={"Authorization": authorization}
                )
            else:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.get("https://api.github.com/user", headers={"Authorization": authorization})
        except (httpx.HTTPError, TimeoutError) as error:
            logger.warning("copilot_github_unavailable", error_type=type(error).__name__)
            raise HTTPException(503, "GitHub identity verification unavailable") from error
        if response.status_code == 403 and (
            response.headers.get("x-ratelimit-remaining") == "0" or "retry-after" in response.headers
        ):
            logger.warning("copilot_github_rate_limited", status_code=response.status_code)
            raise HTTPException(503, "GitHub identity verification rate limited")
        if response.status_code in {401, 403}:
            raise HTTPException(401, "GitHub authentication rejected")
        if response.status_code != 200:
            logger.warning("copilot_github_unavailable", status_code=response.status_code)
            raise HTTPException(503, "GitHub identity verification unavailable")
        try:
            account = _GithubAccount.model_validate(response.json())
        except ValueError as error:
            logger.warning("copilot_github_invalid_response", error_type=type(error).__name__)
            raise HTTPException(503, "GitHub identity verification unavailable") from error
        user_id = str(account.id)
        if user_id not in self.users:
            raise HTTPException(403, "GitHub account is not mapped to a Watcher identity")
        return UserAPIKeyAuth(user_id="github:" + user_id, user_email=self.users[user_id])

    def _headers(self, request: Request, body_length: int) -> list[tuple[bytes, bytes]]:
        """Retain native discovery headers, describing the already decoded body."""
        allowed = _PROVIDER_HEADERS | {"accept", "authorization", "content-type"}
        return [(key, value) for key, value in request.scope["headers"] if key.decode().lower() in allowed] + [
            (b"content-length", str(body_length).encode())
        ]


def _refused(detail: str, names: list[str] | set[str] | None = None) -> HTTPException:
    """A 400 naming what the front door refused, with a safe diagnostic log.

    ``names`` are untrusted field names, header names or tool types. Each
    is cut to 64 characters and at most ten are returned to the client. Logs
    contain only the fixed refusal reason and the number of rejected names.
    """
    shown = sorted({name[:64] for name in names or ()})[:10]
    logger.warning("copilot_request_refused", reason=detail, rejected_count=len(names or ()))
    return HTTPException(400, f"{detail}: {', '.join(shown)}" if shown else detail)


def _uuid_header(request: Request, name: str) -> UUID:
    """A native session or task header as a UUID, refusing a missing or malformed one by name."""
    try:
        return UUID(request.headers.get(name, ""))
    except ValueError as error:
        raise _refused("Invalid native Copilot header", [name]) from error


def _refused_tool_types(tools: list[Any], allowed: frozenset[str | None]) -> list[str]:
    """The tool types in ``tools`` outside ``allowed``, including those inside a namespace.

    A tool without a type reads as ``None``. A tool that is not an object, or
    whose type is not a string, is reported by its Python type name. Namespaces
    may hold only plain client tools.
    """
    refused: list[str] = []
    for tool in tools:
        kind = tool.get("type") if isinstance(tool, dict) else None
        if not isinstance(tool, dict):
            refused.append(type(tool).__name__)
        elif not isinstance(kind, str | None):
            refused.append(type(kind).__name__)
        elif kind not in allowed:
            refused.append(kind or "untyped")
        elif kind == "namespace":
            inner = tool.get("tools")
            if not isinstance(inner, list):
                refused.append("namespace")
            else:
                refused.extend("namespace." + name for name in _refused_tool_types(inner, _NAMESPACED_TOOL_TYPES))
    return refused


def _refused_loaded_tool_types(items: object) -> list[str]:
    """Refused tool types in the ``tool_search_output`` items of a Responses ``input``, each prefixed ``input.``.

    Such an item hands the model tool definitions outside ``tools``, so they
    get the same check. An item whose ``tools`` is not a list is refused.
    """
    refused: list[str] = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and item.get("type") == "tool_search_output":
            tools = item.get("tools")
            if not isinstance(tools, list):
                refused.append("input.tool_search_output")
            else:
                refused.extend("input." + name for name in _refused_tool_types(tools, _LOADED_TOOL_TYPES))
    return refused


def _body_receiver(body: bytes, receive: Receive) -> Receive:
    """Replay the bounded, decoded body once, then preserve disconnect events."""
    pending = True

    async def body_receive() -> Message:
        nonlocal pending
        if pending:
            pending = False
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return body_receive


async def _body(request: Request) -> bytes:
    """Decode a bounded native request without buffering an unlimited gzip/zstd body."""
    encoded = bytearray()
    async for chunk in request.stream():
        if len(encoded) + len(chunk) > _MAX_BODY:
            raise HTTPException(413, "Native request too large")
        encoded.extend(chunk)
    encoding = request.headers.get("content-encoding", "identity")
    try:
        if encoding == "identity":
            return bytes(encoded)
        if encoding == "zstd":
            with zstandard.ZstdDecompressor().stream_reader(bytes(encoded)) as reader:
                decoded = reader.read(_MAX_BODY + 1)
        elif encoding == "gzip":
            with gzip.GzipFile(fileobj=io.BytesIO(encoded)) as reader:
                decoded = reader.read(_MAX_BODY + 1)
        else:
            raise HTTPException(415, "Unsupported content encoding")
    except (EOFError, gzip.BadGzipFile, zlib.error, zstandard.ZstdError) as error:
        raise HTTPException(400, "Invalid native Copilot request") from error
    if len(decoded) > _MAX_BODY:
        raise HTTPException(413, "Native request too large")
    return decoded


@lru_cache(maxsize=1)
def _gateway() -> CopilotGateway:
    # LiteLLM imports configured callbacks during its own startup. Importing its
    # ASGI application at module load would introduce a callback import cycle.
    from litellm.proxy.proxy_server import app as litellm_app

    if os.environ.get("WATCHER_AUTH_MODE") != "proxy":
        raise ValueError("Native Copilot requires WATCHER_AUTH_MODE=proxy")
    users = yaml.safe_load(Path(os.environ["WATCHER_COPILOT_USERS_FILE"]).read_text())
    if not isinstance(users, dict) or not users:
        raise ValueError("WATCHER_COPILOT_USERS_FILE must contain a nonempty ID-to-email mapping")
    if any(not isinstance(user_id, str) for user_id in users):
        raise ValueError("Copilot users must be keyed by quoted numeric GitHub account ID")
    return CopilotGateway(litellm_app, users)


async def app(scope: Scope, receive: Receive, send: Send) -> None:
    """Uvicorn ASGI entry point; use one worker per pod and shared PostgreSQL state."""
    await _gateway()(scope, receive, send)
