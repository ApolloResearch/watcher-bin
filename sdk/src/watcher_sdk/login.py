"""Complete interactive device login and own its credentials independently of Watcher Live."""

import asyncio
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import BaseModel

from watcher_sdk.client import AsyncWatcherClient
from watcher_sdk.errors import WatcherAPIError, WatcherAuthenticationError, WatcherConnectionError
from watcher_sdk.integration_auth import IntegrationAuth, SDKLoginAuth
from watcher_sdk.local_auth import _Login, _login_api_url, _make_private_folder, login_transport

# A genuine approval link is a short URL without a #fragment, and its code is a
# short word such as ABCD-EFGH. A hostile server can relay a genuine link but pad
# it with a long fragment, which the browser never sends to the real page, or
# send a huge code. Either can scroll the terminal line naming the server out of
# view, so anything beyond these bounds is refused as invalid server data.
_MAX_LOGIN_URL_LENGTH = 2048
_MAX_USER_CODE_LENGTH = 32


class DeviceLoginPrompt(BaseModel):
    """Public device approval instructions; never includes the secret polling code."""

    url: str
    user_code: str


async def login(
    base_url: str,
    on_authorization: Callable[[DeviceLoginPrompt], None],
    *,
    state_dir: Path | None = None,
) -> IntegrationAuth:
    """Sign in through WorkOS and atomically save an SDK-owned login.

    Explicit interactive setup calls this function and presents the supplied URL
    and user code. Hook processes must only use the returned credential reference.
    An existing login is preserved on cancellation, timeout or server failure.
    This never writes Watcher's own credential store. An omitted ``state_dir``
    uses WATCHER_SDK_HOME, then XDG_CONFIG_HOME/watcher-sdk, then ~/.config/watcher-sdk.
    Unsupported SSO and rejected authentication raise WatcherAuthenticationError;
    polling rejection raises WatcherAPIError, expiry raises TimeoutError, invalid
    server data raises ValueError, and filesystem failures raise OSError. Invalid
    server data includes an approval link that is not HTTPS, has no host, has a
    user name or password, has a #fragment or is longer than 2048 characters, and
    an approval code that is empty or longer than 32 characters. The credential
    folder and any missing parents are created with mode 0700, and an existing
    credential folder is set to 0700; one owned by another account raises
    UnsafeLoginStoreError, a PermissionError, and one that is a symbolic link or a
    file raises OSError, both before any login is saved. A link, even one whose
    target is missing, raises LinkedCredentialFolderError, an OSError saying that
    the credential folder must not be a symbolic link. Requests and discovery
    still read a login saved in a linked folder; only ``login`` refuses it.
    """
    url = str(_login_api_url(base_url))
    async with AsyncWatcherClient(url, timeout=30, max_retries=0) as client:
        configuration = await client.auth_client_config()
        if configuration.auth_mode != "workos" or not configuration.workos_client_id:
            raise WatcherAuthenticationError(
                400, "device_login_unavailable", "This installer requires WorkOS SSO or an explicit API key"
            )
        grant = await client.auth_device_authorize()
        destination = httpx.URL(grant.verification_uri_complete)
        if (
            destination.scheme != "https"
            or not destination.host
            or destination.userinfo
            or "#" in grant.verification_uri_complete
            or len(str(destination)) > _MAX_LOGIN_URL_LENGTH
        ):
            raise ValueError("The server returned an invalid login URL")
        if not 1 <= len(grant.user_code) <= _MAX_USER_CODE_LENGTH:
            raise ValueError("The server returned an invalid approval code")
        if grant.interval < 1 or not 1 <= grant.expires_in <= 3600:
            raise ValueError("The server returned an invalid login deadline")
        on_authorization(DeviceLoginPrompt(url=str(destination), user_code=grant.user_code))
        interval = grant.interval
        async with asyncio.timeout(grant.expires_in):
            while True:
                await asyncio.sleep(interval)
                try:
                    tokens = await client.auth_device_token(grant.device_code)
                    break
                except WatcherAPIError as error:
                    if error.code == "slow_down":
                        interval += 5
                    elif error.code != "authorization_pending":
                        raise
    async with AsyncWatcherClient(url, access_token=tokens.access_token, timeout=10, max_retries=0) as authenticated:
        await authenticated.auth_me()
    auth = SDKLoginAuth(url, state_dir=state_dir)
    _make_private_folder(auth.credential_file.parent)
    saved = _Login(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        xylon_url=url,
        updated_at=datetime.now(UTC).isoformat(),
    )
    async with auth._refresh_lock():
        auth._save_login(saved)
    return IntegrationAuth(base_url=url, kind="sdk_login", state_dir=auth.credential_file.parent.parent)


async def logout(base_url: str, *, state_dir: Path | None = None) -> bool:
    """Revoke the SDK-owned login's server session, then remove the local login.

    Returns True when a credential was present, False when already absent.
    Revocation is best-effort: when the server cannot be reached, rejects the
    login or fails, the local login is still removed and the server session
    expires on its own. Watcher Live's saved credentials are never touched, but
    the server ends the whole sign-in session behind the SDK login, so the browser
    that approved it, and a Watcher Live login made through that browser, may be
    signed out too. An omitted ``state_dir`` uses the same defaults as ``login``. Existing
    integration references remain installed and will report that login is needed.
    """
    auth = SDKLoginAuth(base_url, state_dir=state_dir)
    if not auth.credential_file.exists():
        return False
    # Revoke before taking the refresh lock: a refresh during revocation takes
    # the same lock, and the lock is not reentrant.
    await _revoke_session(auth)
    async with auth._refresh_lock():
        auth.credential_file.unlink(missing_ok=True)
    return True


async def _revoke_session(auth: SDKLoginAuth) -> None:
    """Ask the server to end the saved login's session, ignoring any failure.

    The server finds the session to end from the access token, and skips
    revocation when that token has expired, which a login saved hours ago
    usually has. Reading the profile first gives the auth flow a 401 to
    answer with a refresh, so the logout request carries a current token.
    A rejected refresh deletes the login itself; logout then has nothing left to remove.
    The logout request is sent even when the profile read fails, because the
    profile needs the server's database and revocation does not: during a
    database outage, or while a slow database makes the profile time out, a
    still-valid access token can end its session anyway. A refresh that gave up
    waiting for the credential lock also still sends it. The request is skipped
    only when the profile read never connected, through a refused connection, a
    failed name lookup or a connect timeout, since it would then only wait through
    the same failure before the local login is removed. It keeps its own
    10-second limit.
    """
    # Revocation is a courtesy to the server. Whatever goes wrong with it, a
    # refused login, an unreachable server, a malformed answer or a fault in this
    # request path, must not stop logout from removing the local login.
    # Cancellation is not an Exception, so it still propagates.
    with suppress(Exception):
        async with AsyncWatcherClient(
            str(auth.base_url), httpx_client=login_transport(auth, timeout=10), timeout=10, max_retries=0
        ) as client:
            try:
                await client.auth_me()
            except Exception as error:
                # The SDK reports a connect timeout as a WatcherTimeoutError, the same
                # error as a slow answer, so only httpx's original error tells them apart.
                if isinstance(error, WatcherConnectionError) or isinstance(error.__cause__, httpx.ConnectTimeout):
                    return
            await client.auth_logout()
