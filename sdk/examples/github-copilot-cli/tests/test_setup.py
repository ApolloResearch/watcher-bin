"""Verify project hook ownership, credential isolation and installation failures."""

import json
import stat
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import JsonValue
from readback_fixture import save_watcher_login
from typer.testing import CliRunner
from watcher_github_copilot_cli import configuration
from watcher_github_copilot_cli.cli import app
from watcher_github_copilot_cli.configuration import (
    HOOK_FILE,
    ProjectHooks,
    configuration_path,
    hooks_without_server,
    install_observer,
    load_configuration,
)
from watcher_github_copilot_cli.diagnostics import read_status

# The configuration path the demo hooks ask users to replace with the one setup prints.
DEMO_CONFIG = "/path/printed/by/setup/config.json"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    path = tmp_path / "project with spaces"
    path.mkdir()
    return path


URL = "http://localhost:8765/api"


@pytest.fixture
def credential(tmp_path: Path) -> Path:
    """A saved Watcher sign-in store for ``URL``, outside the project."""
    state = tmp_path / "watcher"
    save_watcher_login(state, URL, "PRIVATE_TEST_CREDENTIAL")
    return state


def login_file(credential: Path) -> Path:
    return next((credential / "credentials").glob("*.json"))


def setup_arguments(project: Path, credential: Path, config_dir: Path) -> list[str]:
    return [
        "setup",
        "--project",
        str(project),
        "--watcher-url",
        URL,
        "--watcher-auth",
        "--watcher-state-dir",
        str(credential),
        "--config-dir",
        str(config_dir),
    ]


def test_watcher_state_dir_requires_watcher_auth(project: Path, credential: Path, tmp_path: Path) -> None:
    arguments = setup_arguments(project, credential, tmp_path / "configuration")
    arguments.remove("--watcher-auth")
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 2
    assert "--watcher-state-dir requires --watcher-auth" in result.output
    with pytest.raises(ValueError, match="requires --watcher-auth"):
        install_observer(project, URL, tmp_path / "configuration", watcher_state_dir=credential)
    assert not (project / HOOK_FILE).exists()


@pytest.mark.parametrize("option", ["--api-key-file", "--api-key-env"])
def test_setup_no_longer_offers_api_keys(project: Path, credential: Path, tmp_path: Path, option: str) -> None:
    arguments = setup_arguments(project, credential, tmp_path / "configuration")
    result = CliRunner().invoke(app, [*arguments, option, "PRIVATE_TEST_CREDENTIAL"])
    assert result.exit_code == 2
    assert not (project / HOOK_FILE).exists()


def test_repeated_setup_keeps_one_observer_and_unrelated_hooks(project: Path, credential: Path, tmp_path: Path) -> None:
    unrelated = project / ".github/hooks/existing.json"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text('{"version":1,"hooks":{"preToolUse":[{"bash":"echo existing"}]}}\n')
    before = unrelated.read_bytes()
    config_dir = tmp_path / "configuration"
    arguments = setup_arguments(project, credential, config_dir)

    first = CliRunner().invoke(app, arguments)
    assert first.exit_code == 0, first.output
    hook_before = (project / HOOK_FILE).read_bytes()
    second = CliRunner().invoke(app, arguments)

    assert second.exit_code == 0, second.output
    assert (project / HOOK_FILE).read_bytes() == hook_before
    assert unrelated.read_bytes() == before
    installed = ProjectHooks.model_validate_json(hook_before)
    assert set(installed.hooks) == {"agentStop", "sessionEnd", "preToolUse"}
    assert installed.hooks["agentStop"] == installed.hooks["sessionEnd"]
    assert len(installed.hooks["agentStop"]) == 1
    config = load_configuration(configuration_path(project, config_dir))
    assert config.watcher_auth and config.watcher_state_dir == credential.resolve()
    assert config.api_key_file is None and config.api_key_env is None
    assert config.hook.args[:4] == ["-I", "-m", "watcher_github_copilot_cli.cli", "observe"]
    assert config.hook.args[-1] == "--record-only"
    assert Path(config.hook.exec).is_absolute()
    assert "PRIVATE_TEST_CREDENTIAL" not in first.output + second.output + hook_before.decode()
    assert "PRIVATE_TEST_CREDENTIAL" not in configuration_path(project, config_dir).read_text()
    assert stat.S_IMODE(configuration_path(project, config_dir).stat().st_mode) == 0o600


def test_setup_refuses_an_existing_unowned_hook(project: Path, credential: Path, tmp_path: Path) -> None:
    hook = project / HOOK_FILE
    hook.parent.mkdir(parents=True)
    hook.write_text('{"version":1,"hooks":{"agentStop":[{"bash":"echo mine"}]}}\n')
    before = hook.read_bytes()

    result = CliRunner().invoke(app, setup_arguments(project, credential, tmp_path / "configuration"))

    assert result.exit_code == 1
    assert "Setup failed" in result.stderr
    assert hook.read_bytes() == before


def test_setup_preserves_an_unowned_dangling_symlink(project: Path, credential: Path, tmp_path: Path) -> None:
    hook = project / HOOK_FILE
    hook.parent.mkdir(parents=True)
    hook.symlink_to(project / "missing-hook.json")

    result = CliRunner().invoke(app, setup_arguments(project, credential, tmp_path / "configuration"))

    assert result.exit_code == 1
    assert "Setup failed" in result.stderr
    assert hook.is_symlink()
    assert hook.readlink() == project / "missing-hook.json"


@pytest.mark.parametrize("parent", [".github", ".github/hooks"])
def test_setup_refuses_a_parent_symlink_outside_the_project(
    project: Path, credential: Path, tmp_path: Path, parent: str
) -> None:
    outside = tmp_path / "unrelated"
    outside.mkdir()
    redirect = project / parent
    redirect.parent.mkdir(parents=True, exist_ok=True)
    redirect.symlink_to(outside, target_is_directory=True)

    result = CliRunner().invoke(app, setup_arguments(project, credential, tmp_path / "configuration"))

    assert result.exit_code == 1
    assert "Setup failed" in result.stderr
    assert list(outside.iterdir()) == []
    assert redirect.is_symlink()


def test_removal_refuses_a_hook_redirected_outside_the_project(project: Path, credential: Path, tmp_path: Path) -> None:
    config_dir = tmp_path / "configuration"
    result = CliRunner().invoke(app, setup_arguments(project, credential, config_dir))
    assert result.exit_code == 0, result.output
    directory = project / HOOK_FILE.parent
    outside = tmp_path / "moved-hooks"
    directory.rename(outside)
    directory.symlink_to(outside, target_is_directory=True)
    before = (outside / HOOK_FILE.name).read_bytes()

    result = CliRunner().invoke(app, ["remove", "--project", str(project), "--config-dir", str(config_dir)])

    assert result.exit_code == 1
    assert "Removal failed" in result.stderr
    assert (outside / HOOK_FILE.name).read_bytes() == before
    assert configuration_path(project, config_dir).exists()


def test_removal_preserves_entries_added_to_the_owned_file(project: Path, credential: Path, tmp_path: Path) -> None:
    config_dir = tmp_path / "configuration"
    result = CliRunner().invoke(app, setup_arguments(project, credential, config_dir))
    assert result.exit_code == 0, result.output
    hook = project / HOOK_FILE
    document = ProjectHooks.model_validate_json(hook.read_text())
    document.hooks["agentStop"].append({"type": "command", "bash": "echo retained"})
    document.hooks["preToolUse"] = [{"type": "command", "bash": "echo permissions"}]
    hook.write_text(document.model_dump_json())

    removed = CliRunner().invoke(app, ["remove", "--project", str(project), "--config-dir", str(config_dir)])

    assert removed.exit_code == 0, removed.output
    assert ProjectHooks.model_validate_json(hook.read_text()).hooks == {
        "agentStop": [{"type": "command", "bash": "echo retained"}],
        "preToolUse": [{"type": "command", "bash": "echo permissions"}],
    }
    assert "PRIVATE_TEST_CREDENTIAL" in login_file(credential).read_text()
    assert not configuration_path(project, config_dir).exists()


def test_removal_keeps_a_hook_file_replaced_by_someone_else(project: Path, credential: Path, tmp_path: Path) -> None:
    config_dir = tmp_path / "configuration"
    result = CliRunner().invoke(app, setup_arguments(project, credential, config_dir))
    assert result.exit_code == 0, result.output
    hook = project / HOOK_FILE
    hook.write_text('{"version":1,"hooks":{"agentStop":[{"bash":"echo replaced"}]}}\n')

    result = CliRunner().invoke(app, ["remove", "--project", str(project), "--config-dir", str(config_dir)])

    assert result.exit_code == 0
    assert ProjectHooks.model_validate_json(hook.read_text()).hooks == {"agentStop": [{"bash": "echo replaced"}]}
    assert not configuration_path(project, config_dir).exists()


@pytest.mark.parametrize("edit", ["timeout", "argument-syntax"])
@pytest.mark.parametrize("command", ["setup", "remove"])
def test_a_changed_entry_of_this_integration_is_refused(
    project: Path, credential: Path, tmp_path: Path, command: str, edit: str
) -> None:
    config_dir = tmp_path / "configuration"
    arguments = setup_arguments(project, credential, config_dir)
    assert CliRunner().invoke(app, [*arguments, "--enforce"]).exit_code == 0
    hook = project / HOOK_FILE
    document = json.loads(hook.read_text())
    gate = document["hooks"]["preToolUse"][0]
    if edit == "timeout":
        gate["timeoutSec"] = 600
    else:
        gate["args"] = [*gate["args"][:-2], "--config=" + gate["args"][-1]]
    hook.write_text(json.dumps(document))
    before = hook.read_bytes()
    invocation = (
        arguments if command == "setup" else ["remove", "--project", str(project), "--config-dir", str(config_dir)]
    )
    result = CliRunner().invoke(app, invocation)
    assert result.exit_code == 1
    assert hook.read_bytes() == before and configuration_path(project, config_dir).exists()


def test_removal_is_repeatable(project: Path, credential: Path, tmp_path: Path) -> None:
    config_dir = tmp_path / "configuration"
    result = CliRunner().invoke(app, setup_arguments(project, credential, config_dir))
    assert result.exit_code == 0, result.output
    arguments = ["remove", "--project", str(project), "--config-dir", str(config_dir)]

    assert CliRunner().invoke(app, arguments).exit_code == 0
    result = CliRunner().invoke(app, arguments)

    assert result.exit_code == 0
    assert "No installation found" in result.stdout
    assert not (project / HOOK_FILE).exists()


@pytest.mark.parametrize(
    "fault", ["missing-key", "blank-key", "project-key", "project-config", "url-credential", "plain-http"]
)
def test_invalid_configuration_never_installs_a_hook(
    project: Path, credential: Path, tmp_path: Path, fault: str
) -> None:
    config_dir = tmp_path / "configuration"
    if fault == "missing-key":
        login_file(credential).unlink()
    elif fault == "blank-key":
        login_file(credential).write_text("\n")
    elif fault == "project-key":
        credential = project / "watcher"
        save_watcher_login(credential, URL, "PRIVATE_TEST_CREDENTIAL")
    elif fault == "project-config":
        config_dir = project / "configuration"
    arguments = setup_arguments(project, credential, config_dir)
    if fault == "url-credential":
        arguments[arguments.index("--watcher-url") + 1] = "http://PRIVATE_TEST_CREDENTIAL@localhost:8765/api"
    if fault == "plain-http":
        # The key, transcripts and gate answers would cross the network in cleartext.
        arguments[arguments.index("--watcher-url") + 1] = "http://watcher.example.com/api"

    result = CliRunner().invoke(app, arguments)

    assert result.exit_code == 1
    assert "Setup failed" in result.stderr or "run setup again" in result.stderr
    assert "PRIVATE_TEST_CREDENTIAL" not in result.output
    assert not (project / HOOK_FILE).exists()


# A server on this machine that a same-user process could run to answer every gate request with an allow.
STUB = "http://127.0.0.1:9/api"


def test_each_installed_hook_names_the_server_setup_configured(project: Path, credential: Path, tmp_path: Path) -> None:
    config_dir = tmp_path / "configuration"
    assert CliRunner().invoke(app, [*setup_arguments(project, credential, config_dir), "--enforce"]).exit_code == 0
    installed = ProjectHooks.model_validate_json((project / HOOK_FILE).read_text())
    assert set(installed.hooks) == {"agentStop", "sessionEnd", "preToolUse"}
    for entries in installed.hooks.values():
        [entry] = entries
        assert isinstance(entry, dict) and isinstance(entry["args"], list)
        assert entry["args"][entry["args"].index("--watcher-url") + 1] == URL
    path = configuration_path(project, config_dir)
    document = json.loads(path.read_text())
    document["watcher_url"] = STUB
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="different Watcher server"):
        load_configuration(path)
    with pytest.raises(ValueError, match="different Watcher server"):
        load_configuration(path, allow_legacy_credentials=True)
    # Setup and removal still read it, so either repairs the installation.
    assert CliRunner().invoke(app, setup_arguments(project, credential, config_dir)).exit_code == 0
    assert load_configuration(path).watcher_url == URL
    path.write_text(json.dumps(document))
    removed = CliRunner().invoke(app, ["remove", "--project", str(project), "--config-dir", str(config_dir)])
    assert removed.exit_code == 0 and not (project / HOOK_FILE).exists() and not path.exists()


def test_hooks_refuse_a_configuration_redirected_to_another_server(
    project: Path, credential: Path, tmp_path: Path
) -> None:
    config_dir = tmp_path / "configuration"
    assert CliRunner().invoke(app, [*setup_arguments(project, credential, config_dir), "--enforce"]).exit_code == 0
    path = configuration_path(project, config_dir)
    # Rewrite only the private configuration, consistently, with a sign-in store
    # for the stub; the project hook file stays exactly as setup wrote it.
    stub_login = tmp_path / "stub-login"
    save_watcher_login(stub_login, STUB)
    document = json.loads(path.read_text())
    document["watcher_url"] = STUB
    document["watcher_state_dir"] = str(stub_login)
    for command in ("hook", "gate"):
        arguments = document[command]["args"]
        arguments[arguments.index("--watcher-url") + 1] = STUB
    path.write_text(json.dumps(document))
    assert load_configuration(path).watcher_url == STUB
    installed = ProjectHooks.model_validate_json((project / HOOK_FILE).read_text())
    outcomes = {}
    for event, entries in installed.hooks.items():
        [entry] = entries
        assert isinstance(entry, dict) and isinstance(entry["exec"], str) and isinstance(entry["args"], list)
        payload = {"toolName": "bash", "toolArgs": {"command": "ls"}} if event == "preToolUse" else {}
        outcomes[event] = subprocess.run(
            [entry["exec"], *(str(argument) for argument in entry["args"])],
            input=json.dumps({"sessionId": str(uuid4()), "cwd": str(project), **payload}),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    gate = outcomes.pop("preToolUse")
    assert json.loads(gate.stdout) == {
        "permissionDecision": "deny",
        "permissionDecisionReason": "The hook and its private configuration name different Watcher servers; "
        "run setup again",
    }
    for observer in outcomes.values():
        assert observer.returncode == 2 and "different Watcher servers" in observer.stderr
    error = read_status(path).last_error
    assert error is not None and error.failure == "configuration"


def test_status_asks_to_rerun_setup_for_hooks_that_name_no_server(
    project: Path, credential: Path, tmp_path: Path
) -> None:
    config_dir = tmp_path / "configuration"
    arguments = [*setup_arguments(project, credential, config_dir), "--enforce"]
    assert CliRunner().invoke(app, arguments).exit_code == 0
    path = configuration_path(project, config_dir)
    current = CliRunner().invoke(app, ["status", "--config", str(path)])
    assert current.exit_code == 0 and current.stderr == ""
    # An earlier version installed the same hooks without naming the server, so
    # they cannot notice a configuration redirected to another one.
    earlier = json.loads(path.read_text())
    for command in ("hook", "gate"):
        named = earlier[command]["args"].index("--watcher-url")
        del earlier[command]["args"][named : named + 2]
    path.write_text(json.dumps(earlier))
    hooks = {"agentStop": [earlier["hook"]], "sessionEnd": [earlier["hook"]], "preToolUse": [earlier["gate"]]}
    (project / HOOK_FILE).write_text(json.dumps({"version": 1, "hooks": hooks}))
    warned = CliRunner().invoke(app, ["status", "--config", str(path)])
    assert warned.exit_code == 0
    assert json.loads(warned.stdout) == json.loads(current.stdout)
    assert "do not name their Watcher server" in warned.stderr and "run setup again" in warned.stderr.lower()
    assert CliRunner().invoke(app, arguments).exit_code == 0
    repaired = CliRunner().invoke(app, ["status", "--config", str(path)])
    assert repaired.exit_code == 0 and repaired.stderr == ""


def without_server(entry: dict[str, JsonValue]) -> dict[str, JsonValue]:
    arguments = entry["args"]
    assert isinstance(arguments, list)
    named = arguments.index("--watcher-url")
    return {**entry, "args": arguments[:named] + arguments[named + 2 :]}


@pytest.mark.parametrize("installed", ["interrupted_upgrade", "one_entry", "unrelated_entry", "unreadable"])
def test_status_checks_the_hook_entries_copilot_runs(
    project: Path, credential: Path, tmp_path: Path, installed: str
) -> None:
    config_dir = tmp_path / "configuration"
    assert CliRunner().invoke(app, [*setup_arguments(project, credential, config_dir), "--enforce"]).exit_code == 0
    path = configuration_path(project, config_dir)
    hook_file = project / HOOK_FILE
    document = json.loads(hook_file.read_text())
    hooks: dict[str, list[dict[str, JsonValue]]] = document["hooks"]
    if installed == "interrupted_upgrade":
        # Upgrading setup wrote the new configuration, then stopped before rewriting the hook file.
        document["hooks"] = {event: [without_server(entry) for entry in entries] for event, entries in hooks.items()}
    elif installed == "one_entry":
        hooks["preToolUse"] = [without_server(hooks["preToolUse"][0])]
    else:
        hooks["agentStop"].append({"type": "command", "exec": "/usr/local/bin/other-integration", "args": []})
    hook_file.write_text("{not json" if installed == "unreadable" else json.dumps(document))
    result = CliRunner().invoke(app, ["status", "--config", str(path)])
    assert result.exit_code == 0 and set(json.loads(result.stdout)) == {
        "scope",
        "hook_file",
        "hooks_installed",
        "opted_out",
        "last_callback",
        "last_delivery",
        "last_session",
        "last_error",
        "last_review_check",
        "last_review_gap",
    }
    unbound = "do not name their Watcher server" in result.stderr
    assert unbound == (installed in {"interrupted_upgrade", "one_entry"})
    assert ("could not read" in result.stderr) == (installed == "unreadable")


def test_installed_commands_run_as_written_from_an_unrelated_directory(
    project: Path, credential: Path, tmp_path: Path
) -> None:
    config_dir = tmp_path / "configuration"
    assert CliRunner().invoke(app, [*setup_arguments(project, credential, config_dir), "--enforce"]).exit_code == 0
    installed = ProjectHooks.model_validate_json((project / HOOK_FILE).read_text())
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    outcomes = {}
    for event, entries in installed.hooks.items():
        [entry] = entries
        assert isinstance(entry, dict) and isinstance(entry["exec"], str) and isinstance(entry["args"], list)
        command = [entry["exec"], *(str(argument) for argument in entry["args"])]
        outcomes[event] = subprocess.run(
            command, cwd=elsewhere, input="PRIVATE_BAD_JSON", capture_output=True, text=True, timeout=60, check=False
        )
    gate = outcomes.pop("preToolUse")
    assert gate.returncode == 0 and json.loads(gate.stdout)["permissionDecision"] == "deny"
    for observer in outcomes.values():
        assert observer.returncode == 2 and json.loads(observer.stdout) == {}
        assert "recording" in observer.stderr
    assert all("PRIVATE" not in result.stdout + result.stderr for result in [gate, *outcomes.values()])
    assert list(elsewhere.iterdir()) == []


def test_demo_hooks_run_the_same_commands_as_setup(project: Path, credential: Path, tmp_path: Path) -> None:
    config_dir = tmp_path / "configuration"
    assert CliRunner().invoke(app, [*setup_arguments(project, credential, config_dir), "--enforce"]).exit_code == 0
    installed = load_configuration(configuration_path(project, config_dir))
    assert installed.gate is not None
    # Setup's commands, with the demos' placeholder for the configuration path setup
    # prints, and without the server setup names, which the demos leave out.
    installed_path = str(configuration_path(project, config_dir))

    def as_demo(arguments: list[str]) -> list[str]:
        words = [DEMO_CONFIG if argument == installed_path else argument for argument in arguments[3:]]
        server = words.index("--watcher-url")
        assert words[server + 1] == URL
        return words[:server] + words[server + 2 :]

    observer = as_demo(installed.hook.args)
    gate = as_demo(installed.gate.args)
    # The source tree keeps demo/ beside tests/; the container recipe copies it beside the tests.
    demo = next(path for path in (Path(__file__).parents[1] / "demo", Path(__file__).parent / "demo") if path.is_dir())
    expectations = {
        "hooks.observe.json": {
            "agentStop": ["observe", "--config", DEMO_CONFIG],
            "sessionEnd": ["observe", "--config", DEMO_CONFIG],
        },
        "hooks.enforce.json": {"agentStop": observer, "sessionEnd": observer, "preToolUse": gate},
    }
    for name, expected in expectations.items():
        hooks = ProjectHooks.model_validate_json((demo / name).read_text()).hooks
        assert set(hooks) == set(expected)
        for event, entries in hooks.items():
            [entry] = entries
            assert isinstance(entry, dict) and isinstance(entry["bash"], str) and isinstance(entry["timeoutSec"], int)
            assert entry["bash"].split() == ["watcher-github-copilot-cli", *expected[event]]
            minimum = installed.gate.timeoutSec if event == "preToolUse" else installed.hook.timeoutSec
            assert entry["timeoutSec"] >= minimum
    assert observer == ["observe", "--config", DEMO_CONFIG, "--record-only"]
    assert gate == ["enforce", "--config", DEMO_CONFIG]


def test_setup_preserves_the_gate_and_record_only_removes_it(project: Path, credential: Path, tmp_path: Path) -> None:
    config_dir = tmp_path / "configuration"
    arguments = setup_arguments(project, credential, config_dir)
    assert CliRunner().invoke(app, [*arguments, "--enforce"]).exit_code == 0
    assert CliRunner().invoke(app, [*arguments, "--enforce"]).exit_code == 0
    installed = ProjectHooks.model_validate_json((project / HOOK_FILE).read_text())
    [gate] = installed.hooks["preToolUse"]
    assert isinstance(gate, dict) and gate["timeoutSec"] == 480
    args = gate["args"]
    assert isinstance(args, list)
    assert args[2:] == [
        "watcher_github_copilot_cli.cli",
        "enforce",
        "--config",
        str(configuration_path(project, config_dir)),
        "--watcher-url",
        URL,
    ]

    assert CliRunner().invoke(app, arguments).exit_code == 0
    assert "preToolUse" in ProjectHooks.model_validate_json((project / HOOK_FILE).read_text()).hooks
    assert CliRunner().invoke(app, [*arguments, "--record-only"]).exit_code == 0
    assert CliRunner().invoke(app, arguments).exit_code == 0
    assert set(ProjectHooks.model_validate_json((project / HOOK_FILE).read_text()).hooks) == {"agentStop", "sessionEnd"}


def test_an_install_from_an_earlier_version_is_upgraded_and_removable(
    project: Path, credential: Path, tmp_path: Path
) -> None:
    config_dir = tmp_path / "configuration"
    arguments = setup_arguments(project, credential, config_dir)
    assert CliRunner().invoke(app, arguments).exit_code == 0
    # An earlier version installed only agentStop, running a `callback` command.
    path = configuration_path(project, config_dir)
    old = json.loads(path.read_text())
    old["gate"] = None
    old["hook"]["args"] = [*old["hook"]["args"][:3], "callback", "--config", str(path)]
    path.write_text(json.dumps(old))
    (project / HOOK_FILE).write_text(json.dumps({"version": 1, "hooks": {"agentStop": [old["hook"]]}}))
    assert CliRunner().invoke(app, arguments).exit_code == 0
    upgraded = ProjectHooks.model_validate_json((project / HOOK_FILE).read_text())
    assert set(upgraded.hooks) == {"agentStop", "sessionEnd"}
    assert all(json.dumps(entries).count("--record-only") == 1 for entries in upgraded.hooks.values())
    removed = CliRunner().invoke(app, ["remove", "--project", str(project), "--config-dir", str(config_dir)])
    assert removed.exit_code == 0 and not (project / HOOK_FILE).exists()


def test_removal_takes_every_owned_entry_including_the_gate(project: Path, credential: Path, tmp_path: Path) -> None:
    config_dir = tmp_path / "configuration"
    assert CliRunner().invoke(app, [*setup_arguments(project, credential, config_dir), "--enforce"]).exit_code == 0
    removed = CliRunner().invoke(app, ["remove", "--project", str(project), "--config-dir", str(config_dir)])
    assert removed.exit_code == 0 and not (project / HOOK_FILE).exists()


def git(*arguments: str | Path) -> str:
    return subprocess.run(["git", *map(str, arguments)], capture_output=True, text=True, check=True).stdout


def test_the_hook_file_is_kept_out_of_commits(project: Path, credential: Path, tmp_path: Path) -> None:
    git("init", "-q", project)
    exclude = project / ".git/info/exclude"
    exclude.write_text("# local ignores\n/.github/hooks/watcher-sdk-copilot.json\n")
    config_dir = tmp_path / "configuration"
    arguments = setup_arguments(project, credential, config_dir)
    assert CliRunner().invoke(app, arguments).exit_code == 0
    assert exclude.read_text() == "# local ignores\n/.github/hooks/watcher-sdk-copilot.json\n"
    assert git("-C", project, "status", "--porcelain", "--untracked-files=all") == ""
    removed = CliRunner().invoke(app, ["remove", "--project", str(project), "--config-dir", str(config_dir)])
    assert removed.exit_code == 0
    assert "/.github/hooks/watcher-sdk-copilot.json" in exclude.read_text()


@pytest.mark.parametrize("layout", ["worktree", "subfolder"])
def test_the_hook_file_is_excluded_in_worktrees_and_subfolders(credential: Path, tmp_path: Path, layout: str) -> None:
    repository = tmp_path / "repository"
    git("init", "-q", repository)
    git(
        "-C",
        repository,
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
    if layout == "worktree":
        project = tmp_path / "linked"
        git("-C", repository, "worktree", "add", "-q", project)
    else:
        project = repository / "service"
        project.mkdir()
    assert CliRunner().invoke(app, setup_arguments(project, credential, tmp_path / "configuration")).exit_code == 0
    assert git("-C", project, "status", "--porcelain", "--untracked-files=all") == ""


def test_setup_warns_about_settings_that_stop_hooks_from_loading(
    project: Path, credential: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "copilot-home"
    home.mkdir()
    monkeypatch.setenv("COPILOT_HOME", str(home))
    monkeypatch.setattr(configuration, "MANAGED_SETTINGS", tmp_path / "managed-settings.json")
    (project / ".github/copilot").mkdir(parents=True)
    (project / ".github/copilot/settings.json").write_text('{"disableAllHooks": true}')
    (project / ".claude").mkdir()
    (project / ".claude/settings.json").write_text('{"hooks": {"Stop": []}}')
    result = CliRunner().invoke(app, setup_arguments(project, credential, tmp_path / "configuration"))
    assert result.exit_code == 0
    for text in ("Trust this folder", "disableAllHooks", "outside a Git repository", "Claude Code hooks"):
        assert text in result.stderr

    # Copilot's own config.json starts with comment lines.
    (home / "config.json").write_text(
        "// Disposable cache, safe to delete.\n" + json.dumps({"trustedFolders": [str(project.parent)]})
    )
    git("init", "-q", project)
    (project / ".github/copilot/settings.json").write_text('{"disableAllHooks": false}')
    (project / ".claude/settings.json").write_text("{}")
    result = CliRunner().invoke(app, setup_arguments(project, credential, tmp_path / "configuration"))
    assert result.exit_code == 0 and "Warning" not in result.stderr


def test_user_settings_that_disable_hooks_are_reported(
    project: Path, credential: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "copilot-home"
    home.mkdir()
    monkeypatch.setenv("COPILOT_HOME", str(home))
    (home / "settings.json").write_text('// user settings\n{"disableAllHooks": true, "disabledHooks": ["abc"]}')
    result = CliRunner().invoke(app, setup_arguments(project, credential, tmp_path / "configuration"))
    assert result.exit_code == 0
    assert "disableAllHooks" in result.stderr and "disabledHooks" in result.stderr
    assert "Copilot's user settings set disableAllHooks" in result.stderr
    assert "no hook will run" not in result.stderr


def test_unreadable_settings_are_reported_and_git_failures_warn(
    project: Path, credential: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "copilot-home"
    home.mkdir()
    monkeypatch.setenv("COPILOT_HOME", str(home))
    (home / "settings.json").write_text('{"disableAllHooks": true, /* inline */}')
    (project / ".git").mkdir()
    result = CliRunner().invoke(app, setup_arguments(project, credential, tmp_path / "configuration"))
    assert result.exit_code == 0
    assert f"could not read {home / 'settings.json'}" in result.stderr
    assert "local exclude file" in result.stderr


def test_glob_characters_in_the_project_path_are_escaped(credential: Path, tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    git("init", "-q", repository)
    project = repository / "a[b]*"
    project.mkdir()
    assert CliRunner().invoke(app, setup_arguments(project, credential, tmp_path / "configuration")).exit_code == 0
    assert git("-C", repository, "status", "--porcelain", "--untracked-files=all") == ""


def test_setup_recovers_when_an_earlier_run_stopped_between_its_two_writes(
    project: Path, credential: Path, tmp_path: Path
) -> None:
    config_dir = tmp_path / "configuration"
    arguments = setup_arguments(project, credential, config_dir)
    assert CliRunner().invoke(app, [*arguments, "--enforce"]).exit_code == 0
    # A run without --enforce wrote its configuration, then stopped before the hook file.
    path = configuration_path(project, config_dir)
    stored = json.loads(path.read_text())
    stored["gate"] = None
    path.write_text(json.dumps(stored))
    assert CliRunner().invoke(app, arguments).exit_code == 0
    assert set(ProjectHooks.model_validate_json((project / HOOK_FILE).read_text()).hooks) == {"agentStop", "sessionEnd"}


def test_an_exclude_file_that_cannot_be_written_warns(project: Path, credential: Path, tmp_path: Path) -> None:
    git("init", "-q", project)
    exclude = project / ".git/info/exclude"
    exclude.chmod(0o400)
    try:
        result = CliRunner().invoke(app, setup_arguments(project, credential, tmp_path / "configuration"))
    finally:
        exclude.chmod(0o600)
    assert result.exit_code == 0 and "local exclude file" in result.stderr


def test_an_earlier_api_key_installation_on_a_plain_http_server_can_be_replaced_or_removed(
    project: Path, credential: Path, tmp_path: Path
) -> None:
    config_dir = tmp_path / "configuration"
    assert CliRunner().invoke(app, setup_arguments(project, credential, config_dir)).exit_code == 0
    path = configuration_path(project, config_dir)
    hook_file = project / HOOK_FILE
    # An earlier version authenticated with an API key, could use plain HTTP to another
    # machine, and wrote hooks that name no server.
    legacy = json.loads(path.read_text())
    for name in ("hook", "gate"):
        legacy[name] = without_server(legacy[name])
    legacy.update(
        watcher_url="http://10.0.0.5:8026/api",
        watcher_auth=False,
        watcher_state_dir=None,
        api_key_file=str(tmp_path / "key"),
    )
    hooks = json.loads(hook_file.read_text())
    hooks["hooks"] = {event: [without_server(entry) for entry in entries] for event, entries in hooks["hooks"].items()}

    def install_legacy() -> None:
        path.write_text(json.dumps(legacy))
        hook_file.write_text(json.dumps(hooks))

    install_legacy()
    with pytest.raises(ValueError, match="run setup again with a sign-in"):
        load_configuration(path)

    replaced = CliRunner().invoke(app, setup_arguments(project, credential, config_dir))

    assert replaced.exit_code == 0, replaced.output
    current = load_configuration(path)
    assert current.watcher_url == URL and not hooks_without_server(path, current)
    install_legacy()
    removed = CliRunner().invoke(app, ["remove", "--project", str(project), "--config-dir", str(config_dir)])
    assert removed.exit_code == 0, removed.output
    assert not path.exists() and not hook_file.exists()


def test_an_earlier_api_key_installation_can_be_replaced_with_a_login_or_removed(
    project: Path, credential: Path, tmp_path: Path
) -> None:
    config_dir = tmp_path / "configuration"
    assert CliRunner().invoke(app, setup_arguments(project, credential, config_dir)).exit_code == 0
    path = configuration_path(project, config_dir)
    legacy = json.loads(path.read_text())
    key = tmp_path / "key"
    key.write_text("PRIVATE_TEST_CREDENTIAL")
    legacy.update(watcher_auth=False, watcher_state_dir=None, api_key_file=str(key))
    path.write_text(json.dumps(legacy))
    with pytest.raises(ValueError, match="run setup again with a sign-in"):
        load_configuration(path)

    replaced = CliRunner().invoke(app, setup_arguments(project, credential, config_dir))
    assert replaced.exit_code == 0, replaced.output
    assert load_configuration(path).watcher_auth

    path.write_text(json.dumps(legacy))
    removed = CliRunner().invoke(app, ["remove", "--project", str(project), "--config-dir", str(config_dir)])
    assert removed.exit_code == 0, removed.output
    assert not path.exists() and not (project / HOOK_FILE).exists()
