"""Choose and verify persistent authentication for installed local SDK integrations."""

import hashlib
import os
import re
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, ValidationInfo, model_validator

from watcher_sdk.client import AsyncWatcherClient
from watcher_sdk.errors import WatcherAPIError, WatcherAuthenticationError
from watcher_sdk.local_auth import (
    WatcherLoginAuth,
    _api_url,
    _login_api_url,
    _read_login_file,
    login_transport,
    watcher_login_superseded,
)

CLOUD_URL = "https://app.apolloresearch.ai/api"
# Validation context key for a reader that only reports, replaces or deletes a
# saved reference. Set to true, it lets ``IntegrationAuth`` read a login whose URL
# is plain HTTP to another machine instead of refusing it (see ``IntegrationAuth``).
ALLOW_INSECURE_LOGIN_URL = "allow_insecure_login_url"


def sdk_state_directory() -> Path:
    """Resolve WATCHER_SDK_HOME, then XDG_CONFIG_HOME/watcher-sdk, then ~/.config/watcher-sdk."""
    root = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "watcher-sdk"
    return Path(os.environ.get("WATCHER_SDK_HOME") or root).expanduser().resolve()


def watcher_state_directory() -> Path:
    return Path(os.environ.get("APOLLO_MONITOR_HOME") or Path.home() / ".apollo_monitor").expanduser().resolve()


class SDKLoginAuth(WatcherLoginAuth):
    """Refresh an SDK-owned login using the same protocol as Watcher's saved login.

    Credentials are keyed by the full API URL under the supplied private SDK
    state directory. This store is independent of the local Watcher application.
    Reads, refresh, login and logout coordinate through the credential's lock.
    Without ``state_dir``, ``sdk_state_directory()`` selects the store.
    ``transport`` routes token refreshes as it does for WatcherLoginAuth.

    The credential file and its folder must belong to the current user and be
    writable by no one else. ``login`` creates them that way, and every read
    refuses anything else with WatcherAuthenticationError, because another
    account that can write them could swap in its own login.
    """

    _login_instruction = "Call watcher_sdk.login()"
    _private_store = True

    def __init__(
        self, base_url: str, *, state_dir: Path | None = None, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        root = state_dir if state_dir is not None else sdk_state_directory()
        super().__init__(base_url, state_dir=root, transport=transport)
        key = hashlib.sha256(str(self.base_url).encode()).hexdigest()
        self.credential_file = root.expanduser().resolve() / "credentials" / f"{key}.json"

    def _superseded(self) -> bool:
        """The SDK's own store has no Watcher header or helper configuration."""
        return False


class IntegrationAuth(BaseModel):
    """A secret-free, destination-pinned credential reference saved by setup.

    Call ``profile.create_client()`` on each hook invocation. Only explicit
    setup discovers or changes identities; the request path never falls back.
    State directories and API-key paths are resolved when the model is created.

    Login kinds accept only ``state_dir``; omitted directories use the selected
    store's defaults. ``api_key_file`` requires only ``key_file`` and
    ``api_key_env`` requires only ``key_env``. Other source fields must be absent.
    Invalid combinations raise ValueError. Missing or invalid referenced credentials
    raise WatcherAuthenticationError when validated or used.

    A login URL that is plain HTTP to another machine raises InsecureLoginURLError,
    a ValueError, unless the validation context sets ``ALLOW_INSECURE_LOGIN_URL``.
    Such a profile can still be reported, replaced or deleted, but never signs in
    or sends anything: ``login_auth``, ``validate_local`` and ``create_client``
    raise InsecureLoginURLError for it.
    """

    model_config = ConfigDict(extra="forbid")

    base_url: str
    kind: Literal["sdk_login", "watcher_login", "api_key_file", "api_key_env"]
    state_dir: Path | None = None
    key_file: Path | None = None
    key_env: str | None = None

    @model_validator(mode="after")
    def validate_source(self, info: ValidationInfo) -> "IntegrationAuth":
        if self.kind in {"sdk_login", "watcher_login"} and not (info.context or {}).get(ALLOW_INSECURE_LOGIN_URL):
            self.base_url = str(_login_api_url(self.base_url))
        else:
            self.base_url = str(_api_url(self.base_url))
        if self.kind in {"sdk_login", "watcher_login"}:
            if self.key_file is not None or self.key_env is not None:
                raise ValueError("Choose one credential source")
            if self.state_dir is None:
                self.state_dir = sdk_state_directory() if self.kind == "sdk_login" else watcher_state_directory()
            self.state_dir = self.state_dir.expanduser().resolve()
        else:
            if self.state_dir is not None:
                raise ValueError("API keys do not use a login store")
            if self.kind == "api_key_file":
                if self.key_file is None or self.key_env is not None:
                    raise ValueError("An API-key file is required")
                self.key_file = self.key_file.expanduser().resolve()
            elif (
                self.key_file is not None
                or self.key_env is None
                or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.key_env) is None
            ):
                raise ValueError("An API-key environment variable name is required")
        return self

    def login_auth(self) -> WatcherLoginAuth:
        """Return this saved-login transport; API-key profiles must use ``create_client``."""
        if self.kind == "sdk_login":
            return SDKLoginAuth(self.base_url, state_dir=self.state_dir)
        if self.kind == "watcher_login":
            return WatcherLoginAuth(self.base_url, state_dir=self.state_dir)
        raise ValueError("This credential source is not a saved login")

    def validate_local(self) -> None:
        """Check local availability without networking; invalid credentials raise WatcherAuthenticationError."""
        if self.kind in {"sdk_login", "watcher_login"}:
            self.login_auth().validate()
        else:
            self.read_api_key()

    def read_api_key(self) -> str:
        """Read the referenced key without storing its value in configuration or errors."""
        try:
            if self.kind == "api_key_file":
                assert self.key_file is not None
                with self.key_file.open(encoding="utf-8") as source:
                    value = source.read(8193).strip()
            elif self.kind == "api_key_env":
                assert self.key_env is not None
                value = os.environ[self.key_env].strip()
            else:
                raise ValueError("This credential source is not an API key")
            if not value or len(value) > 8192 or any(not 33 <= ord(char) <= 126 for char in value):
                raise ValueError("Invalid API key")
            return value
        except (OSError, KeyError, ValueError):
            raise WatcherAuthenticationError(
                401, "api_key_unavailable", "Check the configured API-key source"
            ) from None

    def create_client(self, *, timeout: float = 10) -> AsyncWatcherClient:
        """Create an async context-managed client; it never prompts or changes the source."""
        if self.kind in {"api_key_file", "api_key_env"}:
            return AsyncWatcherClient(self.base_url, api_key=self.read_api_key(), timeout=timeout, max_retries=0)
        transport = login_transport(self.login_auth(), timeout=timeout)
        return AsyncWatcherClient(self.base_url, httpx_client=transport, timeout=timeout, max_retries=0)


class SavedLoginDestination(BaseModel):
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)
    xylon_url: str


def discover_logins(
    base_url: str | None = None,
    *,
    state_dir: Path | None = None,
    watcher_state_dir: Path | None = None,
) -> list[IntegrationAuth]:
    """List saved login references for explicit setup, without networking or refreshing.

    The caller selects among multiple results. Without ``base_url``, unreadable or
    invalid logins are skipped so healthy stores remain discoverable. With
    ``base_url``, invalid matching credentials fail visibly rather than enabling
    an identity fallback. Watcher header/helper auth
    is outside this API's scope and is never treated as a saved WorkOS login.
    SDK discovery defaults to ``sdk_state_directory()``; Watcher discovery uses
    APOLLO_MONITOR_HOME or ~/.apollo_monitor. Matching unreadable or invalid
    credentials raise WatcherAuthenticationError; absent stores return no entries.
    """
    candidates: list[IntegrationAuth] = []
    roots: dict[Literal["sdk_login", "watcher_login"], Path] = {
        "sdk_login": state_dir if state_dir is not None else sdk_state_directory(),
        "watcher_login": watcher_state_dir if watcher_state_dir is not None else watcher_state_directory(),
    }
    for kind, root in roots.items():
        if base_url is not None:
            profile = IntegrationAuth(base_url=base_url, kind=kind, state_dir=root)
            files = [profile.login_auth().credential_file]
        else:
            files = sorted((root / "credentials").glob("*.json"))
        for path in files:
            try:
                destination = SavedLoginDestination.model_validate_json(_read_login_file(path))
                if base_url is not None and _api_url(destination.xylon_url) != _api_url(base_url):
                    continue
                profile = IntegrationAuth(base_url=base_url or destination.xylon_url, kind=kind, state_dir=root)
                if kind == "watcher_login" and watcher_login_superseded(root, profile.base_url):
                    continue
                profile.validate_local()
                if profile not in candidates:
                    candidates.append(profile)
            except FileNotFoundError:
                continue
            except (OSError, ValueError, httpx.InvalidURL, WatcherAuthenticationError):
                if base_url is not None:
                    raise WatcherAuthenticationError(
                        401, "invalid_saved_login", "A saved login cannot be read; select or repair its store"
                    ) from None
    return candidates


async def verify_integration_auth(profile: IntegrationAuth) -> None:
    """Check ingestion and session read access without uploading a synthetic session.

    User logins read their own sessions and need no broad read permission. Service
    API keys require ``sessions:read:any``. Success proves access, not delivery.
    Missing credentials or permissions raise WatcherAuthenticationError; other
    server failures, including a 2xx response whose body does not have the expected
    shape (empty, ``null``, or a proxy's login page), raise WatcherAPIError.
    Connection failures raise WatcherConnectionError or WatcherTimeoutError.
    """
    async with profile.create_client() as client:
        permissions = ["sessions:ingest"]
        try:
            if profile.kind in {"api_key_file", "api_key_env"}:
                permissions.append("sessions:read:any")
            else:
                await client.auth_me()
            granted = (await client.check_permissions(permissions)).granted
            if granted:
                await client.search_sessions(external_ids={"other": ["sdk-setup:" + str(uuid4())]}, limit=1)
        except (TypeError, AttributeError, KeyError) as error:
            # Generated response parsing fails this way on a malformed body; callers
            # then see a server failure instead of an apparent programming error.
            raise WatcherAPIError(502, "malformed_response", "Watcher returned an unexpected response") from error
        if not granted:
            raise WatcherAuthenticationError(
                403, "integration_permissions_missing", "The credential lacks ingestion or session read access"
            )
