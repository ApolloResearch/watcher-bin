"""Install the observer in Copilot's personal hooks or in one project, keeping its credential private."""

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from filelock import FileLock
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from watcher_sdk import IntegrationAuth, WatcherLoginAuth
from watcher_sdk.integration_auth import ALLOW_INSECURE_LOGIN_URL, watcher_state_directory
from watcher_sdk.local_auth import _api_url

HOOK_FILE = Path(".github/hooks/watcher-sdk-copilot.json")
# Copilot's managed settings file on Linux. An organization policy can also arrive
# from GitHub or a device management profile, which setup cannot read.
MANAGED_SETTINGS = Path("/etc/github-copilot/managed-settings.json")
MAX_HOOK_FILE_BYTES = 1024 * 1024
# agentStop records each completed turn; sessionEnd records the final state,
# including subagents that finish after the last turn.
OBSERVED_EVENTS = ("agentStop", "sessionEnd")


class ObserverHook(BaseModel):
    type: Literal["command"] = "command"
    exec: str
    args: list[str]
    timeoutSec: int = 50


class GateHook(BaseModel):
    """The optional preToolUse gate. Its 480 seconds exceed the gate's own 420-second deadline.

    Copilot runs the tool anyway when this outer timeout expires, so the inner
    deadline must stay shorter.
    """

    type: Literal["command"] = "command"
    exec: str
    args: list[str]
    timeoutSec: int = 480


class ProjectHooks(BaseModel):
    """A Copilot hook file, in either hooks folder: its version, its entries per event and any other fields."""

    model_config = ConfigDict(extra="allow")

    version: Literal[1] = 1
    hooks: dict[str, list[JsonValue]]

    @field_validator("version", mode="before")
    @classmethod
    def refuse_a_boolean_version(cls, value: JsonValue) -> JsonValue:
        """Refuse JSON ``true`` and ``false``, which Copilot rejects as a version.

        ``Literal[1]`` alone matches ``true``, because Python counts ``True`` as 1,
        and Copilot skips the whole file over it. Status would then count hooks
        that never run as installed.
        """
        if isinstance(value, bool):
            raise ValueError("The hook file version must be the number 1")
        return value


# Plain HTTP is accepted only for a Watcher on this machine, as Watcher's own
# credential helpers do: elsewhere the key, transcripts and gate answers would
# cross the network in cleartext, and anyone on the path could rewrite a decision.
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def validate_watcher_url(value: str) -> None:
    """Refuse a Watcher URL with credentials, a query or fragment, or plain HTTP to another host.

    Each refusal raises ``ValueError`` with a fixed message that never repeats the URL.
    """
    url = urlsplit(value)
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
        raise ValueError("Watcher URL must be an HTTP or HTTPS URL without credentials")
    if url.query or url.fragment:
        raise ValueError("Watcher URL must not contain a query or fragment")
    if url.scheme == "http" and url.hostname.lower() not in LOOPBACK_HOSTS:
        raise ValueError("Watcher URL must use HTTPS unless Watcher runs on this machine")


# Credential sources the integration accepts: a user's own login, whose session
# reads the server scopes to that user. API keys would need organization-wide read.
LOGIN_KINDS = frozenset({"sdk_login", "watcher_login"})
API_KEY_UNSUPPORTED = (
    "API-key authentication is no longer supported by the Copilot integration; run setup again with a login"
)
# Setup writes the server into each hook command with this option as well as into
# the private configuration. Anything that can rewrite the configuration could
# otherwise point the hooks at a server of its choosing, such as a stub on this
# machine that allows every call, while the project hook file stayed unchanged.
SERVER_OPTION = "--watcher-url"


def bound_server(args: list[str]) -> str | None:
    """The server a hook command names with ``SERVER_OPTION``; None for commands from earlier versions.

    A trailing option without a value returns an empty string, which matches no server.
    """
    if SERVER_OPTION not in args:
        return None
    return next(iter(args[args.index(SERVER_OPTION) + 1 :]), "")


class InstallationScope(BaseModel):
    """Which folders an installation covers, and the personal install's opt-outs (see ``ObserverConfiguration``).

    ``load_scope`` reads a configuration as this model alone and ignores every
    other field, its server, credential and hook commands included. So the
    opt-outs still hold in a configuration that no other reader accepts.
    """

    model_config = ConfigDict(extra="ignore")

    version: Literal[1] = 1
    project: Path | None = None
    copilot_home: Path | None = None
    opted_out: list[Path] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if (self.project is None) == (self.copilot_home is None):
            raise ValueError("Name either a project or Copilot's personal hooks folder")
        if self.copilot_home is not None and not self.copilot_home.is_absolute():
            raise ValueError("COPILOT_HOME must be an absolute path")
        if self.project is not None and self.opted_out:
            raise ValueError("Only the personal install has opted-out projects")
        return self


class InstallationHooks(BaseModel):
    """The hook commands an installation stores, read alone by ``load_hooks``, like ``InstallationScope``.

    Status and opt-out read them only to find the Python each hook runs (see
    ``scopes``), so a configuration its hooks refuse, for its server or
    credential, still has them read.
    """

    model_config = ConfigDict(extra="ignore")

    hook: ObserverHook | None = None
    gate: GateHook | None = None


class ObserverConfiguration(InstallationScope):
    """One installation: a project's, or the personal one whose hooks run in every folder.

    A project install names its ``project``. The personal install names instead the
    ``copilot_home`` its hook file lives in, and keeps the project roots the user
    opted out of this sample's hooks (see ``project_root``) in ``opted_out``. Every
    callback, a project install's included, reads that list (see ``scopes``). This
    private file is the only place an opt-out is stored, so nothing inside a
    project can opt it out.
    """

    model_config = ConfigDict(extra="forbid")

    watcher_url: str
    # Earlier versions could authenticate with an API key. Those fields stay readable
    # only so a stored configuration that names one gets a clear error.
    api_key_file: Path | None = None
    api_key_env: str | None = None
    watcher_auth: bool = False
    watcher_state_dir: Path | None = None
    auth_profile: IntegrationAuth | None = None
    hook: ObserverHook
    gate: GateHook | None = None

    @model_validator(mode="after")
    def validate_destination(self, info: ValidationInfo) -> "ObserverConfiguration":
        context = info.context or {}
        # Readers that only report an installation, change its opt-outs, replace or
        # delete it still read a configuration redirected after setup (see
        # ``names_another_server``), so they can repair it. The hooks and everything
        # else refuse it.
        lenient = bool(context.get("allow_server_mismatch"))
        if not lenient and _commands_name_another_server(self):
            raise ValueError("The hook commands name a different Watcher server than this configuration")
        legacy = self.api_key_file is not None or self.api_key_env is not None
        if legacy or (self.auth_profile is not None and self.auth_profile.kind not in LOGIN_KINDS):
            # Setup and removal still read an earlier API-key installation so they can replace or remove it.
            # Nothing is ever sent to its server, so an earlier plain-HTTP address does not block that.
            if not context.get("allow_legacy_credentials"):
                raise ValueError(API_KEY_UNSUPPORTED)
            return self
        # Nothing is sent to any server a redirected configuration names either, so a
        # server rewritten to plain HTTP elsewhere does not stop its repair. The same
        # holds for its login, which the lenient read accepts on such a server (see
        # ``load_configuration``). A configuration that is not redirected names one
        # server for both, so this check keeps refusing a plain-HTTP login there too.
        if not (lenient and names_another_server(self)):
            validate_watcher_url(self.watcher_url)
        if self.watcher_auth == (self.auth_profile is not None):
            raise ValueError("Choose one Watcher login")
        if not lenient and _login_names_another_server(self):
            raise ValueError("The credential profile belongs to a different server")
        return self


def _commands_name_another_server(config: ObserverConfiguration) -> bool:
    return any(
        command is not None and bound_server(command.args) not in {None, config.watcher_url}
        for command in (config.hook, config.gate)
    )


def _login_names_another_server(config: ObserverConfiguration) -> bool:
    if config.auth_profile is None:
        return False
    try:
        return _api_url(config.watcher_url) != _api_url(config.auth_profile.base_url)
    except ValueError:
        # A server that is not a valid URL cannot be the one the login belongs to.
        return True


def names_another_server(config: ObserverConfiguration) -> bool:
    """Whether ``config`` names more than one server, so something rewrote part of it after setup.

    That is the case when a hook command stored in it names a different server
    than its ``watcher_url`` (see ``SERVER_OPTION``), or when its login profile
    belongs to a different server than that. Changing either field alone is
    enough. Hooks refuse such a configuration, and ``load_configuration`` refuses
    it too unless asked not to. Commands from earlier versions name no server and
    never count.
    """
    return _commands_name_another_server(config) or _login_names_another_server(config)


def configuration_path(project: Path | None, config_dir: Path | None) -> Path:
    """The private configuration file for ``project``, outside it, or for the personal install when ``None``.

    Each project gets its own folder, named by a hash of its path, and the personal
    install the folder ``personal``, under ``config_dir`` or
    ``$XDG_CONFIG_HOME/watcher-copilot`` (``~/.config`` by default).
    """
    root = config_dir or Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "watcher-copilot"
    identity = "personal" if project is None else hashlib.sha256(str(project).encode()).hexdigest()
    return root.expanduser().resolve() / identity / "config.json"


def copilot_home() -> Path:
    """Copilot's configuration folder, resolved exactly as Copilot resolves it.

    A nonempty ``COPILOT_HOME`` is used as given: Copilot neither expands ``~`` nor
    makes a relative value absolute. Otherwise it is ``~/.copilot``. Copilot reads
    personal hooks from its ``hooks`` folder and session logs from ``session-state``.
    """
    return Path(os.environ.get("COPILOT_HOME") or Path.home() / ".copilot")


def hook_file(config: "ObserverConfiguration") -> Path:
    """Where Copilot reads this installation's hooks: the project's ``.github/hooks`` or the personal hooks folder."""
    if config.project is not None:
        return config.project / HOOK_FILE
    assert config.copilot_home is not None
    return config.copilot_home / "hooks" / HOOK_FILE.name


def _contained(path: Path, folder: Path) -> Path:
    """``path`` when it is a plain file location inside ``folder``; a symlink or redirected folder raises ``ValueError``.

    The agent can write to both hooks folders, and a redirected path would make
    setup or removal write outside them.
    """
    if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
        raise ValueError("The observer hook must be a plain file in its hooks folder, without a redirected path")
    return path


def installed_hook_path(config: "ObserverConfiguration") -> Path:
    """``hook_file(config)``, refusing a symlinked or redirected path with ``ValueError``."""
    if config.project is not None:
        return _project_hook_path(config.project)
    assert config.copilot_home is not None
    return _contained(hook_file(config), config.copilot_home)


def _read_file(path: Path, limit: int) -> str:
    """Read a regular file of at most ``limit`` characters; anything else raises ``ValueError``.

    Refusing devices and FIFOs keeps a misconfigured path from blocking a hook.
    """
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Configuration and credentials must be regular files")
    with path.open("rb") as source:
        contents = source.read(limit + 1)
    if len(contents) > limit:
        raise ValueError("Configuration or credential file exceeds its size limit")
    return contents.decode("utf-8")


def load_configuration(
    path: Path, *, allow_legacy_credentials: bool = False, allow_server_mismatch: bool = False
) -> ObserverConfiguration:
    """Read and validate the configuration setup wrote; a malformed file raises ``ValueError``.

    A configuration from an earlier version that names an API key raises
    ``ValueError`` with ``API_KEY_UNSUPPORTED``, unless ``allow_legacy_credentials``
    is set, which setup and removal use to replace or remove such an installation.
    Such a configuration may name a plain-HTTP server on another machine, since
    nothing is sent to it. A configuration that names more than one server (see
    ``names_another_server``) also raises ``ValueError``, unless
    ``allow_server_mismatch`` is set; its server and its login may then name a
    plain-HTTP server on another machine too. Such a login still never signs in
    (see ``ALLOW_INSECURE_LOGIN_URL``). Setup, removal and opt-out changes set
    both, because they replace or delete the configuration, or change only its
    opt-outs, and so do readers that only report the installation.
    """
    return ObserverConfiguration.model_validate_json(
        _read_file(path, 64 * 1024),
        context={
            "allow_legacy_credentials": allow_legacy_credentials,
            "allow_server_mismatch": allow_server_mismatch,
            ALLOW_INSECURE_LOGIN_URL: allow_server_mismatch,
        },
    )


def load_scope(path: Path) -> InstallationScope:
    """Read only which folders the configuration at ``path`` covers and its opt-outs (see ``InstallationScope``).

    A file that is not JSON, or whose scope is invalid, raises ``ValueError``.
    """
    return InstallationScope.model_validate_json(_read_file(path, 64 * 1024))


def load_hooks(path: Path) -> InstallationHooks:
    """Read only the hook commands the configuration at ``path`` stores (see ``InstallationHooks``).

    A file that is not JSON, or whose commands are invalid, raises ``ValueError``.
    """
    return InstallationHooks.model_validate_json(_read_file(path, 64 * 1024))


def load_auth_profile(path: Path) -> IntegrationAuth:
    return IntegrationAuth.model_validate_json(_read_file(path, 64 * 1024))


def _write_file(path: Path, contents: str) -> None:
    """Replace ``path`` atomically with ``contents`` and a trailing newline, readable only by its owner.

    The owner-only mode comes from ``NamedTemporaryFile``, which creates files with
    mode 0600; the rename keeps it. Configuration and status rely on this.
    """
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        output.write(contents + "\n")
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_hook_file(path: Path) -> ProjectHooks | None:
    """The hook file at ``path``, or ``None`` when there is none.

    A malformed file raises ``ValueError`` and an unreadable one ``OSError``.
    Status and the installers read hook files here, for either installation.
    """
    if not path.exists():
        return None
    return ProjectHooks.model_validate_json(_read_file(path, MAX_HOOK_FILE_BYTES))


def hooks_installed(config: ObserverConfiguration) -> bool:
    """Whether Copilot's hook file for this installation holds exactly the entries it owns, unchanged, and nothing else.

    Copilot skips a whole hook file over one entry it rejects, for example one that
    nests hooks more than one level deep, and over a file-level ``disableAllHooks``.
    This module cannot check every rule Copilot applies, so any other entry or
    top-level field counts as not installed, as does a missing, unreadable,
    malformed or redirected file. A file whose version Copilot rejects, such as
    ``true``, is malformed (see ``ProjectHooks``). Entries are compared as JSON,
    so ``50`` and ``50.0`` differ.
    """
    try:
        document = read_hook_file(installed_hook_path(config))
    except (OSError, ValueError):
        return False
    owned = {event: [entry] for event, entry in _owned_entries(config).items()}
    return (
        document is not None
        and not document.model_extra
        and json.dumps(document.hooks, sort_keys=True) == json.dumps(owned, sort_keys=True)
    )


def _owned_entries(config: ObserverConfiguration) -> dict[str, JsonValue]:
    entries: dict[str, JsonValue] = {event: config.hook.model_dump(mode="json") for event in OBSERVED_EVENTS}
    if config.gate is not None:
        entries["preToolUse"] = config.gate.model_dump(mode="json")
    return entries


def _names(value: JsonValue, text: str) -> bool:
    if isinstance(value, str):
        return text in value
    if isinstance(value, list):
        return any(_names(item, text) for item in value)
    if isinstance(value, dict):
        return any(_names(item, text) for item in value.values())
    return False


def _named_server(entry: JsonValue) -> str | None:
    """The server a hook entry's command names, or None when it names none or its arguments are malformed."""
    arguments = entry.get("args") if isinstance(entry, dict) else None
    if not isinstance(arguments, list) or not all(isinstance(argument, str) for argument in arguments):
        return None
    return bound_server([str(argument) for argument in arguments])


def hooks_without_server(path: Path, config: ObserverConfiguration) -> bool:
    """Whether any hook command of the installation configured at ``path`` names no server.

    Checks the commands stored in the configuration and every entry of the
    installation's hook file, the project's or the personal one (see
    ``installed_hook_path``), that names ``path``, since those entries are what
    Copilot runs. The two can differ: setup writes the configuration first, so an
    upgrade that stops before rewriting the hook file leaves the earlier entries
    installed. A missing hook file has no entries; one that cannot be read or
    parsed, or a symlinked or redirected one, raises ``OSError`` or ``ValueError``.
    """
    commands: list[JsonValue] = [
        command.model_dump(mode="json") for command in (config.hook, config.gate) if command is not None
    ]
    installed = read_hook_file(installed_hook_path(config))
    if installed is not None:
        commands += [entry for entries in installed.hooks.values() for entry in entries if _names(entry, str(path))]
    return any(_named_server(command) is None for command in commands)


def _without_owned_hook(document: ProjectHooks, path: Path, *configs: ObserverConfiguration) -> ProjectHooks:
    """Remove the entries ``configs`` own, refusing when another entry that mentions ``path`` exists.

    Such an entry is one of this integration's, edited by hand. Missing entries are
    tolerated: an install from an earlier version of this sample may lack some of
    today's entries. Setup passes both the stored and the new configuration, so it
    also recovers from a run that stopped between writing the two files.
    """
    owned = [(event, entry) for config in configs for event, entry in _owned_entries(config).items()]
    for event, entries in document.hooks.items():
        for entry in entries:
            if _names(entry, str(path)) and (event, entry) not in owned:
                raise ValueError("The installed hook was changed; restore it before setup or removal")
    for event, entry in owned:
        entries = [item for item in document.hooks.get(event, []) if item != entry]
        if entries:
            document.hooks[event] = entries
        else:
            document.hooks.pop(event, None)
    return document


def exclude_hook_from_git(project: Path) -> bool:
    """List the hook file in the repository's local exclude file; return whether it is excluded.

    Its commands name this machine's interpreter and configuration. On another
    machine a gate command that cannot start makes Copilot deny every tool.
    Only ``info/exclude`` changes, never ``.gitignore``; removal leaves the line.
    Git finds the file for linked worktrees and projects below the repository root.
    Returns ``False`` outside a Git repository or when Git cannot be used.
    """
    try:
        exclude, root = subprocess.run(
            ["git", "-C", str(project), "rev-parse", "--git-path", "info/exclude", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.splitlines()[:2]
        relative = (project / HOOK_FILE).relative_to(Path(root).resolve()).as_posix()
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    # Exclude patterns are globs, so characters such as [ in a folder name are escaped.
    line = "/" + re.sub(r"([\\\[\]*?!#])", r"\\\1", relative)
    path = project / exclude
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if line not in text.splitlines():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as output:
                output.write(("\n" if text and not text.endswith("\n") else "") + line + "\n")
    except (OSError, UnicodeDecodeError):
        return False
    return True


def _project_hook_path(project: Path) -> Path:
    return _contained(project / HOOK_FILE, project)


def install_observer(
    project: Path | None,
    watcher_url: str,
    config_dir: Path | None,
    enforce: bool | None = None,
    watcher_auth: bool = False,
    *,
    auth_profile: IntegrationAuth | None = None,
    watcher_state_dir: Path | None = None,
) -> Path:
    """Add one observer, preserving other hooks and refusing an unowned filename.

    With ``project=None`` the hooks go to Copilot's personal hooks folder,
    ``copilot_home()/hooks``, where they run for every Copilot session of this user,
    with one machine-level configuration that keeps its opt-outs across setups. A
    ``COPILOT_HOME`` that is not absolute raises ``ValueError``, because Copilot
    would resolve it from whichever folder it starts in. With a project they go to
    its ``.github/hooks``, with that project's own configuration.

    New installations include a preToolUse gate that reads the same private
    configuration as the observer. ``enforce=None`` preserves an existing mode;
    an explicit boolean selects blocking review or recording only.

    Setup checks the credential's local presence, not API access. The installed
    environment must stay at its current path. Repeated setup updates the owned
    hook and configuration; it never changes Copilot's native permissions.
    Each hook command also names ``watcher_url``, and refuses to run when the
    configuration names another server.
    """
    if watcher_state_dir is not None and not watcher_auth:
        raise ValueError("--watcher-state-dir requires --watcher-auth")
    home: Path | None = None
    if project is None:
        home = copilot_home()
        if not home.is_absolute():
            raise ValueError("COPILOT_HOME must be an absolute path")
        hook_path = _contained(home / "hooks" / HOOK_FILE.name, home)
    else:
        project = project.expanduser().resolve(strict=True)
        if not project.is_dir():
            raise ValueError("Project must be a directory")
        hook_path = _project_hook_path(project)
    path = configuration_path(project, config_dir)
    if project is not None and path.is_relative_to(project):
        raise ValueError("Configuration must be stored outside the project")
    watcher_url = watcher_url.rstrip("/")
    gate = GateHook(
        exec=str(Path(sys.executable).absolute()),
        args=[
            "-I",
            "-m",
            "watcher_github_copilot_cli.cli",
            "enforce",
            "--config",
            str(path),
            SERVER_OPTION,
            watcher_url,
        ],
    )
    config = ObserverConfiguration(
        project=project,
        copilot_home=home,
        watcher_url=watcher_url,
        watcher_auth=watcher_auth,
        watcher_state_dir=(watcher_state_dir or watcher_state_directory()).expanduser().resolve()
        if watcher_auth
        else None,
        auth_profile=auth_profile,
        hook=ObserverHook(
            exec=str(Path(sys.executable).absolute()),
            args=[
                "-I",
                "-m",
                "watcher_github_copilot_cli.cli",
                "observe",
                "--config",
                str(path),
                SERVER_OPTION,
                watcher_url,
                "--record-only",
            ],
        ),
        gate=gate if enforce is not False else None,
    )
    # A project install refuses a saved login inside the project, where the agent
    # could replace it. The personal install covers no single project.
    if auth_profile is not None:
        if project is not None:
            auth_profile.login_auth().validate_project_location(project)
        auth_profile.validate_local()
    else:
        assert config.watcher_state_dir is not None
        login = WatcherLoginAuth(config.watcher_url, state_dir=config.watcher_state_dir)
        if project is not None:
            login.validate_project_location(project)
        login.validate()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with FileLock(str(path) + ".lock", timeout=5):
        document = ProjectHooks(hooks={})
        previous = (
            load_configuration(path, allow_legacy_credentials=True, allow_server_mismatch=True)
            if path.exists()
            else None
        )
        if previous is not None:
            if previous.project != project or previous.copilot_home != home:
                # The personal install keeps the Copilot home it was installed into,
                # so removal finds its hook file even after COPILOT_HOME changes.
                raise ValueError("Stored configuration belongs to another project or Copilot home")
            if enforce is None:
                config = config.model_copy(update={"gate": gate if previous.gate else None})
            config = config.model_copy(update={"opted_out": previous.opted_out})
        installed = read_hook_file(hook_path)
        if installed is not None:
            if previous is None:
                raise ValueError("The observer hook filename already exists and is not owned by this setup")
            document = _without_owned_hook(installed, path, previous, config.model_copy(update={"gate": gate}))
        for event, entry in _owned_entries(config).items():
            document.hooks.setdefault(event, []).append(entry)
        hook_path.parent.mkdir(parents=True, exist_ok=True)
        _write_file(path, config.model_dump_json(indent=2))
        _write_file(hook_path, document.model_dump_json(indent=2))
    return path


def remove_observer(project: Path | None, config_dir: Path | None) -> bool:
    """Remove the exact installed observer and its configuration, keeping credentials.

    ``project=None`` removes the personal install from the Copilot home it was
    installed into, together with its opt-outs. Unrelated entries in the same file
    survive. An entry of this integration that was edited by hand is refused, so
    removal never leaves a gate behind whose configuration is gone, and never
    removes someone else's integration.
    """
    if project is not None:
        project = project.expanduser().resolve(strict=True)
    path = configuration_path(project, config_dir)
    if not path.exists():
        return False
    with FileLock(str(path) + ".lock", timeout=5):
        config = load_configuration(path, allow_legacy_credentials=True, allow_server_mismatch=True)
        if config.project != project:
            raise ValueError("Stored configuration belongs to another project")
        hook_path = installed_hook_path(config)
        installed = read_hook_file(hook_path)
        if installed is not None:
            document = _without_owned_hook(installed, path, config)
            if document.hooks or document.model_extra:
                _write_file(hook_path, document.model_dump_json(indent=2))
            else:
                hook_path.unlink()
        path.unlink()
    return True


# A linked worktree's .git file holds one short gitdir line, so anything larger is
# not one. Hooks read it before the gate's deadline starts.
MAX_GIT_FILE_BYTES = 64 * 1024


class UninspectableGitMarker(OSError):
    """A ``.git`` marker that exists but cannot be inspected safely, so the project it would mark is unknown."""


def _git_file_line(marker: Path) -> str:
    """The first line of the regular ``.git`` file ``marker``.

    The file is opened without following a symlink and without blocking, then
    checked through the open descriptor, so a FIFO or device put in its place,
    even after an earlier check, is refused instead of blocking the hook. A file
    that is not regular, is larger than ``MAX_GIT_FILE_BYTES``, cannot be read or
    is not UTF-8 text raises ``UninspectableGitMarker``.
    """
    try:
        descriptor = os.open(marker, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise UninspectableGitMarker("A .git file cannot be opened") from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_GIT_FILE_BYTES:
            raise UninspectableGitMarker("A .git file is not a small regular file")
        data = b""
        while len(data) <= MAX_GIT_FILE_BYTES and (chunk := os.read(descriptor, MAX_GIT_FILE_BYTES + 1 - len(data))):
            data += chunk
    except UninspectableGitMarker:
        raise
    except OSError as error:
        raise UninspectableGitMarker("A .git file cannot be read") from error
    finally:
        os.close(descriptor)
    if len(data) > MAX_GIT_FILE_BYTES:
        raise UninspectableGitMarker("A .git file is not a small regular file")
    try:
        return data.decode("utf-8").partition("\n")[0]
    except UnicodeDecodeError as error:
        raise UninspectableGitMarker("A .git file is not UTF-8 text") from error


def _has(path: Path, kind: Callable[[int], bool]) -> bool:
    """Whether ``path`` exists with a mode ``kind`` accepts, such as ``stat.S_ISDIR``; other stat errors raise ``OSError``."""
    try:
        mode = path.stat().st_mode
    except (FileNotFoundError, NotADirectoryError):
        return False
    return kind(mode)


def _is_repository(folder: Path) -> bool:
    """Whether ``folder`` holds a ``.git`` that Copilot accepts as a repository.

    Copilot accepts a ``.git`` folder only with ``HEAD``, ``objects`` and ``refs``,
    and a ``.git`` file only when its ``gitdir:`` line points at a folder with
    ``HEAD`` and either those two folders or a ``commondir``, as a linked worktree's
    does.

    Only a missing ``.git`` gives ``False``. Any other ``.git`` that is not such a
    repository raises ``OSError`` (``UninspectableGitMarker`` for the marker
    itself): one that cannot be inspected, such as an unreadable, oversized or
    non-UTF-8 file, a symlink, a FIFO or another special file, and one that names
    no valid repository, such as a folder without ``HEAD`` or a file pointing at
    a missing folder. Treating it as absent would let ``project_root`` carry on to
    a parent folder's repository, which may be opted out.
    """
    marker = folder / ".git"
    try:
        info = marker.lstat()
    except (FileNotFoundError, NotADirectoryError):
        return False
    if stat.S_ISDIR(info.st_mode):
        if (
            _has(marker / "HEAD", stat.S_ISREG)
            and _has(marker / "objects", stat.S_ISDIR)
            and _has(marker / "refs", stat.S_ISDIR)
        ):
            return True
        raise UninspectableGitMarker("A .git folder is not a repository")
    if not stat.S_ISREG(info.st_mode):
        raise UninspectableGitMarker("A .git marker is neither a folder nor a regular file")
    line = _git_file_line(marker)
    if line.startswith("gitdir:"):
        directory = folder / line.removeprefix("gitdir:").strip()
        if _has(directory / "HEAD", stat.S_ISREG) and (
            _has(directory / "commondir", stat.S_ISREG)
            or (_has(directory / "objects", stat.S_ISDIR) and _has(directory / "refs", stat.S_ISDIR))
        ):
            return True
    raise UninspectableGitMarker("A .git file names no repository")


def project_root(folder: Path) -> Path:
    """The project a Copilot session started in ``folder`` belongs to, as Copilot finds it.

    Symlinks are followed first. Inside a Git repository, including a linked
    worktree or a nested repository, it is the innermost repository's root; that is
    where Copilot reads project hooks from. Elsewhere it is the folder itself, since
    outside Git Copilot reads them only from the folder it starts in. Opt-outs use
    this root. A folder, or a ``.git`` marker on the way up, that cannot be
    inspected raises ``OSError`` (see ``_is_repository``), so a caller never
    settles on a parent's project by mistake.
    """
    resolved = folder.resolve()
    return next((candidate for candidate in (resolved, *resolved.parents) if _is_repository(candidate)), resolved)


def set_opt_out(root: Path, config_dir: Path | None, *, opted_out: bool) -> bool:
    """Opt the project root ``root`` out of this sample's hooks, or back in; return whether that changed.

    ``root`` is written exactly as given, so the caller resolves it (see
    ``project_root``) and confirms that same path before calling. An opt-out turns
    off the personal install and any project install there. The choice is written
    only to the personal install's private configuration. Without a personal
    install this raises ``ValueError``. A personal configuration its hooks refuse,
    one redirected to another server or naming an API key, still takes the change
    and keeps everything else as it was, since every callback reads the opt-outs
    from it anyway (see ``scopes``).
    """
    path = configuration_path(None, config_dir)
    if not path.exists():
        raise ValueError("Install the personal hooks before opting a project out of them")
    with FileLock(str(path) + ".lock", timeout=5):
        config = load_configuration(path, allow_legacy_credentials=True, allow_server_mismatch=True)
        if opted_out:
            updated = config.opted_out if root in config.opted_out else [*config.opted_out, root]
        else:
            updated = [item for item in config.opted_out if item != root]
        if updated != config.opted_out:
            _write_file(path, config.model_copy(update={"opted_out": updated}).model_dump_json(indent=2))
    return updated != config.opted_out


_JSON_FILE = TypeAdapter(dict[str, JsonValue])


def _json_file(path: Path) -> dict[str, JsonValue] | None:
    """A Copilot settings file, ``{}`` when it does not exist, or ``None`` when it cannot be read.

    Copilot writes ``//`` comment lines at the top of its files; they are skipped.
    Other comments or trailing commas make the file unreadable here.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError):
        return None
    try:
        return _JSON_FILE.validate_json("\n".join(line for line in lines if not line.lstrip().startswith("//")))
    except ValidationError:
        return None


def in_git_repository(project: Path) -> bool:
    """Whether ``project`` or a folder above it holds ``.git``, as a checkout, worktree or submodule does."""
    return any((folder / ".git").exists() for folder in (project, *project.parents))


def loading_warnings(project: Path | None) -> list[str]:
    """Settings that make, or may make, Copilot skip or duplicate this installation's hooks without saying so.

    ``None`` checks the personal install: Copilot's user settings and the managed
    policy. A project adds its folder trust, its own settings and its Git layout.
    """
    home = copilot_home()
    files = {"config": home / "config.json", "user": home / "settings.json", "managed": MANAGED_SETTINGS}
    if project is not None:
        project = project.expanduser().resolve()
        files |= {
            "project": project / ".github/copilot/settings.json",
            "local": project / ".github/copilot/settings.local.json",
            "claude": project / ".claude/settings.json",
            "claude-local": project / ".claude/settings.local.json",
        }
    values = {name: _json_file(path) for name, path in files.items()}
    warnings = [
        f"Setup could not read {files[name]}, so it did not check it."
        for name, value in values.items()
        if value is None
    ]
    settings = {name: value or {} for name, value in values.items()}
    trusted = settings["config"].get("trustedFolders")
    if (
        project is not None
        and values["config"] is not None
        and not (
            isinstance(trusted, list)
            and any(isinstance(folder, str) and project.is_relative_to(Path(folder).expanduser()) for folder in trusted)
        )
    ):
        warnings.append("Trust this folder when Copilot asks: Copilot runs no hooks from an untrusted folder.")
    copilot = [settings[name] for name in ("config", "user", "project", "local") if name in settings]
    # Copilot also applies disableAllHooks from a project's Claude Code settings.
    repository = [settings[name] for name in ("project", "local", "claude", "claude-local") if name in settings]
    if any(value.get("disableAllHooks") is True for value in repository):
        warnings.append(
            "This project's Copilot or Claude Code settings set disableAllHooks, so no hook will run in it."
        )
    # Copilot 1.0.91 reads a user-level disableAllHooks yet still runs every hook,
    # so unlike the repository case above this warning must not claim that no hook will run.
    if any(settings[name].get("disableAllHooks") is True for name in ("config", "user")):
        warnings.append(
            "Copilot's user settings set disableAllHooks. Copilot 1.0.91 still ran hooks with it set,"
            " but other versions may skip them."
        )
    if any(value.get("disabledHooks") for value in copilot):
        target = "the personal hooks" if project is None else "this project's hooks"
        warnings.append(f"Copilot's settings list disabledHooks; make sure {target} are not among them.")
    if settings["managed"].get("allowManagedHooksOnly", False) is not False:
        warnings.append(
            "Your organization's Copilot policy allows only managed hooks, so Copilot will not run these hooks."
        )
    if project is None:
        return warnings
    if not in_git_repository(project):
        warnings.append(
            "Start Copilot in the project folder: outside a Git repository, subfolders do not load its hooks."
        )
    if "hooks" in settings["claude"] or "hooks" in settings["claude-local"]:
        warnings.append(
            "Copilot also runs the Claude Code hooks in this project's .claude settings, with Claude-style input."
        )
    return warnings
