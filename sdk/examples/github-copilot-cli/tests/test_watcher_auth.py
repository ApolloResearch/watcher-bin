"""Check optional Watcher Live authentication without using the developer's sign-in."""

import asyncio
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import IO, Literal

import httpx
import pytest
from readback_fixture import save_watcher_login
from typer.testing import CliRunner
from watcher_github_copilot_cli.cli import app
from watcher_github_copilot_cli.configuration import HOOK_FILE, configuration_path, install_observer, load_configuration
from watcher_github_copilot_cli.integration import watcher_settings

from watcher_sdk import IntegrationAuth, WatcherAuthenticationError, WatcherLoginAuth, async_client_from_watcher

URL = "http://localhost:8765/api"


@pytest.fixture
def login(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("APOLLO_MONITOR_HOME", str(tmp_path))
    monkeypatch.setenv("XYLON_URL", URL)
    monkeypatch.delenv("XYLON_API_KEY", raising=False)
    monkeypatch.delenv("WATCHER_API_KEY", raising=False)
    path = tmp_path / "credentials/local.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"access_token": "old", "refresh_token": "refresh", "xylon_url": URL}))
    return path


def test_installs_login_hooks_without_copying_tokens(login: Path, tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    arguments = [
        "setup",
        "--project",
        str(project),
        "--watcher-url",
        URL,
        "--config-dir",
        str(tmp_path / "config"),
        "--watcher-auth",
        "--enforce",
    ]
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 0, result.output
    config = configuration_path(project, tmp_path / "config")
    settings = load_configuration(config)
    assert settings.watcher_auth and settings.api_key_file is None and settings.api_key_env is None
    assert settings.gate is not None
    assert set(json.loads((project / HOOK_FILE).read_text())["hooks"]) == {"agentStop", "sessionEnd", "preToolUse"}
    assert "refresh_token" not in config.read_text() + (project / HOOK_FILE).read_text()
    assert CliRunner().invoke(app, arguments).exit_code == 0
    assert CliRunner().invoke(app, [*arguments, "--api-key-file", str(login)]).exit_code == 2


@pytest.mark.parametrize("saved_url", ["http://localhost:9876/api", "https://watcher.example.com/api", None])
def test_refuses_login_for_another_server(login: Path, saved_url: str | None) -> None:
    login.write_text(json.dumps({"access_token": "old", "xylon_url": saved_url}))
    with pytest.raises(WatcherAuthenticationError, match="exact API URL"):
        WatcherLoginAuth(URL).validate()


def test_missing_login_does_not_fall_back_to_environment_key(login: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    login.unlink()
    monkeypatch.setenv("WATCHER_API_KEY", "different-identity")
    with pytest.raises(WatcherAuthenticationError, match="Sign in"):
        WatcherLoginAuth(URL).validate()


def test_new_hooks_pin_watchers_store(login: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    config = install_observer(project, URL, tmp_path / "config", watcher_auth=True)
    monkeypatch.setenv("APOLLO_MONITOR_HOME", str(tmp_path / "other-store"))
    settings = watcher_settings(config)
    assert settings.watcher_state_dir == login.parent.parent
    WatcherLoginAuth(URL, state_dir=settings.watcher_state_dir).validate()


def test_sdk_profile_is_saved_without_tokens(login: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    profile = IntegrationAuth(base_url=URL, kind="watcher_login", state_dir=login.parent.parent)
    config = install_observer(project, URL, tmp_path / "config", auth_profile=profile)
    settings = watcher_settings(config)
    assert settings.auth_profile == profile
    assert "access_token" not in config.read_text()

    async def handle(transport: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        assert str(request.url) == URL + "/v1/auth/me"
        assert request.headers["authorization"] == "Bearer old"
        return httpx.Response(200, json={"user_id": "user_1"})

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)

    async def verify() -> None:
        async with settings.create_client() as client:
            assert (await client.auth_me()).user_id == "user_1"

    asyncio.run(verify())


@pytest.mark.parametrize("kind", ["api_key_file", "api_key_env"])
def test_setup_refuses_api_key_profiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: Literal["api_key_file", "api_key_env"]
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    key = tmp_path / "key"
    key.write_text("PRIVATE_KEY")
    monkeypatch.setenv("COPILOT_TEST_KEY", "PRIVATE_KEY")
    profile = IntegrationAuth(
        base_url=URL,
        kind=kind,
        key_file=key if kind == "api_key_file" else None,
        key_env="COPILOT_TEST_KEY" if kind == "api_key_env" else None,
    )
    with pytest.raises(ValueError, match="run setup again with a sign-in"):
        install_observer(project, URL, tmp_path / "config", auth_profile=profile)
    assert not (project / HOOK_FILE).exists()


@pytest.mark.parametrize("source", ["legacy", "sdk_login", "watcher_login"])
@pytest.mark.parametrize(
    "layout",
    ["direct", "state_symlink", "credential_symlink", "file_symlink", "parent_symlink_file_external", "default"],
)
def test_setup_rejects_project_contained_login_stores_without_replacing_hooks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: Literal["legacy", "sdk_login", "watcher_login"],
    layout: str,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    initial = tmp_path / "initial-login"
    save_watcher_login(initial, URL)
    config_dir = tmp_path / "configuration"
    config = install_observer(project, URL, config_dir, watcher_auth=True, watcher_state_dir=initial)
    previous_config = config.read_bytes()
    previous_hook = (project / HOOK_FILE).read_bytes()
    state = project / "login"
    state.mkdir()
    if layout == "state_symlink":
        alias = tmp_path / "state-link"
        alias.symlink_to(state, target_is_directory=True)
        state = alias
    elif layout in {"credential_symlink", "parent_symlink_file_external"}:
        (state / "credentials").mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "credentials").symlink_to(state / "credentials", target_is_directory=True)
        state = outside
    monkeypatch.setenv("WATCHER_SDK_HOME", str(state))
    monkeypatch.setenv("APOLLO_MONITOR_HOME", str(state))
    selected_state = None if layout == "default" else state
    profile = IntegrationAuth(
        base_url=URL, kind="sdk_login" if source == "sdk_login" else "watcher_login", state_dir=selected_state
    )
    credential = profile.login_auth().credential_file
    if layout == "parent_symlink_file_external":
        credential.symlink_to(tmp_path / "outside-credential.json")
    if layout == "file_symlink":
        real_credential = credential
        outside_profile = IntegrationAuth(base_url=URL, kind=profile.kind, state_dir=tmp_path / "outside")
        credential = outside_profile.login_auth().credential_file
        credential.parent.mkdir(parents=True)
        real_credential.parent.mkdir(parents=True)
        credential.symlink_to(real_credential)
        selected_state = outside_profile.state_dir
        profile = outside_profile
    credential.parent.mkdir(parents=True, exist_ok=True)
    credential.write_text(
        json.dumps({"access_token": "PRIVATE_ACCESS", "refresh_token": "PRIVATE_REFRESH", "xylon_url": URL})
    )
    with pytest.raises(ValueError, match="outside the project"):
        install_observer(
            project,
            URL,
            config_dir,
            watcher_auth=source == "legacy",
            watcher_state_dir=selected_state if source == "legacy" else None,
            auth_profile=None if source == "legacy" else profile,
        )
    assert config.read_bytes() == previous_config
    assert (project / HOOK_FILE).read_bytes() == previous_hook


@pytest.mark.parametrize(("size", "exit_code"), [(65536, 0), (65537, 1)])
@pytest.mark.parametrize("unicode_path", [False, True])
def test_setup_bounds_the_auth_profile_file(
    login: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, size: int, exit_code: int, unicode_path: bool
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    config_dir = tmp_path / "config"
    config = install_observer(project, URL, config_dir, watcher_auth=True, watcher_state_dir=login.parent.parent)
    previous_config = config.read_bytes()
    previous_hook = (project / HOOK_FILE).read_bytes()
    state_dir = login.parent.parent
    if unicode_path:
        state_dir = state_dir / "é"
        (state_dir / "credentials").mkdir(parents=True)
        (state_dir / "credentials/local.json").write_bytes(login.read_bytes())
    profile = IntegrationAuth(base_url=URL, kind="watcher_login", state_dir=state_dir)
    serialized = profile.model_dump_json()
    document = " " * (size - len(serialized.encode())) + serialized
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(document)
    reads: list[int | None] = []
    original_open = Path.open

    class ProfileReader(io.StringIO):
        def read(self, size: int | None = -1, /) -> str:
            reads.append(size)
            return super().read(size)

    class BinaryProfileReader(io.BytesIO):
        def read(self, size: int | None = -1, /) -> bytes:
            reads.append(size)
            return super().read(size)

    def open_profile(
        path: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> IO[str] | IO[bytes]:
        if path == profile_path:
            return BinaryProfileReader(document.encode()) if "b" in mode else ProfileReader(document)
        return original_open(path, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, "open", open_profile)
    result = CliRunner().invoke(
        app,
        [
            "setup",
            "--project",
            str(project),
            "--watcher-url",
            URL,
            "--config-dir",
            str(tmp_path / "config"),
            "--auth-profile",
            str(profile_path),
        ],
    )
    assert result.exit_code == exit_code, result.output
    assert all(size is not None and 0 < size <= 65537 for size in reads)
    if exit_code:
        assert config.read_bytes() == previous_config
        assert (project / HOOK_FILE).read_bytes() == previous_hook
    else:
        assert reads
        assert load_configuration(config).auth_profile == profile


def test_setup_rejects_a_fifo_auth_profile_without_waiting(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    profile = tmp_path / "profile.fifo"
    os.mkfifo(profile)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "watcher_github_copilot_cli.cli",
            "setup",
            "--project",
            str(project),
            "--watcher-url",
            URL,
            "--config-dir",
            str(tmp_path / "config"),
            "--auth-profile",
            str(profile),
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 1
    assert "Setup failed" in result.stderr
    assert not (project / HOOK_FILE).exists()


def test_setup_missing_sdk_login_gives_sdk_recovery_instructions(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    profile = IntegrationAuth(base_url=URL, kind="sdk_login", state_dir=tmp_path / "sdk-store")
    path = tmp_path / "profile.json"
    path.write_text(profile.model_dump_json())
    result = CliRunner().invoke(
        app,
        [
            "setup",
            "--project",
            str(project),
            "--watcher-url",
            URL,
            "--config-dir",
            str(tmp_path / "config"),
            "--auth-profile",
            str(path),
        ],
    )
    assert result.exit_code == 1
    assert "watcher_sdk.login()" in result.stderr
    assert not (project / HOOK_FILE).exists()


def test_saved_login_coexists_with_captured_routing_headers(login: Path) -> None:
    headers = login.parent.parent / "hook_headers/local.json"
    headers.parent.mkdir()
    headers.write_text(json.dumps({"X-Forwarded-User": "developer"}))
    WatcherLoginAuth(URL).validate()


def test_saved_login_is_not_reused_when_watcher_sends_captured_auth(login: Path) -> None:
    headers = login.parent.parent / "hook_headers/local.json"
    headers.parent.mkdir()
    headers.write_text(json.dumps({"Authorization": "Bearer different-identity"}))
    with pytest.raises(WatcherAuthenticationError, match="hook headers or a credential helper"):
        WatcherLoginAuth(URL).validate()


def test_refreshes_and_retries_with_watchers_shared_credentials(login: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[str] = []

    async def handle(transport: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(URL + "/")
        if request.url.path.endswith("/auth/refresh"):
            assert json.loads(await request.aread()) == {}
            assert request.headers["Cookie"] == "refresh_token=refresh"
            return httpx.Response(
                200, json={"access_token": "new"}, headers={"Set-Cookie": "refresh_token=rotated; Path=/"}
            )
        received.append(request.headers["Authorization"])
        assert "x-api-key" not in request.headers
        if received[-1] == "Bearer old":
            return httpx.Response(401, json={"detail": "Expired"})
        return httpx.Response(200, json={"sessions": [], "total": 0, "limit": 2, "offset": 0})

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)

    async def run() -> None:
        async with async_client_from_watcher(URL) as client:
            result = await client.search_sessions(external_ids={"other": ["copilot-auth-test"]}, limit=2)
            assert result.total == 0

    asyncio.run(run())
    assert received == ["Bearer old", "Bearer new"]
    assert json.loads(login.read_text())["refresh_token"] == "rotated"
