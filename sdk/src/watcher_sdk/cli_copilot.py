"""Manage the optional Copilot package without importing it from the core SDK.

The Copilot package installs its hooks in one of two scopes. The personal
install puts them in Copilot's personal hooks folder, where they run for every
Copilot session of this user, with one private configuration at
``<configuration root>/personal/config.json``. A project install puts them in
one project's ``.github/hooks``, with that project's own private configuration.
Every command here acts on the personal install unless ``--project`` names a
project. Both can exist: Copilot then runs both in that project, and install and
status warn about it. An opt-out, which only the personal install's
configuration stores, turns off both in that project.
"""

import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path

import typer
from pydantic import BaseModel

from watcher_sdk.cli_auth import CommandError, printable, resolve_profile
from watcher_sdk.integration_auth import ALLOW_INSECURE_LOGIN_URL, IntegrationAuth, verify_integration_auth

LOGIN_KINDS = frozenset({"sdk_login", "watcher_login"})
# Doctor reads each retained receipt back once, within this long. Polling would
# rarely confirm more: a judgment can be read back only after its session's
# transcript is recorded, and the hooks already read back after each recording.
READBACK_SECONDS = 30.0


class CopilotInstallation(BaseModel):
    """One installed Copilot integration, read without network access.

    ``project`` is ``None`` for the personal install. ``hook_server`` is the
    server the hook commands name, or ``None`` for hooks from earlier versions,
    which name none. ``redirected`` is true when that server, or the server the
    sign-in belongs to (``auth.base_url``), differs from the one in the private
    configuration: the hooks then refuse to run, because something rewrote the
    configuration after setup.

    ``auth`` is the credential the installation uses. Nothing is ever sent for a
    redirected configuration, so its sign-in may be plain HTTP to another machine,
    which can never sign in (see ``ALLOW_INSECURE_LOGIN_URL``). A redirected
    configuration from the Copilot package's own setup has no ``auth`` at all: its
    hooks use Watcher's saved sign-in for the configuration's server, which is
    whatever rewrote it, so that sign-in is chosen only once install or update names
    a server.
    """

    config: Path
    auth: IntegrationAuth | None
    reviews_tools: bool
    project: Path | None
    hook_file: Path
    hook_server: str | None
    redirected: bool

    def credential(self) -> IntegrationAuth:
        """``auth``; only a redirected configuration can lack one, and every caller refuses those first."""
        assert self.auth is not None, "A redirected configuration names no credential to use"
        return self.auth


def _resolved(project: Path | None) -> Path | None:
    return project.expanduser().resolve() if project is not None else None


def project_option(project: Path | None) -> str:
    """The ``--project`` option that selects ``project``'s install in a suggested command; empty for personal."""
    return f" --project {project}" if project is not None else ""


def managed_command(name: str, project: Path) -> str:
    """This CLI's Copilot command ``name`` for ``project``, as the scope warnings suggest it.

    The Copilot package's ``setup`` is this CLI's ``install``; other names match.
    """
    return f"watcher-sdk integrations {'install' if name == 'setup' else name} copilot --project {project}"


def redirected_message(project: Path | None) -> str:
    return (
        "The hooks and the private configuration name different Watcher servers, so the hooks refuse to run. "
        f"Run watcher-sdk integrations install copilot{project_option(project)} with --cloud or --url "
        "to choose the server again."
    )


def installation(
    project: Path | None, config_dir: Path | None, *, allow_server_mismatch: bool = False
) -> CopilotInstallation | None:
    """Read the personal install, or ``project``'s, without network access; ``None`` when there is none.

    An earlier API-key installation stays readable here so status can name it and
    install can replace it with a sign-in; its hooks refuse to run. By default a
    configuration that names more than one server, through its hook commands or
    its sign-in (see ``names_another_server``), is refused with ``CommandError``, as
    the hooks refuse it, so it never chooses the server a command uses or where
    its sign-in goes. ``allow_server_mismatch`` reads it anyway: install and
    update set it only when the user names the server, and status and doctor set
    it to report the mismatch.
    """
    from watcher_github_copilot_cli.configuration import (
        bound_server,
        configuration_path,
        hook_file,
        load_configuration,
        names_another_server,
    )

    project = _resolved(project)
    path = configuration_path(project, config_dir)
    if not path.exists():
        return None
    config = load_configuration(path, allow_legacy_credentials=True, allow_server_mismatch=True)
    redirected = names_another_server(config)
    if redirected and not allow_server_mismatch:
        raise CommandError(redirected_message(project))
    auth: IntegrationAuth | None
    if config.auth_profile is not None:
        auth = config.auth_profile
    elif config.watcher_auth:
        # Watcher's saved sign-in is chosen by server, and a redirected configuration's
        # server is whatever rewrote it (see ``CopilotInstallation``).
        auth = (
            None
            if redirected
            else IntegrationAuth(base_url=config.watcher_url, kind="watcher_login", state_dir=config.watcher_state_dir)
        )
    elif config.api_key_file is not None:
        auth = IntegrationAuth(base_url=config.watcher_url, kind="api_key_file", key_file=config.api_key_file)
    else:
        auth = IntegrationAuth(base_url=config.watcher_url, kind="api_key_env", key_env=config.api_key_env)
    # Pydantic runs IntegrationAuth's own checks again when ``auth`` goes into this
    # model, so a redirected configuration's sign-in needs the same leniency here as
    # when the configuration was read.
    return CopilotInstallation.model_validate(
        {
            "config": path,
            "auth": auth,
            "reviews_tools": config.gate is not None,
            "project": config.project,
            "hook_file": hook_file(config),
            "hook_server": bound_server(config.hook.args),
            "redirected": redirected,
        },
        context={ALLOW_INSECURE_LOGIN_URL: redirected},
    )


def require_installation(
    project: Path | None, config_dir: Path | None, *, allow_server_mismatch: bool = False
) -> CopilotInstallation:
    """The installation ``installation`` reads, or ``CommandError`` naming the install command when there is none."""
    current = installation(project, config_dir, allow_server_mismatch=allow_server_mismatch)
    if current is None:
        if project is None:
            raise CommandError(
                "No personal Copilot integration is installed. Run watcher-sdk integrations install copilot, "
                "or add --project for a project's own install."
            )
        raise CommandError(
            "No Copilot integration is installed for this project. "
            f"Run watcher-sdk integrations install copilot{project_option(_resolved(project))}."
        )
    return current


def install(
    project: Path | None,
    target: str | None,
    *,
    config_dir: Path | None,
    watcher_auth: bool,
    fresh_login: bool,
    state_dir: Path | None,
    watcher_state_dir: Path | None,
    enforce: bool,
    record_only: bool,
) -> None:
    """Verify server access, then install the personal hooks, or ``project``'s; retain existing mode and auth.

    ``target`` is the server the user named with --cloud or --url, if any. Only a
    named server repairs a configuration redirected to another server, so a
    rewritten configuration never chooses where setup signs in.
    """
    from watcher_github_copilot_cli.configuration import (
        exclude_hook_from_git,
        hook_file,
        install_observer,
        load_configuration,
        loading_warnings,
    )
    from watcher_github_copilot_cli.scopes import overlap_warnings

    if enforce and record_only:
        raise CommandError("Choose --enforce or --record-only, not both.")
    if project is not None:
        project = project.expanduser().resolve(strict=True)
    current = installation(project, config_dir, allow_server_mismatch=target is not None)
    profile = resolve_profile(
        target,
        current.auth if current is not None else None,
        project=project,
        watcher_auth=watcher_auth,
        fresh_login=fresh_login,
        state_dir=state_dir,
        watcher_state_dir=watcher_state_dir,
    )
    if project is not None:
        profile.login_auth().validate_project_location(project)
    profile.validate_local()
    asyncio.run(verify_integration_auth(profile))
    path = install_observer(
        project,
        profile.base_url,
        config_dir,
        False if record_only else True if enforce else None,
        auth_profile=profile,
    )
    config = load_configuration(path)
    if project is None:
        typer.echo(f"Installed Copilot hooks for every Copilot session of this user: {hook_file(config)}")
    else:
        exclude_hook_from_git(project)
        typer.echo(f"Installed Copilot hooks for {project}")
    typer.echo(f"Server access verified: {profile.base_url}\nPrivate configuration: {path}")
    for warning in [*loading_warnings(project), *overlap_warnings(config, path.parent.parent, command=managed_command)]:
        typer.echo(f"Warning: {warning}")
    typer.echo(
        f"Restart Copilot{' and trust this project' if project is not None else ''}. Complete a turn, "
        f"then run watcher-sdk integrations status copilot{project_option(project)}."
    )
    typer.echo("Recording is not confirmed until a hook uploads a session and reads it back.")


def _explain_check_failure(failure: str | None) -> None:
    if failure == "authentication":
        typer.echo("Watcher rejected the credential while reading judgments back. Sign in again.")
    elif failure == "review":
        typer.echo("Some stored judgments did not match the gate's answer, or could not be read back in time.")


def _show_judgments(config: Path) -> None:
    """Print the hooks' last read-back of stored judgments, which a confirmed transcript does not imply."""
    from watcher_github_copilot_cli.diagnostics import read_status

    result = read_status(config)
    check = result.last_review_check
    if check is None:
        typer.echo("Stored judgments: not read back yet")
    else:
        scope = f"Copilot session {check.native_session}" if check.native_session is not None else "all sessions"
        typer.echo(
            f"Stored judgments: read back at {check.at} for {scope}: {check.confirmed} confirmed, "
            f"{check.unconfirmed} unconfirmed, {check.skipped} not stored while paused"
        )
        typer.echo(
            f"Calls judged without storing: {check.gaps} in that session, {check.unscoped_gaps} in an unknown session"
        )
        _explain_check_failure(check.failure)
    if result.last_review_gap is not None:
        typer.echo(f"Last call judged without storing: {result.last_review_gap.at} ({result.last_review_gap.reason})")


def _read_back(current: CopilotInstallation) -> bool:
    """Read the stored judgments of every retained receipt back once now and print the result.

    Returns False only when the hooks' receipts themselves could not be read.
    Only reads: nothing is graded, judged or stored in Watcher, and the hooks'
    own diagnostics keep their last check. A receipt whose judgment is never
    found, such as one from a session the server deleted, is read once and
    counted as unconfirmed.
    """
    from watcher_github_copilot_cli.diagnostics import ReviewCheck
    from watcher_github_copilot_cli.reviews import confirm_reviews

    async def check() -> ReviewCheck:
        async with current.credential().create_client() as client:
            return await confirm_reviews(
                client, current.config, native_session=None, timeout=READBACK_SECONDS, record=False, repeat=False
            )

    result = asyncio.run(check())
    if result.confirmed + result.unconfirmed + result.skipped == 0:
        # With no receipt counted, a failure can only have come from reading the
        # receipts themselves, before any request to Watcher.
        if result.failure is not None:
            typer.echo("Stored judgments read back now: failed, because the hooks' receipts could not be read")
            return False
        typer.echo("Stored judgments read back now: none to check")
        return True
    typer.echo(
        f"Stored judgments read back now: {result.confirmed} confirmed, {result.unconfirmed} unconfirmed, "
        f"{result.skipped} not stored while paused"
    )
    _explain_check_failure(result.failure)
    return True


def status(project: Path | None, config_dir: Path | None, *, verify: bool) -> None:
    """Report scope, hook integrity, transcript delivery and stored judgments; doctor also checks server access.

    A redirected configuration is named, with the command that repairs it,
    instead of failing as unreadable; doctor then stops before any request.
    Doctor also fails when the hooks are missing or changed, or name no server,
    as hooks from earlier versions do, and when it cannot read the hooks'
    receipts. Its read-back of stored judgments only reads (see ``_read_back``).
    """
    from watcher_github_copilot_cli.configuration import (
        hooks_installed,
        hooks_without_server,
        load_configuration,
        loading_warnings,
    )
    from watcher_github_copilot_cli.diagnostics import read_status
    from watcher_github_copilot_cli.scopes import overlap_warnings

    current = require_installation(project, config_dir, allow_server_mismatch=True)
    config = load_configuration(current.config, allow_legacy_credentials=True, allow_server_mismatch=True)
    if current.project is None:
        typer.echo("Scope: personal, every Copilot session of this user")
    else:
        typer.echo(f"Scope: project {current.project}")
    typer.echo(f"Hook file: {current.hook_file}")
    intact = hooks_installed(config)
    try:
        unbound = hooks_without_server(current.config, config)
    except (OSError, ValueError):
        # An unreadable or redirected hook file is already reported as not installed.
        unbound = False
    if not intact:
        typer.echo("Hooks: missing, changed, disabled or holding other entries")
    elif unbound:
        typer.echo("Hooks: need setup again")
    else:
        typer.echo("Hooks: installed")
    if unbound:
        typer.echo(
            "Warning: These hooks do not name their Watcher server, so they cannot refuse a configuration "
            "redirected to another server. Run watcher-sdk integrations install copilot"
            f"{project_option(current.project)} to update them.",
            err=True,
        )
    # Without ``auth``, the configuration uses Watcher's saved sign-in for its own server (see ``CopilotInstallation``).
    login = current.auth.base_url if current.auth is not None else config.watcher_url
    kind = current.auth.kind if current.auth is not None else "watcher_login"
    if current.redirected:
        # Under the lenient read these come from a configuration something rewrote,
        # so they lose characters that could rewrite the terminal.
        typer.echo(
            f"Server: the hooks name {printable(current.hook_server or 'no server')}, the private configuration "
            f"names {printable(config.watcher_url)}, and its sign-in belongs to {printable(login)}."
        )
        typer.echo(redirected_message(current.project))
    else:
        typer.echo(f"Server: {login}")
    typer.echo(f"Credentials: {kind}")
    legacy = kind not in LOGIN_KINDS
    if legacy:
        typer.echo(
            "API keys are no longer supported; these hooks withhold tools and do not record. "
            f"Run watcher-sdk integrations install copilot{project_option(current.project)} to sign in instead."
        )
    typer.echo(f"Tool review: {'enabled (server policy applies)' if current.reviews_tools else 'recording only'}")
    if current.project is None:
        typer.echo(f"Opted-out projects: {', '.join(map(str, config.opted_out)) or 'none'}")
    result = read_status(current.config)
    typer.echo(f"Last hook callback: {result.last_callback or 'none'}")
    delivery = f"{result.last_delivery} (the transcript only)" if result.last_delivery else "not yet confirmed"
    typer.echo(f"Confirmed delivery: {delivery}")
    if result.last_session is not None:
        typer.echo(f"Watcher session: {result.last_session}")
    _show_judgments(current.config)
    if result.last_error is not None:
        typer.echo(f"Last failure: {result.last_error.failure} at {result.last_error.at}")
        if result.last_error.failure == "authentication":
            typer.echo(
                "Sign in again to the selected credential store, then run watcher-sdk integrations doctor copilot"
                f"{project_option(current.project)}."
            )
    for warning in overlap_warnings(config, current.config.parent.parent, command=managed_command):
        typer.echo(f"Warning: {warning}")
    if verify:
        if current.redirected:
            raise CommandError(redirected_message(current.project))
        if legacy:
            raise CommandError(
                "Replace the API-key installation with watcher-sdk integrations install copilot"
                f"{project_option(current.project)}."
            )
        current.credential().validate_local()
        asyncio.run(verify_integration_auth(current.credential()))
        typer.echo("Server access: verified")
        for warning in loading_warnings(config.project):
            typer.echo(f"Warning: {warning}")
        receipts_read = _read_back(current)
        if not intact or unbound or not Path(config.hook.exec).is_file():
            raise CommandError(
                "Repair this installation with watcher-sdk integrations install copilot"
                f"{project_option(current.project)}."
            )
        if not receipts_read:
            raise CommandError(
                f"Doctor could not read the hooks' receipts in {current.config.parent}. Check that events.jsonl and "
                "events.previous.jsonl there are regular files this user can read, then run watcher-sdk integrations "
                f"doctor copilot{project_option(current.project)} again."
            )


def logs(project: Path | None, config_dir: Path | None, limit: int) -> None:
    """Print the newest ``limit`` hook events, oldest first, across the current and rotated log.

    A partly written or corrupt line is skipped and counted rather than hiding the
    events around it.
    """
    from pydantic import ValidationError
    from watcher_github_copilot_cli.diagnostics import HookEvent

    current = require_installation(project, config_dir)
    path = current.config.with_name("events.jsonl")
    lines: list[str] = []
    for log in (path.with_suffix(".previous.jsonl"), path):
        if log.exists():
            lines.extend(log.read_text(errors="replace").splitlines())
    if not lines:
        typer.echo("No hook events recorded yet.")
        return
    skipped = 0
    for line in lines[-limit:]:
        try:
            typer.echo(HookEvent.model_validate_json(line).model_dump_json())
        except ValidationError:
            skipped += 1
    if skipped:
        typer.echo(f"Skipped {skipped} unreadable log line{'s' if skipped > 1 else ''}.")


def remove(project: Path | None, config_dir: Path | None) -> None:
    """Remove the personal hooks, with their opt-outs, or ``project``'s; keep saved sign-ins and unrelated hooks."""
    from watcher_github_copilot_cli.configuration import remove_observer

    removed = remove_observer(project, config_dir)
    typer.echo("Copilot hooks removed. Saved sign-ins are retained." if removed else "No Copilot hooks found.")


def opt_out(project: Path, config_dir: Path | None, *, opted_out: bool) -> None:
    """Opt ``project`` out of every Copilot hook this integration installed, or back in.

    The choice is stored only in the personal install's private configuration,
    never in the project, so it needs the personal install. It applies to the
    project as Copilot finds it: the innermost Git repository's root, or the
    folder itself outside Git. That root is found once, and exactly the root a
    person confirms at an interactive terminal by typing it is written, as the
    Copilot package's own commands do (see its ``terminal_confirms``), so an
    agent's ordinary shell command cannot change it. Opting out also warns about
    a project install there whose hooks run another Python, which may ignore
    opt-outs.
    """
    from watcher_github_copilot_cli.cli import terminal_confirms
    from watcher_github_copilot_cli.configuration import configuration_path, project_root, set_opt_out
    from watcher_github_copilot_cli.scopes import stale_install_warnings

    personal = configuration_path(None, config_dir)
    if not personal.exists():
        raise CommandError(
            "Opting a project out needs the personal install, which stores the choice. "
            "Run watcher-sdk integrations install copilot first."
        )
    try:
        root = project_root(project.expanduser().resolve(strict=opted_out))
    except (OSError, RuntimeError):
        raise CommandError(
            f"Name {'an existing folder' if opted_out else 'a folder'} whose project can be found. Nothing changed."
        ) from None
    if not terminal_confirms("Opting a project out" if opted_out else "Opting a project back in", root):
        raise typer.Exit(1)
    changed = set_opt_out(root, config_dir, opted_out=opted_out)
    if opted_out:
        typer.echo(
            f"Copilot hooks now leave {root} alone, the personal install's and any project install's."
            if changed
            else f"{root} was already opted out."
        )
        for warning in stale_install_warnings(personal.parent.parent, root, command=managed_command):
            typer.echo(f"Warning: {warning}")
    else:
        typer.echo(f"Copilot hooks cover {root} again." if changed else f"{root} was not opted out.")


def update(project: Path | None, config_dir: Path | None, version: str | None, target: str | None = None) -> None:
    """Run the bundled bootstrap; setup keeps the installed scope, credential and mode.

    The installer reinstalls against ``target`` when the user names a server,
    which also repairs a redirected configuration, and otherwise against the
    installed server.
    """
    current = require_installation(project, config_dir, allow_server_mismatch=target is not None)
    source = Path(sys.prefix).parent.parent.parent
    script = source / "install.sh"
    # Every extracted source archive ships install.sh in an sdk/ folder, so only the
    # installer's own <root>/releases/<X.Y.Z>/sdk layout identifies a managed install.
    # Anything else would make the bootstrap create its runtime in an unrelated folder.
    managed = (
        script.is_file()
        and source.name == "sdk"
        and re.fullmatch(r"\d+\.\d+\.\d+", source.parent.name) is not None
        and source.parent.parent.name == "releases"
    )
    if not managed:
        raise CommandError("This command is not in a managed installation. Re-run the SDK release installer to update.")
    command = Path(sys.argv[0]).expanduser().absolute()  # noqa: APE015
    if command.name != "watcher-sdk" or command.resolve() != (Path(sys.prefix) / "bin/watcher-sdk").resolve():
        raise CommandError("Run the watcher-sdk command from this managed installation to update it.")
    args = ["bash", str(script), "copilot", "--url", target or current.credential().base_url]
    if project is not None:
        args.extend(["--project", str(project.expanduser().resolve())])
    if config_dir is not None:
        args.extend(["--config-dir", str(config_dir.expanduser().resolve())])
    if version is not None:
        args.extend(["--version", version])
    environment = os.environ.copy()
    # A download override left in the user's shell would silently become the source of
    # both the release archive and its checksum, so update always uses the public release.
    environment.pop("WATCHER_SDK_DOWNLOAD_BASE", None)
    environment["WATCHER_SDK_INSTALL_ROOT"] = str(source.parent.parent.parent)
    environment["WATCHER_SDK_BIN_DIR"] = str(command.parent)
    result = subprocess.run(args, check=False, env=environment)
    if result.returncode:
        raise CommandError("Update failed. The previous hooks remain available; check the installer output.")
