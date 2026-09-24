"""Watcher API OAuth/token exchange — refresh token is httpOnly cookie only, not JSON."""

from __future__ import annotations

from pydantic import BaseModel

REFRESH_TOKEN_COOKIE_NAME = "refresh_token"


class AuthExchangeResult(BaseModel):
    """Result of ``auth_callback`` or ``auth_refresh`` on :class:`AsyncWatcherClient`.

    ``refresh_token`` comes from the ``Set-Cookie`` header, not the JSON body.
    """

    access_token: str
    refresh_token: str
    user: dict[str, str | None] | None = None


class AuthLogoutResult(BaseModel):
    """Result of ``auth_logout`` (``POST /v1/auth/logout``)."""

    status: str
