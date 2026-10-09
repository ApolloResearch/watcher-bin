"""Verify the personal install, per-project opt-outs and running beside project installs."""

import json
import os
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, get_args

import httpx
import pytest
from click.testing import Result
from pydantic import Field, JsonValue, TypeAdapter
from readback_fixture import save_watcher_login
from test_identity import ARGS, MILLIS, STAMP
from test_saved_judgments import ROOT, Judgment, JudgmentServer, SubmittedTool, outcome, stored
from test_setup import without_server
from typer.testing import CliRunner
from watcher_github_copilot_cli import cli, configuration, integration, scopes
from watcher_github_copilot_cli.cli import app
from watcher_github_copilot_cli.configuration import (
    HOOK_FILE,
    InstallationScope,
    ObserverConfiguration,
    ProjectHooks,
    configuration_path,
    copilot_home,
    load_configuration,
    names_another_server,
    project_root,
)
from watcher_github_copilot_cli.diagnostics import HookEvent, read_status
from watcher_github_copilot_cli.transcript import session_state_dir

from watcher_sdk import IntegrationAuth
from watcher_sdk.local_auth import InsecureLoginURLError

SESSION = "4f3b0c9e-1c7d-4a47-9a0e-3a4e2f9b6c11"
URL = "http://localhost:8765/api"
GIT_LOCATION_VARIABLES = ("GIT_DIR", "GIT_WORK_TREE")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Copilot's configuration directory for this test, with no managed policy and no Git location variables."""
    path = tmp_path / "copilot-home"
    monkeypatch.setenv("COPILOT_HOME", str(path))
    for name in GIT_LOCATION_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(configuration, "MANAGED_SETTINGS", tmp_path / "managed-settings.json")
    return path


@pytest.fixture
def credential(tmp_path: Path) -> Path:
    """A saved Watcher sign-in store for ``URL``."""
    state = tmp_path / "watcher"
    save_watcher_login(state, URL, "PRIVATE_TEST_CREDENTIAL")
    return state


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    return tmp_path / "configuration"


@pytest.fixture
def confirmed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for a person confirming opt-out and opt-in at an interactive terminal."""
    monkeypatch.setattr(cli, "terminal_confirms", lambda action, root: True)


def git(*arguments: str | Path) -> str:
    return subprocess.run(["git", *map(str, arguments)], capture_output=True, text=True, check=True).stdout


def repository(path: Path) -> Path:
    git("init", "-q", path)
    return path


def setup_arguments(credential: Path, config_dir: Path) -> list[str]:
    """Setup's arguments for the personal install, signed in with the saved sign-in in ``credential``."""
    return [
        "setup",
        "--watcher-url",
        URL,
        "--watcher-auth",
        "--watcher-state-dir",
        str(credential),
        "--config-dir",
        str(config_dir),
    ]


def setup(credential: Path, config_dir: Path, *extra: str, succeeds: bool = True) -> Result:
    result = CliRunner().invoke(app, [*setup_arguments(credential, config_dir), *extra])
    assert (result.exit_code == 0) is succeeds, result.output
    return result


def personal_hook(home: Path) -> Path:
    return home / "hooks" / HOOK_FILE.name


def personal_config(config_dir: Path) -> Path:
    return configuration_path(None, config_dir)


def trust(home: Path, *folders: Path) -> None:
    """Record ``folders`` as trusted the way Copilot does when you choose to remember a folder."""
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(
        "// Copilot writes comment lines first.\n" + json.dumps({"trustedFolders": [str(item) for item in folders]})
    )


def payloads(cwd: Path | str) -> dict[str, dict[str, JsonValue]]:
    """One native payload per installed event, all from a session started in ``cwd``."""
    return {
        "preToolUse": {
            "sessionId": SESSION,
            "cwd": str(cwd),
            "timestamp": 1,
            "toolName": "bash",
            "toolArgs": {"command": "pwd"},
        },
        "agentStop": {
            "sessionId": SESSION,
            "cwd": str(cwd),
            "timestamp": 1,
            "transcriptPath": "/x",
            "stopReason": "end_turn",
        },
        "sessionEnd": {"sessionId": SESSION, "cwd": str(cwd), "timestamp": 1, "reason": "complete"},
    }


_JSON_OBJECT = TypeAdapter(dict[str, JsonValue])


def copilot_loads(path: Path) -> bool:
    """Whether Copilot loads the hook file at ``path`` at all.

    Copilot 1.0.91 skips a whole file that is missing, has a ``version`` other
    than the number 1 (JSON ``true`` included), is disabled as a whole, holds an
    event whose value is not a list, or holds any entry nesting hooks more than
    one level deep. The file is read as plain JSON rather than through
    ``ProjectHooks``, so this stand-in for Copilot stays independent of the code
    it checks.
    """
    if not path.is_file():
        return False
    try:
        document = _JSON_OBJECT.validate_json(path.read_text())
    except ValueError:
        return False
    version = document.get("version", 1)
    hooks = document.get("hooks")
    if isinstance(version, bool) or version != 1 or document.get("disableAllHooks") is True:
        return False
    if not isinstance(hooks, dict):
        return False
    for entries in hooks.values():
        if not isinstance(entries, list):
            return False
        for entry in entries:
            inner = entry.get("hooks") if isinstance(entry, dict) else None
            if isinstance(inner, list) and any(isinstance(item, dict) and "hooks" in item for item in inner):
                return False
    return True


def run_installed(event: str, payload: Mapping[str, JsonValue], hook_files: list[Path]) -> list[Result]:
    """Run each installed entry for ``event`` in order, as Copilot runs personal hooks before project hooks.

    A file Copilot would skip as a whole (see ``copilot_loads``) is skipped here
    too, and another integration's entry does nothing. Pass only the files a
    running session loaded when it started: Copilot does not pick up a hook file
    added or restored later.
    """
    results: list[Result] = []
    for path in hook_files:
        if not copilot_loads(path):
            continue
        for entry in ProjectHooks.model_validate_json(path.read_text()).hooks.get(event, []):
            assert isinstance(entry, dict)
            if "args" not in entry:
                continue
            assert isinstance(entry["args"], list)
            results.append(
                CliRunner().invoke(app, [str(item) for item in entry["args"][3:]], input=json.dumps(payload))
            )
    return results


def fire(
    monkeypatch: pytest.MonkeyPatch, event: str, payload: Mapping[str, JsonValue], hook_files: list[Path]
) -> list[str]:
    """Run the installed entries for ``event`` (see ``run_installed``) without a Watcher.

    Returns the configurations whose callback went on to Watcher. Every callback
    must answer ``{}``: a gate that hands a call to Watcher here gets a deferred
    answer, and one that leaves the call alone never denies it.
    """
    handled: list[str] = []

    async def handle(
        mode: str, payload: Mapping[str, JsonValue], config: Path | None, *, grade: bool, watcher_url: str | None
    ) -> str | None:
        handled.append(str(config))
        return "deferred" if mode == "enforce" else None

    monkeypatch.setattr(integration, "run_hook", handle)
    monkeypatch.setattr(integration, "record_in_background", lambda raw, args: pytest.fail("detached"))
    for result in run_installed(event, payload, hook_files):
        assert result.exit_code == 0 and result.stdout == "{}\n", result.output
    return handled


class SharedWatcher(JudgmentServer):
    """A fake Watcher that keeps one stored decision per call, however many gate requests name it.

    Watcher stores one decision per native call and answers a repeated request
    for a stored call with that decision, so both installs can confirm it.
    ``callers`` holds the credential that sent each of ``submissions``.
    """

    callers: list[str] = Field(default_factory=list)

    def respond(self, request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/hooks/pre-tool-use"):
            return super().respond(request)
        self.callers.append(request.headers["authorization"])
        response = super().respond(request)
        submission = self.submissions[-1]
        if isinstance(submission.input, SubmittedTool) and not submission.ephemeral:
            assert submission.external_ids is not None and submission.input.tool_use_id is not None
            trajectory = self.sessions[submission.external_ids["other"]].trajectories[0]
            if all(item.tool_use_id != submission.input.tool_use_id for item in trajectory.judgments):
                trajectory.judgments.append(
                    Judgment(
                        tool_use_id=submission.input.tool_use_id,
                        tool_name=submission.input.tool_name,
                        tool_input=submission.input.tool_input,
                        applied="allow",
                        judged="allow",
                        source="rule",
                        grade_ids=[],
                    )
                )
        return response


def pending_call(project: Path) -> list[dict[str, JsonValue]]:
    """Copilot's log for ``SESSION`` while one shell call in ``project`` waits for the preToolUse hooks.

    The session started in ``project`` a minute from now, after every file the
    test wrote, as a session started after setup does. Copilot writes one hook
    record for the call before it runs every preToolUse entry, personal and
    project alike.
    """
    started = datetime.fromtimestamp(time.time() + 60, UTC).isoformat()
    context: dict[str, JsonValue] = {"cwd": str(project), "gitRoot": str(project)}
    call: dict[str, JsonValue] = {"toolCallId": "native-call", "name": "bash", "arguments": ARGS}
    return [
        {
            "type": "session.start",
            "timestamp": started,
            "data": {"sessionId": SESSION, "startTime": started, "context": context},
        },
        {"type": "user.message", "data": {"content": "Run the command"}},
        {"type": "assistant.turn_start", "data": {"turnId": "0"}},
        {"type": "assistant.message", "data": {"content": "", "toolRequests": [call]}},
        {
            "type": "hook.start",
            "timestamp": STAMP,
            "data": {
                "hookType": "preToolUse",
                "hookInvocationId": "invocation",
                "input": {
                    "sessionId": SESSION,
                    "cwd": str(project),
                    "toolCalls": [{"id": "native-call", "name": "bash", "args": ARGS}],
                },
            },
        },
    ]


def events(config: Path) -> list[HookEvent]:
    return [HookEvent.model_validate_json(line) for line in config.with_name("events.jsonl").read_text().splitlines()]


def test_setup_installs_personal_hooks_by_default(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    first = setup(credential, config_dir)
    installed = personal_hook(home).read_bytes()
    second = setup(credential, config_dir)

    assert personal_hook(home).read_bytes() == installed
    hooks = ProjectHooks.model_validate_json(installed).hooks
    assert set(hooks) == {"agentStop", "sessionEnd", "preToolUse"}
    assert all(len(entries) == 1 for entries in hooks.values())
    config = load_configuration(personal_config(config_dir))
    assert config.project is None and config.copilot_home == home and config.opted_out == []
    assert personal_config(config_dir) == config_dir.resolve() / "personal" / "config.json"
    assert str(personal_hook(home)) in first.stdout and "every Copilot session" in first.stdout
    assert "Installed the Blocking review hooks" in first.stdout
    assert "PRIVATE_TEST_CREDENTIAL" not in first.output + second.output + installed.decode()
    # A personal install writes nothing into the folder setup ran from.
    assert list(workspace.iterdir()) == []
    for warning in ("Trust this folder", "outside a Git repository", "local exclude file"):
        assert warning not in first.stderr

    removed = CliRunner().invoke(app, ["remove", "--config-dir", str(config_dir)])
    assert removed.exit_code == 0 and "Hooks removed" in removed.stdout
    assert not personal_hook(home).exists() and not personal_config(config_dir).exists()


@pytest.mark.parametrize("value", [None, ""])
def test_copilot_home_resolves_as_copilot_resolves_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    if value is None:
        monkeypatch.delenv("COPILOT_HOME", raising=False)
    else:
        # Copilot treats an empty COPILOT_HOME as unset.
        monkeypatch.setenv("COPILOT_HOME", value)
    assert copilot_home() == tmp_path / "user" / ".copilot"
    assert session_state_dir() == tmp_path / "user" / ".copilot" / "session-state"
    # Copilot uses a set value exactly as given, without expanding ~.
    monkeypatch.setenv("COPILOT_HOME", "~/elsewhere")
    assert copilot_home() == Path("~/elsewhere")


@pytest.mark.parametrize("value", ["relative/copilot", "~/copilot"])
def test_setup_refuses_a_copilot_home_copilot_would_resolve_from_its_working_folder(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COPILOT_HOME", value)
    result = CliRunner().invoke(app, setup_arguments(credential, config_dir))
    assert result.exit_code == 1 and "COPILOT_HOME" in result.stderr
    assert not (tmp_path / value).exists() and not personal_config(config_dir).exists()


def test_setup_refuses_an_unowned_or_redirected_personal_hook(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path
) -> None:
    hook = personal_hook(home)
    hook.parent.mkdir(parents=True)
    hook.write_text('{"version":1,"hooks":{"agentStop":[{"bash":"echo mine"}]}}\n')
    arguments = setup_arguments(credential, config_dir)
    assert CliRunner().invoke(app, arguments).exit_code == 1
    assert "echo mine" in hook.read_text()

    hook.unlink()
    hook.parent.rmdir()
    outside = tmp_path / "dotfiles-hooks"
    outside.mkdir()
    hook.parent.symlink_to(outside, target_is_directory=True)
    assert CliRunner().invoke(app, arguments).exit_code == 1
    assert list(outside.iterdir()) == [] and not personal_config(config_dir).exists()


def test_one_machine_configuration_for_the_personal_install_and_one_per_project(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = repository(tmp_path / "project")
    setup(credential, config_dir)
    record_only = setup(credential, config_dir, "--project", str(project), "--record-only")

    assert "Installed the Record only hooks" in record_only.stdout
    personal = load_configuration(personal_config(config_dir))
    own = load_configuration(configuration_path(project, config_dir))
    assert personal.project is None and personal.gate is not None
    assert own.project == project and own.copilot_home is None and own.gate is None
    assert personal_config(config_dir) != configuration_path(project, config_dir)

    # The personal install keeps the Copilot home it was installed into, so removal
    # finds its hook file even when COPILOT_HOME has changed since.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "other-home"))
    moved = CliRunner().invoke(app, setup_arguments(credential, config_dir))
    assert moved.exit_code == 1 and not (tmp_path / "other-home").exists()
    assert CliRunner().invoke(app, ["remove", "--config-dir", str(config_dir)]).exit_code == 0
    assert not personal_hook(home).exists()
    assert (project / HOOK_FILE).exists() and configuration_path(project, config_dir).exists()
    removed = CliRunner().invoke(app, ["remove", "--project", str(project), "--config-dir", str(config_dir)])
    assert removed.exit_code == 0 and not (project / HOOK_FILE).exists()


def test_personal_setup_warns_about_settings_and_policy_that_block_personal_hooks(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path
) -> None:
    home.mkdir()
    (home / "settings.json").write_text('// user settings\n{"disableAllHooks": true, "disabledHooks": ["abc"]}')
    policy = tmp_path / "managed-settings.json"
    policy.write_text('{"allowManagedHooksOnly": true}')

    result = setup(credential, config_dir)

    assert "disableAllHooks" in result.stderr and "disabledHooks" in result.stderr
    assert "no hook will run" not in result.stderr
    assert "only managed hooks" in result.stderr
    assert "Trust this folder" not in result.stderr and "Claude Code hooks" not in result.stderr

    (home / "settings.json").write_text("{}")
    policy.write_text('{"allowManagedHooksOnly": false}')
    assert "Warning" not in setup(credential, config_dir).stderr


@pytest.mark.parametrize("settings", ["settings.json", "config.json"])
def test_user_level_disable_all_hooks_is_reported_without_claiming_no_hook_will_run(
    home: Path, credential: Path, config_dir: Path, settings: str
) -> None:
    home.mkdir()
    (home / settings).write_text('{"disableAllHooks": true}')

    result = setup(credential, config_dir)

    assert "Copilot's user settings set disableAllHooks" in result.stderr
    assert "no hook will run" not in result.stderr


def test_a_managed_only_policy_is_reported_for_a_project_install_too(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path
) -> None:
    project = repository(tmp_path / "project")
    trust(home, project)
    policy = tmp_path / "managed-settings.json"
    policy.write_text('{"allowManagedHooksOnly": true}')
    assert "only managed hooks" in setup(credential, config_dir, "--project", str(project)).stderr
    policy.write_text("{ not json")
    assert f"could not read {policy}" in setup(credential, config_dir, "--project", str(project)).stderr


def in_terminal(*arguments: str, typed: str) -> tuple[int, str]:
    """Run the CLI with a pseudo-terminal as stdin and stdout, as a person at a terminal does, typing ``typed``."""
    controller, terminal = os.openpty()
    process = subprocess.Popen(
        [sys.executable, "-m", "watcher_github_copilot_cli.cli", *arguments],
        stdin=terminal,
        stdout=terminal,
        stderr=terminal,
    )
    os.close(terminal)
    os.write(controller, typed.encode() + b"\n")
    output = b""
    while True:
        try:
            chunk = os.read(controller, 4096)
        except OSError:
            break
        if not chunk:
            break
        output += chunk
    os.close(controller)
    return process.wait(timeout=60), output.decode(errors="replace")


@pytest.mark.parametrize("command", ["opt-out", "opt-in"])
def test_opting_out_or_in_needs_a_person_at_an_interactive_terminal(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path, command: str
) -> None:
    project = repository(tmp_path / "project")
    setup(credential, config_dir)
    if command == "opt-in":
        configuration.set_opt_out(project, config_dir, opted_out=True)
    before = personal_config(config_dir).read_text()
    arguments = [command, "--project", str(project), "--config-dir", str(config_dir)]

    # Copilot runs an agent's shell commands without a terminal, so the agent cannot confirm.
    piped = subprocess.run(
        [sys.executable, "-m", "watcher_github_copilot_cli.cli", *arguments],
        input=f"{project}\n",
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    refused = CliRunner().invoke(app, arguments, input=f"{project}\n")
    mistyped, mistyped_output = in_terminal(*arguments, typed=str(tmp_path))

    for status, output in ((piped.returncode, piped.stderr), (refused.exit_code, refused.stderr)):
        assert status == 1 and "interactive terminal" in output, output
        # The check stops an agent's ordinary command, not a same-user process.
        assert "fake a terminal" in output and "edit the configuration" in output, output
    assert mistyped == 1 and "did not match" in mistyped_output
    assert personal_config(config_dir).read_text() == before
    confirmed, output = in_terminal(*arguments, typed=str(project))
    assert confirmed == 0, output
    assert load_configuration(personal_config(config_dir)).opted_out == ([project] if command == "opt-out" else [])


@pytest.mark.parametrize("command", ["opt-out", "opt-in"])
def test_opt_out_and_opt_in_write_the_folder_that_was_confirmed(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    first = repository(tmp_path / "first").resolve()
    second = repository(tmp_path / "second").resolve()
    link = tmp_path / "link"
    link.symlink_to(first, target_is_directory=True)
    setup(credential, config_dir)
    if command == "opt-in":
        for root in (first, second):
            configuration.set_opt_out(root, config_dir, opted_out=True)
    asked: list[Path] = []

    def confirm(action: str, root: Path) -> bool:
        asked.append(root)
        # The folder changes while the prompt waits for the person.
        link.unlink()
        link.symlink_to(second, target_is_directory=True)
        return True

    monkeypatch.setattr(cli, "terminal_confirms", confirm)
    result = CliRunner().invoke(app, [command, "--project", str(link), "--config-dir", str(config_dir)])

    assert result.exit_code == 0 and asked == [first], result.output
    assert load_configuration(personal_config(config_dir)).opted_out == ([first] if command == "opt-out" else [second])

    def unresolvable(folder: Path) -> Path:
        raise PermissionError(folder)

    # A folder whose project cannot be found is refused, never changed without asking.
    monkeypatch.setattr(cli, "project_root", unresolvable)
    refused = CliRunner().invoke(app, [command, "--project", str(second), "--config-dir", str(config_dir)])
    assert refused.exit_code == 1 and asked == [first]
    assert load_configuration(personal_config(config_dir)).opted_out == ([first] if command == "opt-out" else [second])


def test_opting_a_project_out_is_kept_only_in_the_machine_configuration(
    confirmed: None, home: Path, credential: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = repository(tmp_path / "project")
    (project / "src").mkdir()
    before = sorted(project.rglob("*"))
    assert (
        CliRunner().invoke(app, ["opt-out", "--project", str(project), "--config-dir", str(config_dir)]).exit_code == 1
    )
    setup(credential, config_dir)

    result = CliRunner().invoke(app, ["opt-out", "--project", str(project / "src"), "--config-dir", str(config_dir)])

    assert result.exit_code == 0 and str(project) in result.stdout
    assert load_configuration(personal_config(config_dir)).opted_out == [project]
    assert sorted(project.rglob("*")) == before
    # Repeating setup keeps the opt-out; repeating the opt-out changes nothing.
    setup(credential, config_dir, "--record-only")
    again = CliRunner().invoke(app, ["opt-out", "--project", str(project), "--config-dir", str(config_dir)])
    assert again.exit_code == 0 and "already" in again.stdout
    assert load_configuration(personal_config(config_dir)).opted_out == [project]

    for event, payload in payloads(project / "src").items():
        assert fire(monkeypatch, event, payload, [personal_hook(home)]) == []
    # The record-only setup above removed the gate, so only the two observers fire.
    skipped = [item for item in events(personal_config(config_dir)) if item.kind == "skipped"]
    assert len(skipped) == 2 and {item.skip for item in skipped} == {"opted_out"}

    cleared = CliRunner().invoke(app, ["opt-in", "--project", str(project), "--config-dir", str(config_dir)])
    assert cleared.exit_code == 0 and load_configuration(personal_config(config_dir)).opted_out == []
    assert fire(monkeypatch, "agentStop", payloads(project)["agentStop"], [personal_hook(home)]) == [
        str(personal_config(config_dir))
    ]
    missing = CliRunner().invoke(app, ["opt-out", "--project", str(tmp_path / "gone"), "--config-dir", str(config_dir)])
    assert missing.exit_code == 1 and "Opt-out failed" in missing.stderr


def test_neither_gate_allows_or_denies_in_an_opted_out_project(
    confirmed: None, home: Path, credential: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "scratch"
    project.mkdir()
    setup(credential, config_dir)
    setup(credential, config_dir, "--project", str(project))
    assert (
        CliRunner().invoke(app, ["opt-out", "--project", str(project), "--config-dir", str(config_dir)]).exit_code == 0
    )

    async def unexpected(
        mode: str, payload: Mapping[str, JsonValue], config: Path | None, *, grade: bool, watcher_url: str | None
    ) -> None:
        pytest.fail("an opted-out callback reached Watcher")

    monkeypatch.setattr(integration, "run_hook", unexpected)
    detached: list[list[str]] = []
    monkeypatch.setattr(integration, "record_in_background", lambda raw, arguments: detached.append(arguments))

    for hook in (personal_hook(home), project / HOOK_FILE):
        installed = ProjectHooks.model_validate_json(hook.read_text())
        [gate] = installed.hooks["preToolUse"]
        assert isinstance(gate, dict) and isinstance(gate["exec"], str) and isinstance(gate["args"], list)

        answer = subprocess.run(
            [gate["exec"], *map(str, gate["args"])],
            input=json.dumps(payloads(project)["preToolUse"]),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        assert answer.returncode == 0 and answer.stdout == "{}\n", hook
        # An interactive exit hands its recording to a detached process at once, and
        # that process leaves the opted-out project alone.
        [observer] = installed.hooks["sessionEnd"]
        assert isinstance(observer, dict) and isinstance(observer["args"], list)
        ending = payloads(project)["sessionEnd"] | {"reason": "user_exit"}
        detached.clear()
        result = CliRunner().invoke(app, [str(item) for item in observer["args"][3:]], input=json.dumps(ending))
        assert result.exit_code == 0 and result.stdout == "{}\n" and len(detached) == 1, hook
        worker = CliRunner().invoke(app, [*detached[0], "--in-background"], input=json.dumps(ending))
        assert worker.exit_code == 0 and worker.stdout == "{}\n", hook


def test_a_callback_without_a_usable_folder_is_recorded_and_judged_by_both_installs(
    confirmed: None, home: Path, credential: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "scratch"
    project.mkdir()
    setup(credential, config_dir)
    setup(credential, config_dir, "--project", str(project))
    assert (
        CliRunner().invoke(app, ["opt-out", "--project", str(project), "--config-dir", str(config_dir)]).exit_code == 0
    )
    both = [str(personal_config(config_dir)), str(configuration_path(project, config_dir))]
    for cwd in (None, "relative/scratch", 7):
        payload: dict[str, JsonValue] = dict(payloads(project)["preToolUse"])
        if cwd is None:
            payload.pop("cwd")
        else:
            payload["cwd"] = cwd
        assert fire(monkeypatch, "preToolUse", payload, [personal_hook(home), project / HOOK_FILE]) == both


@pytest.mark.parametrize(
    "layout,cwd,root",
    [
        ("plain", "plain/sub", "plain/sub"),
        ("repository", "repo/sub/deep", "repo"),
        ("repository", "link/deep", "repo"),
        ("worktree", "linked/inner", "linked"),
        ("nested", "repo/sub/nested/deeper", "repo/sub/nested"),
        ("bare-git-layout", "minimal/sub", "minimal"),
    ],
)
def test_project_root_matches_copilots_repository_root(tmp_path: Path, layout: str, cwd: str, root: str) -> None:
    (tmp_path / "plain/sub").mkdir(parents=True)
    repo = repository(tmp_path / "repo")
    (repo / "sub/deep").mkdir(parents=True)
    (tmp_path / "link").symlink_to(repo / "sub", target_is_directory=True)
    if layout == "worktree":
        git(
            "-C",
            repo,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "x",
        )
        git("-C", repo, "worktree", "add", "-q", tmp_path / "linked")
        (tmp_path / "linked/inner").mkdir()
    if layout == "nested":
        repository(repo / "sub/nested")
        (repo / "sub/nested/deeper").mkdir()
    if layout == "bare-git-layout":
        for folder in ("objects", "refs", "sub"):
            (tmp_path / "minimal" / (folder if folder == "sub" else f".git/{folder}")).mkdir(parents=True)
        (tmp_path / "minimal/.git/HEAD").write_text("ref: refs/heads/main\n")

    assert project_root(tmp_path / cwd) == (tmp_path / root).resolve()


@pytest.mark.timeout(20)
@pytest.mark.parametrize(
    "marker",
    [
        "unreadable",
        "oversized",
        "fifo",
        "symlink",
        "swapped-for-a-fifo",
        "folder-without-head",
        "folder-without-refs",
        "file-not-utf8",
        "file-without-gitdir",
        "file-to-a-missing-folder",
        "file-to-an-invalid-folder",
    ],
)
def test_a_git_marker_that_cannot_be_inspected_keeps_an_opted_out_parent_from_applying(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, marker: str
) -> None:
    # Treating such a marker, or one that names no valid repository, as absent would
    # let the search for the project reach an opted-out repository above it. The
    # project stays unknown instead, so the hooks record and judge, and reading the
    # marker never blocks before the gate's deadline.
    if marker == "unreadable" and os.geteuid() == 0:
        pytest.skip("root can read a file with no permissions")
    outer = repository(tmp_path / "outer").resolve()
    inner = outer / "inner"
    inner.mkdir()
    real = repository(tmp_path / "real")
    git_file = inner / ".git"
    if marker == "unreadable":
        git_file.write_text(f"gitdir: {real / '.git'}\n")
        git_file.chmod(0)
    elif marker == "oversized":
        git_file.write_text(f"gitdir: {real / '.git'}\n" + "x" * 70 * 1024)
    elif marker == "fifo":
        os.mkfifo(git_file)
    elif marker == "symlink":
        git_file.symlink_to(real / ".git", target_is_directory=True)
    elif marker.startswith("folder-without-"):
        # Copilot accepts a .git folder only with HEAD, objects and refs.
        git_file.mkdir()
        for name in ("objects", "refs"):
            if marker != f"folder-without-{name}":
                (git_file / name).mkdir()
        if marker != "folder-without-head":
            (git_file / "HEAD").write_text("ref: refs/heads/main\n")
    elif marker == "file-not-utf8":
        git_file.write_bytes(b"gitdir: " + str(real / ".git").encode() + b"\xff\n")
    elif marker == "file-without-gitdir":
        git_file.write_text(f"see {real / '.git'}\n")
    elif marker == "file-to-a-missing-folder":
        git_file.write_text(f"gitdir: {tmp_path / 'missing'}\n")
    elif marker == "file-to-an-invalid-folder":
        (tmp_path / "empty").mkdir()
        git_file.write_text(f"gitdir: {tmp_path / 'empty'}\n")
    else:
        # A FIFO swapped in after the marker was found to be a regular file, before it is read.
        git_file.write_text(f"gitdir: {real / '.git'}\n")
        lstat = Path.lstat

        def swapped(path: Path) -> os.stat_result:
            info = lstat(path)
            if path == git_file and stat.S_ISREG(info.st_mode):
                git_file.unlink()
                os.mkfifo(git_file)
            return info

        monkeypatch.setattr(Path, "lstat", swapped)
    setup(credential, config_dir)
    configuration.set_opt_out(outer, config_dir, opted_out=True)

    with pytest.raises(OSError):
        project_root(inner)
    callback = payloads(inner)["preToolUse"]
    assert fire(monkeypatch, "preToolUse", callback, [personal_hook(home)]) == [str(personal_config(config_dir))]


def test_a_held_diagnostics_lock_never_delays_the_detached_session_end_recorder(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Saving diagnostics can wait two seconds for its lock, longer than Copilot gives
    # an interactive session's sessionEnd hooks, so the hand-off comes first.
    project = repository(tmp_path / "project")
    setup(credential, config_dir)
    lock = personal_config(config_dir).with_name("diagnostics.lock")
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"from filelock import FileLock; import time; held = FileLock({str(lock)!r}); held.acquire(); print('held', flush=True); time.sleep(20)",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout is not None and holder.stdout.readline().strip() == "held"
    handed_off: list[float] = []
    monkeypatch.setattr(integration, "record_in_background", lambda raw, arguments: handed_off.append(time.monotonic()))
    [observer] = ProjectHooks.model_validate_json(personal_hook(home).read_text()).hooks["sessionEnd"]
    assert isinstance(observer, dict) and isinstance(observer["args"], list)
    ending = payloads(project)["sessionEnd"] | {"reason": "abort"}
    started = time.monotonic()
    try:
        result = CliRunner().invoke(app, [str(item) for item in observer["args"][3:]], input=json.dumps(ending))
    finally:
        holder.kill()
        holder.wait()

    assert result.exit_code == 0 and len(handed_off) == 1 and handed_off[0] - started < 1.0


def test_an_unexpected_error_in_the_scope_check_is_saved_and_the_call_still_handled(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = repository(tmp_path / "project")
    setup(credential, config_dir)

    def broken(config: Path, payload: Mapping[str, JsonValue]) -> None:
        raise RuntimeError("unexpected")

    handled: list[str] = []

    async def handle(
        mode: str, payload: Mapping[str, JsonValue], config: Path | None, *, grade: bool, watcher_url: str | None
    ) -> str | None:
        handled.append(str(config))
        return "deferred" if mode == "enforce" else None

    monkeypatch.setattr(integration, "skip_reason", broken)
    monkeypatch.setattr(integration, "run_hook", handle)
    [result] = run_installed("preToolUse", payloads(project)["preToolUse"], [personal_hook(home)])

    assert result.exit_code == 0 and result.stdout == "{}\n" and "Traceback" not in result.stderr, result.stderr
    assert handled == [str(personal_config(config_dir))]
    failures = [(item.failure, item.hook) for item in events(personal_config(config_dir)) if item.kind == "failed"]
    assert failures == [("configuration", "enforce")]


def test_a_slow_scope_check_never_holds_up_the_detached_session_end_recorder(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Copilot stops an interactive session's sessionEnd hooks after about 1.5 seconds,
    # so the hook hands the recording to a detached process before any opt-out check.
    project = repository(tmp_path / "project")
    setup(credential, config_dir)
    release = threading.Event()

    def hangs(config: Path, payload: Mapping[str, JsonValue]) -> None:
        release.wait(30)

    detached: list[list[str]] = []
    monkeypatch.setattr(integration, "skip_reason", hangs)
    monkeypatch.setattr(integration, "SCOPE_SECONDS", 30)
    monkeypatch.setattr(integration, "record_in_background", lambda raw, arguments: detached.append(arguments))
    [observer] = ProjectHooks.model_validate_json(personal_hook(home).read_text()).hooks["sessionEnd"]
    assert isinstance(observer, dict) and isinstance(observer["args"], list)
    ending = payloads(project)["sessionEnd"] | {"reason": "user_exit"}
    started = time.monotonic()
    try:
        result = CliRunner().invoke(app, [str(item) for item in observer["args"][3:]], input=json.dumps(ending))
    finally:
        release.set()

    assert result.exit_code == 0 and len(detached) == 1 and time.monotonic() - started < 1.5


def test_a_scope_check_that_hangs_still_records_and_judges(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The scope check runs before the gate's own deadline and Copilot's outer timeout
    # fails open, so a check that does not finish in time leaves the call to the hooks.
    project = repository(tmp_path / "project")
    setup(credential, config_dir)
    release = threading.Event()

    def hangs(config: Path, payload: Mapping[str, JsonValue]) -> None:
        release.wait(30)

    monkeypatch.setattr(integration, "skip_reason", hangs)
    monkeypatch.setattr(integration, "SCOPE_SECONDS", 0.2)
    started = time.monotonic()
    try:
        handled = fire(monkeypatch, "preToolUse", payloads(project)["preToolUse"], [personal_hook(home)])
    finally:
        release.set()

    assert handled == [str(personal_config(config_dir))] and time.monotonic() - started < 10


def test_opt_outs_follow_symlinks_and_git_roots_but_not_plain_subfolders(
    confirmed: None, home: Path, credential: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = repository(tmp_path / "repo")
    (repo / "service/api").mkdir(parents=True)
    link = tmp_path / "service-link"
    link.symlink_to(repo / "service", target_is_directory=True)
    plain = tmp_path / "plain"
    (plain / "sub").mkdir(parents=True)
    setup(credential, config_dir)
    for folder in (link, plain):
        result = CliRunner().invoke(app, ["opt-out", "--project", str(folder), "--config-dir", str(config_dir)])
        assert result.exit_code == 0
    assert load_configuration(personal_config(config_dir)).opted_out == [repo.resolve(), plain.resolve()]
    personal = str(personal_config(config_dir))

    for cwd in (repo, repo / "service/api", link / "api", plain):
        assert fire(monkeypatch, "preToolUse", payloads(cwd)["preToolUse"], [personal_hook(home)]) == []
    # Outside Git, Copilot treats the folder it starts in as the project.
    assert fire(monkeypatch, "preToolUse", payloads(plain / "sub")["preToolUse"], [personal_hook(home)]) == [personal]

    cleared = CliRunner().invoke(app, ["opt-in", "--project", str(link / "api"), "--config-dir", str(config_dir)])
    assert cleared.exit_code == 0 and load_configuration(personal_config(config_dir)).opted_out == [plain.resolve()]
    plain_removed = tmp_path / "removed"
    plain_removed.mkdir()
    assert (
        CliRunner().invoke(app, ["opt-out", "--project", str(plain_removed), "--config-dir", str(config_dir)]).exit_code
        == 0
    )
    plain_removed.rmdir()
    gone = CliRunner().invoke(app, ["opt-in", "--project", str(plain_removed), "--config-dir", str(config_dir)])
    assert (
        gone.exit_code == 0 and plain_removed.resolve() not in load_configuration(personal_config(config_dir)).opted_out
    )


@pytest.mark.parametrize("order", ["personal-first", "project-first"])
def test_both_installs_record_and_gate_a_project_they_both_cover(
    home: Path,
    credential: Path,
    config_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    order: str,
) -> None:
    project = repository(tmp_path / "project")
    project_credential = tmp_path / "project-login"
    save_watcher_login(project_credential, URL, "PROJECT_TEST_CREDENTIAL")
    trust(home, project)
    installs = [(credential, []), (project_credential, ["--project", str(project)])]
    for key, extra in installs if order == "personal-first" else reversed(installs):
        setup(key, config_dir, *extra)
    hook_files = [personal_hook(home), project / HOOK_FILE]
    watcher = SharedWatcher(sessions={ROOT: stored()}, response=outcome(decision="allow", judged="allow"))

    async def handle(transport: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        return watcher.respond(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)
    log = home / "session-state" / SESSION / "events.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text("".join(json.dumps(event) + "\n" for event in pending_call(project)))
    callback: dict[str, JsonValue] = {
        "sessionId": SESSION,
        "timestamp": MILLIS,
        "cwd": str(project),
        "toolName": "bash",
        "toolArgs": ARGS,
    }

    answers = [
        _JSON_OBJECT.validate_json(result.stdout) for result in run_installed("preToolUse", callback, hook_files)
    ]

    assert [answer["permissionDecision"] for answer in answers] == ["allow", "allow"]
    assert watcher.callers == ["Bearer PRIVATE_TEST_CREDENTIAL", "Bearer PROJECT_TEST_CREDENTIAL"]
    # Both gates name the same native call in the same session, so Watcher keeps one decision for it.
    named = SubmittedTool(tool_name="Bash", tool_input=ARGS, tool_use_id="native-call")
    assert [submission.input for submission in watcher.submissions] == [named, named]
    assert all(not item.ephemeral and item.external_ids == {"other": ROOT} for item in watcher.submissions)
    assert watcher.submissions[0].messages == watcher.submissions[1].messages
    assert len(watcher.sessions[ROOT].trajectories[0].judgments) == 1

    turn: dict[str, JsonValue] = {"sessionId": SESSION, "transcriptPath": str(log), "timestamp": MILLIS}
    result: dict[str, JsonValue] = {"content": "done"}
    finished: list[dict[str, JsonValue]] = [
        {"type": "hook.end", "data": {"hookInvocationId": "invocation"}},
        {"type": "tool.execution_complete", "data": {"toolCallId": "native-call", "success": True, "result": result}},
        {"type": "assistant.message", "data": {"content": "Done"}},
        {"type": "assistant.turn_end", "data": {"turnId": "0"}},
        {"type": "hook.start", "data": {"hookType": "agentStop", "input": turn}},
    ]
    with log.open("a") as stream:
        stream.writelines(json.dumps(event) + "\n" for event in finished)

    recorded = run_installed("agentStop", turn, hook_files)

    assert [(item.exit_code, item.stdout) for item in recorded] == [(0, "{}\n"), (0, "{}\n")]
    assert watcher.callers[2:] == ["Bearer PRIVATE_TEST_CREDENTIAL", "Bearer PROJECT_TEST_CREDENTIAL"]
    # Both installs send the same history; recording is idempotent, so the second adds no messages.
    first, second = watcher.submissions[2:]
    assert first.input == second.input == [] and first.messages == second.messages
    for config in (personal_config(config_dir), configuration_path(project, config_dir)):
        status = read_status(config)
        assert status.last_delivery is not None and status.last_review_check is not None, config
        assert (status.last_review_check.confirmed, status.last_review_check.unconfirmed) == (1, 0), config
        assert all(item.kind != "skipped" for item in events(config))


def test_opting_a_project_out_turns_off_its_project_install_too(
    confirmed: None, home: Path, credential: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = repository(tmp_path / "project")
    (project / "src").mkdir()
    link = tmp_path / "project-link"
    link.symlink_to(project, target_is_directory=True)
    setup(credential, config_dir)
    setup(credential, config_dir, "--project", str(project))
    opted = CliRunner().invoke(app, ["opt-out", "--project", str(link / "src"), "--config-dir", str(config_dir)])
    assert opted.exit_code == 0 and str(project) in opted.stdout
    hook_files = [personal_hook(home), project / HOOK_FILE]
    own = configuration_path(project, config_dir)

    for cwd in (project, project / "src", link / "src"):
        for event, payload in payloads(cwd).items():
            assert fire(monkeypatch, event, payload, hook_files) == [], (cwd, event)
    for config in (personal_config(config_dir), own):
        assert [item.skip for item in events(config) if item.kind == "skipped"] == ["opted_out"] * 9, config

    cleared = CliRunner().invoke(app, ["opt-in", "--project", str(project), "--config-dir", str(config_dir)])
    assert cleared.exit_code == 0
    for event, payload in payloads(project).items():
        assert fire(monkeypatch, event, payload, hook_files) == [str(personal_config(config_dir)), str(own)], event


@pytest.mark.parametrize("unread", ["no-personal-install", "personal-configuration"])
def test_a_project_install_handles_its_calls_when_it_cannot_read_the_opt_outs(
    confirmed: None,
    home: Path,
    credential: Path,
    config_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unread: str,
) -> None:
    project = repository(tmp_path / "project")
    if unread == "personal-configuration":
        setup(credential, config_dir)
        opted = CliRunner().invoke(app, ["opt-out", "--project", str(project), "--config-dir", str(config_dir)])
        assert opted.exit_code == 0
    setup(credential, config_dir, "--project", str(project))
    if unread == "personal-configuration":
        personal_config(config_dir).write_text("{")
    own = str(configuration_path(project, config_dir))
    for event, payload in payloads(project).items():
        assert fire(monkeypatch, event, payload, [project / HOOK_FILE]) == [own], event


def refused_by_hooks(path: Path, stored: str, tmp_path: Path) -> None:
    """Rewrite the configuration at ``path`` so its hooks refuse it: redirected to another server, or naming an API key."""
    document = json.loads(path.read_text())
    if stored == "redirected":
        document["watcher_url"] = "http://127.0.0.1:9/api"
    else:
        document |= {"watcher_auth": False, "watcher_state_dir": None, "api_key_file": str(tmp_path / "key")}
    path.write_text(json.dumps(document))


@pytest.mark.parametrize("stored", ["redirected", "api-key"])
def test_opt_outs_and_overlaps_hold_for_configurations_the_hooks_refuse(
    confirmed: None,
    home: Path,
    credential: Path,
    config_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stored: str,
) -> None:
    project = repository(tmp_path / "project")
    setup(credential, config_dir)
    setup(credential, config_dir, "--project", str(project))
    refused_by_hooks(configuration_path(project, config_dir), stored, tmp_path)
    # Copilot still runs the project's hooks, so the personal install still counts it as an overlap.
    personal = CliRunner().invoke(app, ["status", "--config-dir", str(config_dir)])
    assert personal.exit_code == 0 and f"A project install also covers {project}" in personal.stderr
    refused_by_hooks(personal_config(config_dir), stored, tmp_path)

    opted = CliRunner().invoke(app, ["opt-out", "--project", str(project), "--config-dir", str(config_dir)])

    assert opted.exit_code == 0, opted.output
    for event, payload in payloads(project).items():
        assert fire(monkeypatch, event, payload, [personal_hook(home), project / HOOK_FILE]) == [], event
    cleared = CliRunner().invoke(app, ["opt-in", "--project", str(project), "--config-dir", str(config_dir)])
    assert cleared.exit_code == 0 and "cover" in cleared.stdout


def profile_setup(credential: Path, config_dir: Path, tmp_path: Path, *extra: str) -> Result:
    """Set up with a credential profile for ``URL``, as ``watcher-sdk integrations install`` does."""
    profile = tmp_path / "profile.json"
    profile.write_text(IntegrationAuth(base_url=URL, kind="watcher_login", state_dir=credential).model_dump_json())
    arguments = ["setup", "--watcher-url", URL, "--auth-profile", str(profile), "--config-dir", str(config_dir)]
    result = CliRunner().invoke(app, [*arguments, *extra])
    assert result.exit_code == 0, result.output
    return result


ServerField = Literal["watcher_url", "auth_profile"]


def rewrite_servers(path: Path, fields: tuple[ServerField, ...], server: str) -> None:
    """Point only ``fields`` of the configuration at ``path``, its server, its sign-in's or both, at ``server``.

    The hook commands stored in it keep naming the server setup wrote.
    """
    document = json.loads(path.read_text())
    if "watcher_url" in fields:
        document["watcher_url"] = server
    if "auth_profile" in fields:
        document["auth_profile"]["base_url"] = server
    path.write_text(json.dumps(document))


SERVER_REWRITES = [
    pytest.param(("watcher_url",), "http://127.0.0.1:9/api", id="server-on-this-machine"),
    pytest.param(("watcher_url",), "https://elsewhere.example/api", id="server-elsewhere"),
    pytest.param(("watcher_url",), "http://elsewhere.example/api", id="plain-http-server-elsewhere"),
    pytest.param(("auth_profile",), "http://127.0.0.1:9/api", id="login-on-this-machine"),
    pytest.param(("auth_profile",), "https://elsewhere.example/api", id="login-elsewhere"),
    pytest.param(("auth_profile",), "http://elsewhere.example/api", id="plain-http-login-elsewhere"),
    pytest.param(get_args(ServerField), "http://elsewhere.example/api", id="plain-http-server-and-login-elsewhere"),
]


@pytest.mark.parametrize(("fields", "server"), SERVER_REWRITES)
def test_setup_opt_outs_and_removal_repair_a_configuration_with_its_server_or_login_rewritten(
    confirmed: None,
    home: Path,
    credential: Path,
    config_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fields: tuple[ServerField, ...],
    server: str,
) -> None:
    project = repository(tmp_path / "project")
    profile_setup(credential, config_dir, tmp_path)
    profile_setup(credential, config_dir, tmp_path, "--project", str(project))
    path = personal_config(config_dir)
    assert not names_another_server(load_configuration(path))
    rewrite_servers(path, fields, server)
    # The hooks refuse it, since it no longer names the server their commands name,
    # or since its sign-in is plain HTTP to another machine.
    with pytest.raises(ValueError, match="different|HTTPS"):
        load_configuration(path)
    assert names_another_server(load_configuration(path, allow_server_mismatch=True))

    opted = CliRunner().invoke(app, ["opt-out", "--project", str(project), "--config-dir", str(config_dir)])

    assert opted.exit_code == 0, opted.output
    for event, payload in payloads(project).items():
        assert fire(monkeypatch, event, payload, [personal_hook(home), project / HOOK_FILE]) == [], event
    cleared = CliRunner().invoke(app, ["opt-in", "--project", str(project), "--config-dir", str(config_dir)])
    assert cleared.exit_code == 0 and "cover" in cleared.stdout
    profile_setup(credential, config_dir, tmp_path)
    repaired = load_configuration(path)
    assert repaired.watcher_url == URL and repaired.auth_profile is not None and repaired.auth_profile.base_url == URL
    rewrite_servers(configuration_path(project, config_dir), fields, server)
    removed = CliRunner().invoke(app, ["remove", "--project", str(project), "--config-dir", str(config_dir)])
    assert removed.exit_code == 0, removed.output
    assert not (project / HOOK_FILE).exists() and not configuration_path(project, config_dir).exists()


def test_a_configuration_naming_one_plain_http_server_elsewhere_is_refused_even_for_repair(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path
) -> None:
    profile_setup(credential, config_dir, tmp_path)
    path = personal_config(config_dir)
    server = "http://elsewhere.example/api"
    rewrite_servers(path, get_args(ServerField), server)
    # With the hook commands rewritten too, the configuration names a single server,
    # so it is not redirected and the HTTPS rule applies to every reader.
    document = json.loads(path.read_text())
    for command in ("hook", "gate"):
        arguments = document[command]["args"]
        arguments[arguments.index("--watcher-url") + 1] = server
    path.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="HTTPS"):
        load_configuration(path, allow_legacy_credentials=True, allow_server_mismatch=True)


def test_a_plain_http_login_elsewhere_read_for_repair_never_signs_in(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path
) -> None:
    profile_setup(credential, config_dir, tmp_path)
    path = personal_config(config_dir)
    rewrite_servers(path, ("auth_profile",), "http://elsewhere.example/api")

    config = load_configuration(path, allow_server_mismatch=True)

    assert names_another_server(config) and config.auth_profile is not None
    with pytest.raises(InsecureLoginURLError):
        config.auth_profile.login_auth()


def test_a_server_that_is_not_a_url_never_matches_the_login(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path
) -> None:
    profile_setup(credential, config_dir, tmp_path)
    path = personal_config(config_dir)
    # Hooks from an earlier version name no server, so only the sign-in can show the rewrite.
    document = json.loads(path.read_text())
    document["watcher_url"] = "not a URL"
    for command in ("hook", "gate"):
        document[command] = without_server(document[command])
    path.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="HTTP or HTTPS"):
        load_configuration(path)
    assert names_another_server(load_configuration(path, allow_server_mismatch=True))


@pytest.mark.parametrize(
    "login",
    [
        pytest.param({"base_url": "not a URL", "kind": "watcher_login"}, id="login-that-is-not-a-url"),
        pytest.param({"base_url": URL, "kind": "unknown"}, id="unknown-credential"),
        pytest.param("not a profile", id="malformed"),
    ],
)
def test_opt_outs_hold_whatever_credential_the_personal_configuration_names(
    confirmed: None,
    home: Path,
    credential: Path,
    config_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    login: JsonValue,
) -> None:
    project = repository(tmp_path / "project")
    profile_setup(credential, config_dir, tmp_path)
    profile_setup(credential, config_dir, tmp_path, "--project", str(project))
    opted = CliRunner().invoke(app, ["opt-out", "--project", str(project), "--config-dir", str(config_dir)])
    assert opted.exit_code == 0, opted.output
    # No reader accepts this credential, so only the scope and opt-outs stay readable.
    document = json.loads(personal_config(config_dir).read_text())
    document["auth_profile"] = login
    personal_config(config_dir).write_text(json.dumps(document))
    with pytest.raises(ValueError):
        load_configuration(personal_config(config_dir), allow_legacy_credentials=True, allow_server_mismatch=True)

    for event, payload in payloads(project).items():
        assert fire(monkeypatch, event, payload, [personal_hook(home), project / HOOK_FILE]) == [], event
    personal = scopes.personal_install(config_dir)
    assert personal is not None and personal.opted_out == [project]


@pytest.mark.parametrize(
    "server", ["http://127.0.0.1:9/api", "https://elsewhere.example/api", "http://elsewhere.example/api"]
)
def test_a_project_install_honors_the_opt_out_when_only_the_personal_server_changed(
    confirmed: None,
    home: Path,
    credential: Path,
    config_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    server: str,
) -> None:
    project = repository(tmp_path / "project")
    profile_setup(credential, config_dir, tmp_path)
    profile_setup(credential, config_dir, tmp_path, "--project", str(project))
    opted = CliRunner().invoke(app, ["opt-out", "--project", str(project), "--config-dir", str(config_dir)])
    assert opted.exit_code == 0, opted.output
    path = personal_config(config_dir)
    rewrite_servers(path, ("watcher_url",), server)
    # The sign-in still names the server setup wrote, so the full configuration no
    # longer validates. The opt-out lookup reads only the scope and opt-outs.
    rewritten = load_configuration(path, allow_server_mismatch=True)
    assert rewritten.auth_profile is not None and rewritten.auth_profile.base_url == URL
    with pytest.raises(ValueError, match="different"):
        load_configuration(path)
    own = configuration_path(project, config_dir)

    assert scopes.skip_reason(own, payloads(project)["preToolUse"]) == "opted_out"
    for event, payload in payloads(project).items():
        assert fire(monkeypatch, event, payload, [project / HOOK_FILE]) == [], event
    assert [item.skip for item in events(own) if item.kind == "skipped"] == ["opted_out"] * 3


@pytest.mark.parametrize("damage", ["corrupt", "missing", "symlink-to-itself"])
def test_an_opt_out_holds_even_when_the_project_install_cannot_read_its_configuration(
    confirmed: None, home: Path, credential: Path, config_dir: Path, tmp_path: Path, damage: str
) -> None:
    project = repository(tmp_path / "project")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    setup(credential, config_dir)
    setup(credential, config_dir, "--project", str(project))
    assert (
        CliRunner().invoke(app, ["opt-out", "--project", str(project), "--config-dir", str(config_dir)]).exit_code == 0
    )
    own = configuration_path(project, config_dir)
    own.unlink()
    if damage == "corrupt":
        own.write_text("{")
    elif damage == "symlink-to-itself":
        own.symlink_to(own)
    [gate] = ProjectHooks.model_validate_json((project / HOOK_FILE).read_text()).hooks["preToolUse"]
    assert isinstance(gate, dict) and isinstance(gate["exec"], str) and isinstance(gate["args"], list)
    command = [gate["exec"], *map(str, gate["args"])]

    def answer(cwd: Path) -> str:
        result = subprocess.run(
            command,
            input=json.dumps(payloads(cwd)["preToolUse"]),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    assert answer(project) == "{}\n"
    assert [item.skip for item in events(own) if item.kind == "skipped"] == ["opted_out"]
    # Where no opt-out applies, the broken configuration still withholds the call.
    assert _JSON_OBJECT.validate_json(answer(elsewhere))["permissionDecision"] == "deny"


@pytest.mark.parametrize("install", ["personal", "project"])
@pytest.mark.parametrize("given", ["relative", "symlink"])
def test_an_opt_out_holds_for_a_relative_or_symlinked_configuration_path(
    confirmed: None,
    home: Path,
    credential: Path,
    config_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    install: str,
    given: str,
) -> None:
    project = repository(tmp_path / "project")
    setup(credential, config_dir)
    setup(credential, config_dir, "--project", str(project))
    assert (
        CliRunner().invoke(app, ["opt-out", "--project", str(project), "--config-dir", str(config_dir)]).exit_code == 0
    )
    config = personal_config(config_dir) if install == "personal" else configuration_path(project, config_dir)
    if given == "relative":
        # As a hook command run from the configuration's own folder with --config config.json.
        monkeypatch.chdir(config.parent)
        argument = config.name
    else:
        link = tmp_path / "linked" / "config.json"
        link.parent.mkdir()
        link.symlink_to(config)
        argument = str(link)

    async def unexpected(
        mode: str, payload: Mapping[str, JsonValue], config: Path | None, *, grade: bool, watcher_url: str | None
    ) -> None:
        pytest.fail("an opted-out callback reached Watcher")

    monkeypatch.setattr(integration, "run_hook", unexpected)
    for command, event in (("enforce", "preToolUse"), ("observe", "agentStop")):
        result = CliRunner().invoke(app, [command, "--config", argument], input=json.dumps(payloads(project)[event]))
        assert result.exit_code == 0 and result.stdout == "{}\n", (command, result.output)
    assert [item.skip for item in events(Path(argument).absolute()) if item.kind == "skipped"] == ["opted_out"] * 2


def test_setup_and_status_warn_when_both_installs_cover_a_project(
    confirmed: None, home: Path, credential: Path, config_dir: Path, tmp_path: Path
) -> None:
    project = repository(tmp_path / "project")
    other = repository(tmp_path / "other")
    trust(home, project, other)
    alone = setup(credential, config_dir, "--project", str(other))
    assert "twice" not in alone.stderr

    personal = setup(credential, config_dir)

    # Personal setup lists the project install it overlaps and how to remove it, and removes nothing.
    assert f"A project install also covers {other}" in personal.stderr
    assert f"remove --project {other}" in personal.stderr
    assert (other / HOOK_FILE).exists()
    both = setup(credential, config_dir, "--project", str(project))
    assert "The personal install also covers this project" in both.stderr
    assert "each tool call twice" in both.stderr

    def status(*scope: str) -> str:
        result = CliRunner().invoke(app, ["status", *scope, "--config-dir", str(config_dir)])
        assert result.exit_code == 0, result.output
        return result.stderr

    overlapping = status()
    assert f"covers {project}" in overlapping and f"covers {other}" in overlapping
    assert "each tool call twice" in status("--project", str(project))

    # An opted-out project runs neither install, so nothing in it is judged twice.
    opted = CliRunner().invoke(app, ["opt-out", "--project", str(other), "--config-dir", str(config_dir)])
    assert opted.exit_code == 0
    assert f"covers {project}" in status() and f"covers {other}" not in status()
    for warnings in (status("--project", str(other)), setup(credential, config_dir, "--project", str(other)).stderr):
        assert "is opted out" in warnings and "twice" not in warnings

    removed = CliRunner().invoke(app, ["remove", "--project", str(project), "--config-dir", str(config_dir)])
    assert removed.exit_code == 0 and status() == ""
    assert CliRunner().invoke(app, ["remove", "--config-dir", str(config_dir)]).exit_code == 0
    assert status("--project", str(other)) == ""


def test_an_opt_out_warns_about_a_project_install_that_runs_another_python(
    confirmed: None, home: Path, credential: Path, config_dir: Path, tmp_path: Path
) -> None:
    # An install set up from another checkout runs that checkout's code, which may
    # predate opt-outs, so status cannot promise the opt-out applies to it.
    project = repository(tmp_path / "project")
    setup(credential, config_dir)
    setup(credential, config_dir, "--project", str(project))
    other = str(tmp_path / "old-checkout" / ".venv" / "bin" / "python")
    own = configuration_path(project, config_dir)
    stored = json.loads(own.read_text())
    stored["hook"]["exec"] = stored["gate"]["exec"] = other
    own.write_text(json.dumps(stored))
    document = json.loads((project / HOOK_FILE).read_text())
    for entries in document["hooks"].values():
        entries[0]["exec"] = other
    (project / HOOK_FILE).write_text(json.dumps(document))

    opted = CliRunner().invoke(app, ["opt-out", "--project", str(project), "--config-dir", str(config_dir)])

    def status(*scope: str) -> str:
        result = CliRunner().invoke(app, ["status", *scope, "--config-dir", str(config_dir)])
        assert result.exit_code == 0, result.output
        return result.stderr

    for warnings in (opted.stderr, status(), status("--project", str(project))):
        assert "may not apply" in warnings and other in warnings and "setup --project" in warnings, warnings
    assert "leave it alone" not in status("--project", str(project))
    setup(credential, config_dir, "--project", str(project))
    for warnings in (status(), status("--project", str(project))):
        assert "may not apply" not in warnings
    assert "which run this version of the sample, leave it alone" in status("--project", str(project))


def test_the_other_python_warning_holds_for_a_project_configuration_its_hooks_refuse(
    confirmed: None, home: Path, credential: Path, config_dir: Path, tmp_path: Path
) -> None:
    project = repository(tmp_path / "project")
    setup(credential, config_dir)
    setup(credential, config_dir, "--project", str(project))
    other = str(tmp_path / "old-checkout" / ".venv" / "bin" / "python")
    own = configuration_path(project, config_dir)
    stored = json.loads(own.read_text())
    stored["hook"]["exec"] = stored["gate"]["exec"] = other
    own.write_text(json.dumps(stored))
    refused_by_hooks(own, "redirected", tmp_path)

    opted = CliRunner().invoke(app, ["opt-out", "--project", str(project), "--config-dir", str(config_dir)])
    status = CliRunner().invoke(app, ["status", "--config-dir", str(config_dir)])

    assert opted.exit_code == 0 and status.exit_code == 0, opted.output + status.output
    for warnings in (opted.stderr, status.stderr):
        assert "may not apply" in warnings and other in warnings, warnings


def test_overlap_warnings_skip_configurations_and_folders_they_cannot_read(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = repository(tmp_path / "project")
    setup(credential, config_dir)
    setup(credential, config_dir, "--project", str(project))
    broken = config_dir / "broken" / "config.json"
    broken.parent.mkdir()
    broken.write_text("{")

    def unreadable(folder: Path) -> Path:
        raise PermissionError(folder)

    # A project whose root cannot be found counts as not opted out, so the overlap is still reported.
    monkeypatch.setattr(scopes, "project_root", unreadable)
    [warning] = scopes.overlap_warnings(load_configuration(personal_config(config_dir)), config_dir)
    assert f"covers {project}" in warning
    assert scopes.stale_install_warnings(config_dir, project) == []


def test_overlap_warnings_name_the_commands_of_the_tool_that_shows_them(
    confirmed: None, home: Path, credential: Path, config_dir: Path, tmp_path: Path
) -> None:
    project = repository(tmp_path / "project")
    setup(credential, config_dir)
    setup(credential, config_dir, "--project", str(project))
    personal = load_configuration(personal_config(config_dir))
    own = load_configuration(configuration_path(project, config_dir))

    def managed(name: str, folder: Path) -> str:
        return f"managed {name} copilot --project {folder}"

    [overlap] = scopes.overlap_warnings(personal, config_dir, command=managed)
    assert f"Run managed remove copilot --project {project} to keep" in overlap
    [covered] = scopes.overlap_warnings(own, config_dir, command=managed)
    assert f"Run managed remove copilot --project {project} to keep" in covered
    assert (
        CliRunner().invoke(app, ["opt-out", "--project", str(project), "--config-dir", str(config_dir)]).exit_code == 0
    )
    [opted] = scopes.overlap_warnings(own, config_dir, command=managed)
    assert f"Run managed opt-in copilot --project {project} to turn it back on" in opted
    stored = json.loads(configuration_path(project, config_dir).read_text())
    stored["hook"]["exec"] = str(tmp_path / "old-checkout" / ".venv" / "bin" / "python")
    configuration_path(project, config_dir).write_text(json.dumps(stored))
    [stale] = scopes.stale_install_warnings(config_dir, project, command=managed)
    assert f"Run managed setup copilot --project {project} with this version" in stale


def _replace_entries(path: Path, change: str) -> None:
    document = json.loads(path.read_text())
    if change == "file-disabled":
        document["disableAllHooks"] = True
    elif change == "nested-extra-entry":
        # Copilot ignores the whole file over this one entry: it nests hooks two levels deep.
        document["hooks"]["sessionStart"] = [{"hooks": [{"hooks": [{"type": "command", "bash": "true"}]}]}]
    path.write_text(json.dumps(document))


def test_status_reports_either_installation(
    confirmed: None, home: Path, credential: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = CliRunner().invoke(app, ["status", "--config-dir", str(config_dir)])
    assert missing.exit_code == 1 and "No configuration" in missing.stderr
    project = repository(tmp_path / "project")
    setup(credential, config_dir)
    setup(credential, config_dir, "--project", str(project))
    assert (
        CliRunner().invoke(app, ["opt-out", "--project", str(tmp_path), "--config-dir", str(config_dir)]).exit_code == 0
    )

    personal = CliRunner().invoke(app, ["status", "--config-dir", str(config_dir)])
    assert personal.exit_code == 0 and "hook file for this installation" not in personal.stderr
    report = json.loads(personal.stdout)
    assert report["scope"] == "personal" and report["hook_file"] == str(personal_hook(home))
    assert report["hooks_installed"] is True and report["opted_out"] == [str(tmp_path.resolve())]
    assert report["last_delivery"] is None

    own = CliRunner().invoke(app, ["status", "--project", str(project), "--config-dir", str(config_dir)])
    assert json.loads(own.stdout)["scope"] == "project"
    assert json.loads(own.stdout)["hook_file"] == str(project / HOOK_FILE)
    by_path = CliRunner().invoke(app, ["status", "--config", str(configuration_path(project, config_dir))])
    assert json.loads(by_path.stdout)["scope"] == "project"
    assert json.loads(own.stdout)["hooks_installed"] is True and "hook file for this installation" not in own.stderr
    # One extra entry Copilot rejects makes it ignore the whole file, so the hooks are not intact.
    _replace_entries(project / HOOK_FILE, "nested-extra-entry")
    rejected = CliRunner().invoke(app, ["status", "--project", str(project), "--config-dir", str(config_dir)])
    assert json.loads(rejected.stdout)["hooks_installed"] is False
    assert "other entries" in rejected.stderr

    _replace_entries(personal_hook(home), "file-disabled")
    changed = CliRunner().invoke(app, ["status", "--config-dir", str(config_dir)])
    assert json.loads(changed.stdout)["hooks_installed"] is False and "run setup again" in changed.stderr
    personal_hook(home).unlink()
    personal_hook(home).symlink_to(tmp_path / "elsewhere.json")
    redirected = CliRunner().invoke(app, ["status", "--config-dir", str(config_dir)])
    assert json.loads(redirected.stdout)["hooks_installed"] is False


@pytest.mark.parametrize("installed", ["bound", "unbound", "redirected"])
def test_status_checks_which_server_the_personal_hook_file_names(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path, installed: str
) -> None:
    setup(credential, config_dir)
    hook = personal_hook(home)
    document = json.loads(hook.read_text())
    if installed == "unbound":
        # An upgrade that stopped after writing the configuration left an earlier gate that names no server.
        document["hooks"]["preToolUse"] = [without_server(document["hooks"]["preToolUse"][0])]
        hook.write_text(json.dumps(document))
    elif installed == "redirected":
        target = tmp_path / "elsewhere.json"
        target.write_text(json.dumps(document))
        hook.unlink()
        hook.symlink_to(target)

    result = CliRunner().invoke(app, ["status", "--config-dir", str(config_dir)])

    assert result.exit_code == 0, result.output
    assert ("do not name their Watcher server" in result.stderr) == (installed == "unbound")
    assert (f"could not read {hook}" in result.stderr) == (installed == "redirected")


# What Copilot 1.0.91's own hook loader does with each top-level version, in both
# hook folders. Python counts True as 1, so a loose comparison accepts JSON true.
@pytest.mark.parametrize(
    "version,loaded",
    [
        (None, True),
        ("1", True),
        ("1.0", True),
        ("1e0", True),
        ("true", False),
        ("false", False),
        ('"1"', False),
        ("null", False),
        ("2", False),
    ],
)
def test_a_hook_file_counts_as_installed_only_with_a_version_copilot_accepts(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path, version: str | None, loaded: bool
) -> None:
    project = repository(tmp_path / "project")
    setup(credential, config_dir)
    setup(credential, config_dir, "--project", str(project))
    prefix = "" if version is None else f'"version": {version}, '

    for hook, scope in ((personal_hook(home), []), (project / HOOK_FILE, ["--project", str(project)])):
        hooks = json.dumps(json.loads(hook.read_text())["hooks"])
        hook.write_text("{" + prefix + '"hooks": ' + hooks + "}")
        assert copilot_loads(hook) is loaded

        status = CliRunner().invoke(app, ["status", *scope, "--config-dir", str(config_dir)])
        assert json.loads(status.stdout)["hooks_installed"] is loaded, hook
        assert ("hook file for this installation" in status.stderr) is not loaded
        # Setup leaves a file Copilot rejects for the user to correct, as it does an edited entry.
        setup(credential, config_dir, *scope, succeeds=loaded)


@pytest.mark.parametrize(
    "settings",
    [
        ".github/copilot/settings.json",
        ".github/copilot/settings.local.json",
        ".claude/settings.json",
        ".claude/settings.local.json",
    ],
)
def test_project_setup_warns_when_any_repository_settings_file_disables_all_hooks(
    home: Path, credential: Path, config_dir: Path, tmp_path: Path, settings: str
) -> None:
    project = repository(tmp_path / "project")
    trust(home, project)
    (project / settings).parent.mkdir(parents=True)
    (project / settings).write_text('{"disableAllHooks": true}')

    result = setup(credential, config_dir, "--project", str(project))

    assert "This project's Copilot or Claude Code settings set disableAllHooks, so no hook will run" in result.stderr
    assert "user settings" not in result.stderr


@pytest.mark.parametrize(
    "fields,message",
    [
        ({}, "either a project"),
        ({"project": "/project", "copilot_home": "/home/copilot"}, "either a project"),
        ({"copilot_home": "relative"}, "absolute"),
        ({"project": "/project", "opted_out": ["/project"]}, "Only the personal install"),
    ],
)
@pytest.mark.parametrize("model", [ObserverConfiguration, InstallationScope])
def test_a_configuration_names_exactly_one_installation(
    fields: dict[str, JsonValue], message: str, model: type[InstallationScope]
) -> None:
    document: dict[str, JsonValue] = {
        "watcher_url": "https://watcher.test/api",
        "watcher_auth": True,
        "watcher_state_dir": "/login",
        "hook": {"exec": "/python", "args": []},
    }
    with pytest.raises(ValueError, match=message):
        model.model_validate(document | fields)


def test_removal_finishes_when_the_personal_hook_file_is_already_gone(
    confirmed: None, home: Path, credential: Path, config_dir: Path
) -> None:
    missing = CliRunner().invoke(app, ["opt-in", "--project", str(home.parent), "--config-dir", str(config_dir)])
    assert missing.exit_code == 1 and "Opt-in failed" in missing.stderr
    setup(credential, config_dir)
    personal_hook(home).unlink()
    removed = CliRunner().invoke(app, ["remove", "--config-dir", str(config_dir)])
    assert removed.exit_code == 0 and not personal_config(config_dir).exists()


def test_folders_that_cannot_be_resolved_are_recorded_and_judged(
    confirmed: None, home: Path, credential: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = repository(tmp_path / "project")
    setup(credential, config_dir)
    setup(credential, config_dir, "--project", str(project))
    assert (
        CliRunner().invoke(app, ["opt-out", "--project", str(project), "--config-dir", str(config_dir)]).exit_code == 0
    )
    hook_files = [personal_hook(home), project / HOOK_FILE]
    both = [str(personal_config(config_dir)), str(configuration_path(project, config_dir))]
    loop = tmp_path / "loop"
    loop.symlink_to(loop)
    # Python 3.12 raises RuntimeError on a symlink loop; later releases leave it unresolved.
    assert fire(monkeypatch, "preToolUse", payloads(loop)["preToolUse"], hook_files) == both

    def unreadable(folder: Path) -> Path:
        raise PermissionError(folder)

    monkeypatch.setattr(scopes, "project_root", unreadable)
    assert fire(monkeypatch, "preToolUse", payloads(project)["preToolUse"], hook_files) == both

    # A configuration path that cannot be resolved still finds the opt-out through its folders.
    monkeypatch.setattr(scopes, "project_root", project_root)
    config = configuration_path(project, config_dir)
    resolve = Path.resolve

    def unresolvable(path: Path, strict: bool = False) -> Path:
        if path == config:
            raise RuntimeError(path)
        return resolve(path, strict)

    monkeypatch.setattr(Path, "resolve", unresolvable)
    assert scopes.skip_reason(config, payloads(project)["preToolUse"]) == "opted_out"
    # Without a working folder, a relative path names no configuration root at all.
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    assert scopes.skip_reason(Path("config.json"), payloads(project)["preToolUse"]) is None
