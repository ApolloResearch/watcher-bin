"""Adapt authenticated LiteLLM accounts to Watcher's trusted-proxy interface.

Only the gateway process holds the proxy token. The operator must provision
account email addresses from a trusted source and restrict access to Watcher.
"""

import json
import os
import re
from uuid import NAMESPACE_URL, uuid5

import httpx
from fastapi import HTTPException
from litellm.constants import LITELLM_PROXY_MASTER_KEY_ALIAS
from litellm.proxy._types import UserAPIKeyAuth

from watcher_sdk import AsyncWatcherClient


def account_email(user: UserAPIKeyAuth) -> str:
    """Return a normalized, administrator-provisioned account email.

    Require a nonempty, nondefault ``user_id`` and a valid ``user_email``;
    reject the proxy master-key identity. Raise HTTP 401 for missing or invalid
    attribution. The caller supplies LiteLLM's authenticated object, never
    constructs it from unverified client headers or request-body fields.
    """
    email = user.user_email.strip().lower() if user.user_email else ""
    if (
        not user.user_id
        or not user.user_id.strip()
        or user.user_id == "default_user_id"
        or user.api_key == LITELLM_PROXY_MASTER_KEY_ALIAS
        or not email.isascii()
        or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
        or len(email) > 256
        or any(ord(char) < 32 or ord(char) == 127 for char in email)
    ):
        raise HTTPException(401, "Watcher requires a personal LiteLLM account with an account ID and email")
    return email


def require_proxy_configuration() -> None:
    """Refuse missing server credentials before paying for provider generation."""
    for setting in ("WATCHER_API_URL", "WATCHER_PROXY_AUTH_TOKEN"):
        if not os.environ.get(setting, "").strip():
            raise HTTPException(503, f"{setting} must be configured on the Watcher gateway")


def account_session(user: UserAPIKeyAuth, session_id: str) -> str:
    """Namespace client IDs by the authenticated account, stable across key rotation.

    JSON framing keeps arbitrary client IDs from colliding with the account ID.
    The caller must use this result only once, at the Watcher request boundary.
    ``account_email`` validates the account first and may raise HTTP 401.
    """
    account_email(user)
    identity = json.dumps(["watcher-litellm", user.user_id, session_id], separators=(",", ":"))
    return "litellm:" + str(uuid5(NAMESPACE_URL, identity))


def proxy_client(user: UserAPIKeyAuth) -> AsyncWatcherClient:
    """Create an owner-bound client; the caller must enter it with ``async with``.

    Require ``WATCHER_API_URL`` and a nonblank ``WATCHER_PROXY_AUTH_TOKEN``.
    Optional ``WATCHER_PROXY_HEADER_USER`` and ``WATCHER_PROXY_HEADER_ROLE``
    default to ``x-forwarded-user`` and ``x-forwarded-user-role``. Send the
    validated account email and member role. Invalid attribution raises HTTP
    401; missing settings or an empty token raise configuration errors.
    """
    token = os.environ["WATCHER_PROXY_AUTH_TOKEN"]
    if not token.strip():
        raise ValueError("WATCHER_PROXY_AUTH_TOKEN must not be empty")
    http = httpx.AsyncClient(
        base_url=os.environ["WATCHER_API_URL"],
        headers={
            "x-auth-proxy-token": token,
            os.environ.get("WATCHER_PROXY_HEADER_USER", "x-forwarded-user"): account_email(user),
            os.environ.get("WATCHER_PROXY_HEADER_ROLE", "x-forwarded-user-role"): "member",
        },
    )
    return AsyncWatcherClient(os.environ["WATCHER_API_URL"], httpx_client=http)
