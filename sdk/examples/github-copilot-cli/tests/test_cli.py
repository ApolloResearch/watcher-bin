"""Exercise the installed hook command's control output and safe usage errors."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest
from pydantic import JsonValue
from readback_fixture import login_configuration
from typer.testing import CliRunner
from watcher_github_copilot_cli import cli, integration
from watcher_github_copilot_cli.configuration import ObserverConfiguration
from watcher_github_copilot_cli.recording import RecordedSession

from watcher_sdk import AsyncWatcherClient, WatcherAuthenticationError, WatcherConnectionError


@pytest.mark.parametrize("arguments", [[], ["--help"], ["help"]])
def test_help_never_consumes_a_hook(arguments: list[str]) -> None:
    result = CliRunner().invoke(integration.app, arguments)
    assert result.exit_code == 0
    assert "observe" in result.stdout and "enforce" in result.stdout
    assert "permissionDecision" not in result.stdout


def test_unknown_command_has_a_nonzero_exit():
    result = CliRunner().invoke(integration.app, ["unknown"])
    assert result.exit_code != 0


def test_invalid_input_denies_without_echoing_content():
    result = CliRunner().invoke(integration.app, ["enforce"], input="PRIVATE invalid JSON")
    assert result.exit_code == 0
    assert json.loads(result.stdout)["permissionDecision"] == "deny"
    assert "PRIVATE" not in result.stdout + result.stderr


def test_observer_failure_warns_without_blocking_or_leaking_content():
    result = CliRunner().invoke(integration.app, ["observe"], input="PRIVATE invalid JSON")
    assert result.exit_code == 2 and result.stdout == "{}\n"
    assert "did not confirm" in result.stderr and "PRIVATE" not in result.stderr


def test_confirmed_allow_skips_native_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[dict[str, JsonValue]] = []

    async def accept(
        mode: str, payload: Mapping[str, JsonValue], config: Path | None, *, grade: bool, watcher_url: str | None = None
    ) -> str:
        received.append({"mode": mode, "payload": dict(payload)})
        return "allow"

    monkeypatch.setattr(integration, "run_hook", accept)
    result = CliRunner().invoke(integration.app, ["enforce"], input='{"toolName":"bash"}')
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "permissionDecision": "allow",
        "permissionDecisionReason": "Watcher approved this call",
    }
    assert received == [{"mode": "enforce", "payload": {"toolName": "bash"}}]


def test_deferral_preserves_native_permissions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def defer(
        mode: str, payload: Mapping[str, JsonValue], config: Path | None, *, grade: bool, watcher_url: str | None = None
    ) -> str:
        return "deferred"

    monkeypatch.setattr(integration, "run_hook", defer)
    config = tmp_path / "config.json"
    result = CliRunner().invoke(integration.app, ["enforce", "--config", str(config)], input='{"toolName":"bash"}')
    assert result.exit_code == 0 and result.stdout == "{}\n"
    kinds = [json.loads(line)["kind"] for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert kinds == ["started", "deferred"]


@pytest.mark.parametrize(
    ("named", "configured", "decision"),
    [
        ("https://watcher.test/api/", "https://watcher.test/api", "allow"),
        ("http://127.0.0.1:9/api", "https://watcher.test/api", "deny"),
        ("https://watcher.test/api", None, "deny"),
    ],
)
def test_the_gate_checks_the_server_its_command_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, named: str, configured: str | None, decision: str
) -> None:
    async def approve(
        client: AsyncWatcherClient,
        payload: Mapping[str, JsonValue],
        *,
        hook_timeout: int | None = None,
        config: Path | None = None,
    ) -> Literal["allow"]:
        return "allow"

    monkeypatch.setattr(integration, "apply_policy", approve)
    config = tmp_path / "config" / "config.json"
    if configured is not None:
        login_configuration(config, tmp_path, configured)
    result = CliRunner().invoke(
        integration.app, ["enforce", "--config", str(config), "--watcher-url", named], input='{"toolName":"bash"}'
    )
    answer = json.loads(result.stdout)
    assert answer["permissionDecision"] == decision
    if configured is not None and decision == "deny":
        assert "different Watcher servers" in answer["permissionDecisionReason"]


def test_the_gate_uses_the_configuration_it_checked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    server = "https://watcher.test/api"
    config = login_configuration(tmp_path / "config" / "config.json", tmp_path, server)
    # Another process of this user rewrites the file right after each read, into a
    # configuration that is consistent on its own but names a stub on this machine.
    redirected = config.read_text().replace(server, "http://127.0.0.1:9/api")
    load = integration.load_configuration

    def load_then_redirect(path: Path) -> ObserverConfiguration:
        loaded = load(path)
        path.write_text(redirected)
        return loaded

    destinations: list[str] = []
    client_for = integration.async_client_from_watcher

    def record_destination(
        base_url: str, *, state_dir: Path | None = None, timeout: float = 30, max_retries: int = 0
    ) -> AsyncWatcherClient:
        destinations.append(base_url)
        return client_for(base_url, state_dir=state_dir, timeout=timeout, max_retries=max_retries)

    async def approve(
        client: AsyncWatcherClient,
        payload: Mapping[str, JsonValue],
        *,
        hook_timeout: int | None = None,
        config: Path | None = None,
    ) -> Literal["allow"]:
        return "allow"

    monkeypatch.setattr(integration, "load_configuration", load_then_redirect)
    monkeypatch.setattr(integration, "async_client_from_watcher", record_destination)
    monkeypatch.setattr(integration, "apply_policy", approve)
    result = CliRunner().invoke(
        integration.app, ["enforce", "--config", str(config), "--watcher-url", server], input='{"toolName":"bash"}'
    )
    assert json.loads(result.stdout)["permissionDecision"] == "allow"
    assert destinations == [server]


@pytest.mark.parametrize(
    "error,reason",
    [
        (integration.PolicyDenial("PRIVATE"), "Watcher withheld this tool call"),
        (PermissionError("PRIVATE"), "Watcher could not evaluate this tool call, so it was withheld"),
        (
            WatcherAuthenticationError(401, "PRIVATE"),
            "Watcher rejected the credential. Sign in again before retrying this tool call",
        ),
        (WatcherConnectionError("PRIVATE"), "Watcher could not be reached in time, so the tool call was withheld"),
        (TimeoutError(), "Watcher could not be reached in time, so the tool call was withheld"),
        (ValueError("PRIVATE"), "Watcher could not evaluate this tool call, so it was withheld"),
    ],
)
def test_denials_explain_their_category_without_service_text(
    monkeypatch: pytest.MonkeyPatch, error: Exception, reason: str
) -> None:
    async def fail(
        mode: str, payload: Mapping[str, JsonValue], config: Path | None, *, grade: bool, watcher_url: str | None = None
    ) -> None:
        raise error

    monkeypatch.setattr(integration, "run_hook", fail)
    result = CliRunner().invoke(integration.app, ["enforce"], input='{"toolName":"bash"}')
    assert json.loads(result.stdout) == {"permissionDecision": "deny", "permissionDecisionReason": reason}


def test_an_escalation_asks_the_user(monkeypatch: pytest.MonkeyPatch) -> None:
    async def escalate(
        mode: str, payload: Mapping[str, JsonValue], config: Path | None, *, grade: bool, watcher_url: str | None = None
    ) -> None:
        raise integration.Escalation("PRIVATE")

    monkeypatch.setattr(integration, "run_hook", escalate)
    result = CliRunner().invoke(integration.app, ["enforce"], input='{"toolName":"bash"}')
    answer = json.loads(result.stdout)
    assert answer["permissionDecision"] == "ask" and "PRIVATE" not in result.stdout


@pytest.mark.parametrize("arguments,grade", [(["observe"], True), (["observe", "--record-only"], False)])
def test_record_only_skips_assessment(monkeypatch: pytest.MonkeyPatch, arguments: list[str], grade: bool) -> None:
    received: list[bool] = []

    async def accept(
        mode: str, payload: Mapping[str, JsonValue], config: Path | None, *, grade: bool, watcher_url: str | None = None
    ) -> None:
        received.append(grade)

    monkeypatch.setattr(integration, "run_hook", accept)
    result = CliRunner().invoke(integration.app, arguments, input="{}")
    assert result.exit_code == 0 and result.stdout == "{}\n"
    assert received == [grade]


def test_hooks_read_the_login_from_setup_configuration(tmp_path: Path) -> None:
    config = login_configuration(tmp_path / "config" / "config.json", tmp_path, "https://watcher.test/api")
    assert integration.watcher_settings(config) == integration.WatcherSettings(
        watcher_url="https://watcher.test/api", watcher_auth=True, watcher_state_dir=tmp_path / "config" / "watcher"
    )


def test_hooks_refuse_to_run_without_setup_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WATCHER_URL", "https://watcher.test/api")
    monkeypatch.setenv("WATCHER_API_KEY", "PRIVATE_KEY")
    with pytest.raises(ValueError, match="--config"):
        integration.watcher_settings(None)


def test_a_stored_api_key_configuration_asks_for_a_login(tmp_path: Path) -> None:
    key = tmp_path / "key"
    key.write_text("PRIVATE_KEY\n")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "project": str(tmp_path),
                "watcher_url": "https://watcher.test/api",
                "api_key_file": str(key),
                "api_key_env": None,
                "hook": {"exec": "/python", "args": []},
            }
        )
    )
    with pytest.raises(integration.UnsupportedCredentialError):
        integration.watcher_settings(config)
    result = CliRunner().invoke(integration.app, ["enforce", "--config", str(config)], input='{"toolName":"bash"}')
    answer = json.loads(result.stdout)
    assert (
        answer["permissionDecision"] == "deny" and "run setup again with a login" in answer["permissionDecisionReason"]
    )
    assert "PRIVATE_KEY" not in result.stdout + result.stderr


def test_replay_records_the_session_as_it_stands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    received: list[Mapping[str, JsonValue]] = []
    stored = RecordedSession(session=UUID(int=1), subagents={"agent-1": UUID(int=2)})

    async def record(
        client: object, payload: Mapping[str, JsonValue], *, grade: bool, config: Path | None = None
    ) -> RecordedSession | None:
        # The configuration locates the gate's escalations, so replay uploads answers too.
        assert not grade and config == tmp_path / "config" / "config.json"
        received.append(payload)
        return stored if len(received) == 1 else None

    config = login_configuration(tmp_path / "config" / "config.json", tmp_path, "https://watcher.test/api")
    monkeypatch.setattr(cli, "observe_callback", record)
    session_id = "4f3b0c9e-1c7d-4a47-9a0e-3a4e2f9b6c11"
    arguments = ["replay", "--config", str(config), "--session-id", session_id]
    first = CliRunner().invoke(cli.app, arguments)
    assert first.exit_code == 0
    assert received[0] == {"sessionId": session_id, "reason": "replay"}
    assert f"github-copilot-cli:{session_id}:agent:agent-1" in first.stdout
    second = CliRunner().invoke(cli.app, arguments)
    assert second.exit_code == 1 and "no assistant reply" in second.stderr


@pytest.mark.parametrize(
    "reason,arguments,detached",
    [
        ("user_exit", ["observe", "--record-only"], True),
        ("abort", ["observe"], True),
        ("complete", ["observe", "--record-only"], False),
        ("user_exit", ["observe", "--record-only", "--in-background"], False),
        ("user_exit", ["observe", "--watcher-url", "https://watcher.example.com/api", "--record-only"], True),
    ],
)
def test_interactive_endings_are_recorded_by_a_detached_process(
    monkeypatch: pytest.MonkeyPatch, reason: str, arguments: list[str], detached: bool
) -> None:
    started: list[tuple[str, list[str]]] = []
    ran: list[Mapping[str, JsonValue]] = []

    async def run(
        mode: str, payload: Mapping[str, JsonValue], config: Path | None, *, grade: bool, watcher_url: str | None = None
    ) -> None:
        ran.append(payload)

    monkeypatch.setattr(integration, "run_hook", run)
    monkeypatch.setattr(integration, "record_in_background", lambda raw, args: started.append((raw, args)))
    payload = json.dumps({"sessionId": "4f3b0c9e-1c7d-4a47-9a0e-3a4e2f9b6c11", "reason": reason})
    result = CliRunner().invoke(integration.app, arguments, input=payload)
    assert result.exit_code == 0 and result.stdout == "{}\n"
    if detached:
        assert started == [(payload, [a for a in arguments if a != "--in-background"])] and ran == []
    else:
        assert started == [] and len(ran) == 1


def test_a_turn_is_never_detached(monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[Mapping[str, JsonValue]] = []

    async def run(
        mode: str, payload: Mapping[str, JsonValue], config: Path | None, *, grade: bool, watcher_url: str | None = None
    ) -> None:
        ran.append(payload)

    monkeypatch.setattr(integration, "run_hook", run)
    monkeypatch.setattr(integration, "record_in_background", lambda raw, args: pytest.fail("detached a turn"))
    payload = {"sessionId": "4f3b0c9e-1c7d-4a47-9a0e-3a4e2f9b6c11", "transcriptPath": "/x", "reason": "user_exit"}
    assert CliRunner().invoke(integration.app, ["observe"], input=json.dumps(payload)).exit_code == 0
    assert len(ran) == 1


def test_the_detached_process_receives_the_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured = tmp_path / "stdin"

    class Popen:
        def __init__(self, command: list[str], **options: object) -> None:
            assert command[1:4] == ["-I", "-m", "watcher_github_copilot_cli.cli"]
            assert command[4:] == ["observe", "--record-only", "--in-background"]
            assert options["start_new_session"] is True
            self.stdin = captured.open("w")

    monkeypatch.setattr(integration.subprocess, "Popen", Popen)
    integration.record_in_background('{"reason": "user_exit"}', ["observe", "--record-only"])
    assert captured.read_text() == '{"reason": "user_exit"}'


@pytest.mark.parametrize(
    "url,refusal",
    [
        ("https://watcher.test/api", None),
        ("http://localhost:8765/api", None),
        ("http://127.0.0.1:8765/api", None),
        ("http://[::1]:8765/api", None),
        ("http://watcher.test/api", "HTTPS"),
        ("http://localhost.watcher.test/api", "HTTPS"),
        ("https://watcher.test/api?token=x", "query or fragment"),
        ("https://user:secret@watcher.test/api", "without credentials"),
    ],
)
def test_plain_http_is_accepted_only_for_this_machine(tmp_path: Path, url: str, refusal: str | None) -> None:
    config = tmp_path / "config.json"
    document = {"project": str(tmp_path), "watcher_url": url, "watcher_auth": True, "watcher_state_dir": str(tmp_path)}
    config.write_text(json.dumps(document | {"hook": {"exec": "/python", "args": []}}))
    if refusal is None:
        assert integration.watcher_settings(config).watcher_url == url
    else:
        with pytest.raises(ValueError, match=refusal):
            integration.watcher_settings(config)
