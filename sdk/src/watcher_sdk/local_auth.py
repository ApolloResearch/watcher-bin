"""Authenticate local SDK integrations with the installed Watcher's saved sign-in."""

import asyncio
import errno
import hashlib
import http.cookiejar
import json
import os
import re
import stat
import tempfile
from collections.abc import AsyncGenerator, AsyncIterator, Generator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from watcher_sdk.auth_support import REFRESH_TOKEN_COOKIE_NAME
from watcher_sdk.client import AsyncWatcherClient, watcher_sdk_user_agent
from watcher_sdk.errors import WatcherAPIError, WatcherAuthenticationError, WatcherTimeoutError


class _Login(BaseModel):
    model_config = ConfigDict(extra="allow")

    access_token: str = Field(pattern=r"^[\x21-\x7e]+$", repr=False)
    refresh_token: str | None = Field(default=None, pattern=r"^[\x21-\x7e]+$", repr=False)
    xylon_url: str
    updated_at: str | None = None


class _RefreshedToken(BaseModel):
    access_token: str = Field(pattern=r"^[\x21-\x7e]+$", repr=False)


def _api_url(value: str) -> httpx.URL:
    url = httpx.URL(value)
    if url.scheme not in {"http", "https"} or not url.host or url.userinfo or url.query or url.fragment:
        raise ValueError("Watcher URL must be HTTP or HTTPS without credentials, query or fragment")
    path = url.path.rstrip("/")
    return url.copy_with(path=path if path.endswith("/api") else path + "/api")


_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


class InsecureLoginURLError(ValueError):
    """A sign-in URL uses plain HTTP to a host other than this machine.

    Its message is fixed text with no URL or credential, so command-line tools
    may show it to explain why the sign-in was refused.
    """


def _login_api_url(value: str) -> httpx.URL:
    """Normalize a URL that will carry bearer and refresh tokens.

    Sign-in, refresh and saved sign-in requests send long-lived secrets, so they
    require HTTPS except to this machine, matching Watcher's credential helpers.
    API-key clients keep accepting any HTTP URL.
    """
    url = _api_url(value)
    if url.scheme == "http" and url.host.lower() not in _LOOPBACK_HOSTS:
        raise InsecureLoginURLError("Watcher sign-in requires an HTTPS URL unless the server runs on this machine")
    return url


def _credential_name(url: httpx.URL) -> str:
    hostname = url.host.lower()
    if hostname in _LOOPBACK_HOSTS:
        return "local"
    if hostname == "app.apolloresearch.ai":
        return "production"
    if hostname.startswith("watcher-") and hostname.endswith(".apolloresearch.ai"):
        environment = hostname.removeprefix("watcher-").removesuffix(".apolloresearch.ai")
        if environment in {"dev", "staging", "preprod"}:
            return environment
    return re.sub(r"[^a-z0-9._-]+", "_", hostname)


def watcher_login_superseded(state_dir: Path, base_url: str) -> bool:
    """Whether Watcher sends another identity than its saved sign-in to ``base_url``.

    Mirrors Watcher Live's request-credential precedence. A credential helper
    (``credential_helpers/<sha256 of the API URL>/config.json``, even a broken or
    symlinked one) always replaces the saved sign-in, and Watcher refuses to write
    one while it exists. Captured hook headers (``hook_headers/<env>.json``)
    replace it only when they carry ``Authorization`` or ``x-api-key``; routing
    headers coexist with the sign-in. An unreadable headers file is a fatal
    configuration error for Watcher, so it also counts as superseded here.
    """
    url = _api_url(base_url)
    root = state_dir.expanduser()
    key = hashlib.sha256(str(url).encode()).hexdigest()
    if os.path.lexists(root / "credential_helpers" / key / "config.json"):
        return True
    headers_file = root / "hook_headers" / f"{_credential_name(url)}.json"
    if not os.path.lexists(headers_file):
        return False
    try:
        headers = json.loads(_read_login_file(headers_file))
    except (OSError, ValueError):
        return True
    if not isinstance(headers, dict):
        return True
    return any(str(name).lower() in {"authorization", "x-api-key"} for name in headers)


class UnsafeLoginStoreError(PermissionError):
    """Another local account owns, or can write, a saved sign-in or the folder holding it.

    Such an account could swap in its own sign-in, so this user's sessions would
    upload into its account. The message is fixed text without a path.
    """

    def __init__(self) -> None:
        super().__init__("Another account can change the saved sign-in or its folder")


class LinkedCredentialFolderError(OSError):
    """The folder a new saved sign-in would go in is a symbolic link, even one whose target is missing.

    Sign-in refuses such a folder before creating or changing anything, because the
    link could point anywhere. The system's own errors ("File exists", "Not a
    directory" or "Too many levels of symbolic links") do not name this cause, so
    this error does. It is an OSError with ``errno.ELOOP``, so handlers for
    filesystem failures still catch it. Its message is fixed text without the path,
    so command-line tools may show it; ``filename`` holds the folder.
    """

    def __init__(self, folder: Path) -> None:
        super().__init__(errno.ELOOP, "The credential folder must not be a symbolic link", str(folder))

    def __str__(self) -> str:
        return str(self.strerror)


def _require_private(info: os.stat_result) -> None:
    """Refuse a file or folder that another account owns or can write. POSIX only."""
    if info.st_uid != os.geteuid() or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise UnsafeLoginStoreError


def _make_private_folder(folder: Path) -> None:
    """Create ``folder`` and any missing parents with mode 0700, and set ``folder`` itself to 0700.

    ``Path.mkdir(parents=True)`` gives new parents the umask's mode (0777 under
    umask 0) and leaves an existing folder as it is, so neither is enough here.
    Existing parents keep their modes. A folder another account owns raises
    UnsafeLoginStoreError instead of being used.

    ``folder`` itself must be a real folder, not a symbolic link or a file: either
    raises OSError and nothing changes mode. A link, even one whose target is
    missing, is refused before anything is created, with LinkedCredentialFolderError.
    The owner check and the mode change both go through one open handle
    on the folder, opened without following a link, so whoever can write the folder
    above it cannot swap in a link after that check and have this change the mode
    of a file or folder elsewhere.
    """
    if folder.is_symlink():
        raise LinkedCredentialFolderError(folder)
    for missing in reversed([path for path in (folder, *folder.parents) if not path.exists()]):
        missing.mkdir(mode=0o700, exist_ok=True)
    descriptor = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if os.fstat(descriptor).st_uid != os.geteuid():
            raise UnsafeLoginStoreError
        os.fchmod(descriptor, 0o700)
    finally:
        os.close(descriptor)


def _read_login_file(path: Path, *, private: bool = False) -> bytes:
    """Read a regular credential file, rejecting payloads larger than 64 KiB.

    With ``private``, the file and the folder holding it must belong to the current
    user and be writable by no one else; otherwise UnsafeLoginStoreError is raised.
    The file is checked after it is opened, so it cannot be swapped in between.
    """
    if private:
        _require_private(path.parent.stat())
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Credentials must be stored in a regular file")
    with path.open("rb") as source:
        if private:
            _require_private(os.fstat(source.fileno()))
        contents = source.read(65537)
    if len(contents) > 65536:
        raise ValueError("Credential file exceeds its size limit")
    return contents


# RFC 6265 cookie-value characters: printable ASCII except double quote, comma, semicolon and backslash.
_COOKIE_VALUE = re.compile(r"[\x21\x23-\x2b\x2d-\x3a\x3c-\x5b\x5d-\x7e]+")


def _cookie_jar_refusing_all() -> http.cookiejar.CookieJar:
    return http.cookiejar.CookieJar(policy=http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))


class WatcherLoginAuth(httpx.Auth):
    """Use the current user's Watcher sign-in in an asynchronous HTTP client.

    Reads the installed client's credential store on each request and retries one
    token rejected with HTTP 401 after refresh. A sign-in without a refresh token
    returns that 401 to the caller without refreshing; other statuses do not refresh.
    Missing, unreadable or destination-mismatched credentials raise WatcherAuthenticationError.
    The saved server must match ``base_url``, including
    its port and path. A missing or rejected sign-in never falls back to another identity.
    Refresh uses Watcher's existing per-file lock and updates that same credential file.

    ``state_dir`` defaults to APOLLO_MONITOR_HOME or ~/.apollo_monitor. This requires
    the same OS user as Watcher and its POSIX credential store, but no Watcher Python
    package or running daemon. Use explicit service credentials for remote integrations.

    The token refresh never goes through the HTTP client that uses this auth, so
    that client's cookie jar, hooks, redirect setting and connection options
    (``verify``, ``cert``, ``proxy``, ``trust_env``, ``transport``) never apply to it.
    By default the refresh goes out on a single-use connection that the SDK owns,
    which follows no redirect, keeps no cookie, and takes its proxy and certificate
    settings from the environment, such as HTTPS_PROXY and SSL_CERT_FILE. Pass
    ``transport`` to send it through that httpx transport instead, for TLS, client
    certificates or a proxy set up in code. The SDK hands the one request to the
    transport directly, with no redirects or cookie jar, and never closes it.
    A refresh answered with a redirect raises WatcherAuthenticationError and saves nothing.
    """

    _login_instruction = "Sign in to Watcher"
    # Watcher sets the modes of its own store. Stores this SDK creates are
    # required to be private on every read; see SDKLoginAuth.
    _private_store = False

    def __init__(
        self, base_url: str, *, state_dir: Path | None = None, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.base_url = _login_api_url(base_url)
        self.transport = transport
        self.state_dir = state_dir or Path(os.environ.get("APOLLO_MONITOR_HOME") or Path.home() / ".apollo_monitor")
        # Keep the filename and flock protocol compatible with Watcher Live's credential store.
        self.credential_file = self.state_dir.expanduser() / "credentials" / f"{_credential_name(self.base_url)}.json"

    def validate(self) -> None:
        """Check local sign-in availability and server binding without making a request."""
        self._read_login()

    def validate_project_location(self, project: Path) -> None:
        """Reject project-contained stores before sign-in or refresh can write credentials.

        Resolves the project, store, credential directory and file independently
        so symlinks cannot place either saved tokens or temporary writes in the project.
        Checks paths only; the store and credential file need not exist yet.
        """
        project = project.expanduser().resolve()
        paths = (self.credential_file.parent.parent, self.credential_file.parent, self.credential_file)
        if any(path.resolve().is_relative_to(project) for path in paths):
            raise ValueError("The saved sign-in must be stored outside the project")

    def _superseded(self) -> bool:
        """Watcher's own store ignores a sign-in once headers or a helper own the server."""
        return watcher_login_superseded(self.state_dir, str(self.base_url))

    def _read_login(self) -> _Login:
        if self._superseded():
            raise WatcherAuthenticationError(
                401,
                "watcher_login_superseded",
                "Watcher authenticates this server with hook headers or a credential helper, which the SDK "
                "cannot reuse; use an SDK sign-in or an API key",
            )
        try:
            login = _Login.model_validate_json(_read_login_file(self.credential_file, private=self._private_store))
            if _api_url(login.xylon_url) != self.base_url:
                raise ValueError("Saved sign-in belongs to a different server")
            return login
        except UnsafeLoginStoreError:
            raise WatcherAuthenticationError(
                401,
                "watcher_login_unsafe",
                f"{self._login_instruction} again: another account can change the saved sign-in",
            ) from None
        except (OSError, ValueError, httpx.InvalidURL):
            raise WatcherAuthenticationError(
                401, "watcher_login_unavailable", f"{self._login_instruction} for this exact API URL first"
            ) from None

    @asynccontextmanager
    async def _refresh_lock(self) -> AsyncIterator[None]:
        """Share Watcher's lock across the read, token exchange and atomic write."""
        if os.name != "posix":
            raise RuntimeError("Watcher sign-in refresh requires a POSIX credential store")
        import fcntl

        descriptor = os.open(self.credential_file.with_suffix(".lock"), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                async with asyncio.timeout(30):
                    while True:
                        try:
                            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            await asyncio.sleep(0.05)
            except TimeoutError:
                raise WatcherTimeoutError("Timed out waiting to refresh the saved sign-in; retry the request") from None
            yield
        finally:
            os.close(descriptor)

    def _save_login(self, login: _Login) -> None:
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.credential_file.parent, delete=False
            ) as output:
                temporary = Path(output.name)
                output.write(login.model_dump_json(indent=2) + "\n")
            temporary.replace(self.credential_file)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _apply_login(self, request: httpx.Request, login: _Login) -> None:
        request.headers.pop("x-api-key", None)
        request.headers["Authorization"] = f"Bearer {login.access_token}"

    async def _send_refresh(self, refresh_request: httpx.Request) -> httpx.Response:
        """Send the refresh exchange and return its fully read answer, following no redirect.

        The refresh never goes through the caller's client. That client may follow
        redirects and keep cookies. Watcher answers a refresh by setting the new
        refresh token as a cookie, so the client's jar would keep it, and when httpx
        follows a redirect it fills in the Cookie header from that jar. A cookie
        matches every port of its host, so a redirect to another port would carry
        the token there.

        Without ``self.transport`` the request goes out on a single-use client that
        follows no redirect and keeps no cookie. With it, the request is handed to
        the transport directly: a transport sends exactly one request, and no client
        sits in between to follow a redirect or fill a cookie jar. The caller owns
        that transport and may share it with its own client, so it is never closed here.
        """
        if self.transport is None:
            async with httpx.AsyncClient(follow_redirects=False, cookies=_cookie_jar_refusing_all()) as refresher:
                return await refresher.send(refresh_request)
        response = await self.transport.handle_async_request(refresh_request)
        # An httpx client would attach the request itself; reading the rotated
        # refresh cookie off the response needs it.
        response.request = refresh_request
        try:
            await response.aread()
        finally:
            await response.aclose()
        return response

    def sync_auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        raise RuntimeError("WatcherLoginAuth requires httpx.AsyncClient")

    async def async_auth_flow(self, request: httpx.Request) -> AsyncGenerator[httpx.Request, httpx.Response]:
        """Authenticate only the configured server and refresh a rejected token once."""
        target = self.base_url
        if (
            request.url.scheme != target.scheme
            or request.url.host != target.host
            or request.url.port != target.port
            or not request.url.path.startswith(target.path + "/")
        ):
            raise ValueError("Watcher sign-in cannot authenticate a different server or API path")
        await request.aread()
        login = self._read_login()
        self._apply_login(request, login)
        response = yield request
        if response.status_code != 401 or not login.refresh_token or request.url.path.endswith("/auth/refresh"):
            return
        await response.aread()
        async with self._refresh_lock():
            current = self._read_login()
            if current.access_token == login.access_token:
                # A token that a Cookie header cannot carry intact cannot be refreshed.
                if not current.refresh_token or not _COOKIE_VALUE.fullmatch(current.refresh_token):
                    raise WatcherAuthenticationError(401, "watcher_login_expired", f"{self._login_instruction} again")
                refresh_request = httpx.Request(
                    "POST",
                    str(target) + "/v1/auth/refresh",
                    # Watcher's refresh route reads the refresh token from this cookie, as it
                    # does the Analyzer's, and requires the empty JSON body. Production's
                    # firewall rejects any request that has no User-Agent header.
                    headers={
                        "Cookie": f"{REFRESH_TOKEN_COOKIE_NAME}={current.refresh_token}",
                        "User-Agent": watcher_sdk_user_agent(),
                    },
                    json={},
                    # Only the timeout carries over from the caller's request. Its other
                    # extensions belong to the caller: a "trace" callback, for one, is
                    # handed the headers of each request it sees, refresh token included.
                    # The httpx client that drives this flow always sets a timeout.
                    extensions={"timeout": request.extensions["timeout"]},
                )
                refreshed = await self._send_refresh(refresh_request)
                if refreshed.request is not refresh_request or refreshed.is_redirect:
                    # A redirect means Watcher did not refresh the sign-in at this address, and
                    # following it could hand the token to another server. _send_refresh
                    # never follows one, so the answer always belongs to refresh_request.
                    # The identity check stays as a second safeguard: if a redirect were
                    # ever followed, whatever answered may not be Watcher, and saving its
                    # tokens would sign this user in as someone else.
                    raise WatcherAuthenticationError(
                        502,
                        "watcher_refresh_redirected",
                        f"{self._login_instruction} again: Watcher redirected the sign-in refresh",
                    )
                latest = self._read_login()
                if latest.refresh_token != current.refresh_token:
                    current = latest
                elif refreshed.status_code == 401:
                    self.credential_file.unlink()
                    raise WatcherAuthenticationError(401, "watcher_login_expired", f"{self._login_instruction} again")
                else:
                    try:
                        refresh_token = refreshed.cookies.get(REFRESH_TOKEN_COOKIE_NAME)
                        if refreshed.status_code != 200 and not (refreshed.status_code == 503 and refresh_token):
                            raise WatcherAPIError(
                                refreshed.status_code, "watcher_refresh_failed", "Watcher sign-in refresh failed"
                            )
                        if not refresh_token:
                            raise ValueError("Invalid refreshed credentials")
                        access_token = current.access_token
                        if refreshed.status_code == 200:
                            access_token = _RefreshedToken.model_validate_json(refreshed.content).access_token
                        # A 503 may carry a rotated refresh cookie when access-token verification is unavailable.
                        current = _Login.model_validate(
                            {
                                **current.model_dump(),
                                "access_token": access_token,
                                "refresh_token": refresh_token,
                                "updated_at": datetime.now(UTC).isoformat(),
                            }
                        )
                    except (ValidationError, ValueError, httpx.CookieConflict):
                        raise WatcherAuthenticationError(
                            502, "watcher_refresh_invalid", "Watcher did not return valid refreshed credentials"
                        ) from None
                    self._save_login(current)
                    if refreshed.status_code != 200:
                        raise WatcherAPIError(
                            refreshed.status_code, "watcher_refresh_failed", "Watcher sign-in refresh failed"
                        )
            self._apply_login(request, current)
        yield request


def login_transport(auth: WatcherLoginAuth, *, timeout: float) -> httpx.AsyncClient:
    """An HTTP client for saved sign-in auth that never stores cookies.

    Watcher's sign-in and refresh routes answer with the refresh token as a cookie.
    A caller that sends one of them through this client would otherwise leave that
    long-lived secret in the client's jar, which sends it with every later request.
    The auth flow's own refresh never goes through this client.
    """
    return httpx.AsyncClient(
        base_url=str(auth.base_url),
        auth=auth,
        timeout=timeout,
        follow_redirects=False,
        cookies=_cookie_jar_refusing_all(),
    )


def async_client_from_watcher(
    base_url: str,
    *,
    state_dir: Path | None = None,
    timeout: float = 30,
    max_retries: int = 0,
) -> AsyncWatcherClient:
    """Create an SDK client using the installed Watcher's sign-in and token refresh.

    Use with ``async with`` to close its HTTP connections. Reads credentials only
    when requesting or explicitly validating them, and never starts a sign-in flow.
    The installed Watcher app can be frozen; its Python modules are not needed.
    """
    auth = WatcherLoginAuth(base_url, state_dir=state_dir)
    transport = login_transport(auth, timeout=timeout)
    return AsyncWatcherClient(
        base_url=str(auth.base_url), timeout=timeout, max_retries=max_retries, httpx_client=transport
    )
