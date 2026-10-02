"""Configure observation, for every Copilot session or one project, and replay completed sessions."""

import asyncio
import sys
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

import typer

from watcher_github_copilot_cli.configuration import (
    configuration_path,
    exclude_hook_from_git,
    hook_file,
    hooks_installed,
    hooks_without_server,
    in_git_repository,
    install_observer,
    load_auth_profile,
    load_configuration,
    loading_warnings,
    project_root,
    remove_observer,
    set_opt_out,
)
from watcher_github_copilot_cli.diagnostics import HookStatus, read_status
from watcher_github_copilot_cli.integration import app, observe_callback, recording_failure, watcher_settings
from watcher_github_copilot_cli.recording import PartialRecordingError, RecordedSession
from watcher_github_copilot_cli.scopes import overlap_warnings, stale_install_warnings
from watcher_sdk import WatcherAuthenticationError

ConfigDirOption = Annotated[Path | None, typer.Option(help="Configuration root used during setup.")]


class InstallationStatus(HookStatus):
    """What status prints: the installation's scope, whether its hooks are intact, and the hook status.

    ``scope`` is ``personal`` for the hooks in Copilot's personal hooks folder,
    which run in every folder, and ``project`` for one project's hooks.
    """

    scope: Literal["personal", "project"]
    hook_file: Path
    hooks_installed: bool
    opted_out: list[Path]


@app.command("setup")
def setup_command(
    watcher_url: Annotated[str, typer.Option(help="Watcher API base URL, including /api when required.")],
    project: Annotated[
        Path | None,
        typer.Option(help="Install in this project's .github/hooks instead of Copilot's personal hooks folder."),
    ] = None,
    config_dir: Annotated[Path | None, typer.Option(help="Configuration root outside the project.")] = None,
    enforce: Annotated[
        bool, typer.Option(help="Enable blocking review; new installations enable it by default.")
    ] = False,
    record_only: Annotated[bool, typer.Option(help="Install recording without blocking review.")] = False,
    watcher_auth: Annotated[
        bool, typer.Option(help="Reuse and refresh this user's saved Watcher login for the same API URL.")
    ] = False,
    watcher_state_dir: Annotated[
        Path | None, typer.Option(help="Saved Watcher login directory to bind to these hooks.")
    ] = None,
    auth_profile: Annotated[Path | None, typer.Option(hidden=True)] = None,
) -> None:
    """Install hooks for every Copilot session, or one project's, preserving an existing mode unless selected.

    Warns about any project that the personal install and the project's own
    install would both cover, without removing either.
    """
    if watcher_state_dir is not None and not watcher_auth:
        typer.echo("--watcher-state-dir requires --watcher-auth.", err=True)
        raise typer.Exit(2)
    try:
        if enforce and record_only:
            raise ValueError("Choose either --enforce or --record-only")
        path = install_observer(
            project,
            watcher_url,
            config_dir,
            False if record_only else True if enforce else None,
            watcher_auth,
            auth_profile=load_auth_profile(auth_profile) if auth_profile is not None else None,
            watcher_state_dir=watcher_state_dir,
        )
    except WatcherAuthenticationError as error:
        typer.echo(f"{error.message}, then run setup again.", err=True)
        raise typer.Exit(1) from None
    except (OSError, ValueError, KeyError):
        typer.echo(
            "Setup failed. Check the project, COPILOT_HOME, URL, credential source and existing hook ownership.",
            err=True,
        )
        raise typer.Exit(1) from None
    config = load_configuration(path)
    install = "Blocking review" if config.gate else "Record only"
    if project is None:
        typer.echo(f"Installed the {install} hooks for every Copilot session of this user: {hook_file(config)}")
        typer.echo(f"Configuration: {path}")
        warnings = loading_warnings(None)
    else:
        typer.echo(f"Installed the {install} hooks. Configuration: {path}")
        warnings = loading_warnings(project)
        resolved = project.expanduser().resolve()
        if not exclude_hook_from_git(resolved) and in_git_repository(resolved):
            warnings.append("Setup could not list the hook file in Git's local exclude file; do not commit it.")
    warnings += overlap_warnings(config, path.parent.parent)
    for warning in warnings:
        typer.echo(f"Warning: {warning}", err=True)
    typer.echo("API delivery is verified on the first completed turn.")


@app.command("status")
def status_command(
    config: Annotated[Path | None, typer.Option(help="Configuration written by setup.")] = None,
    project: Annotated[
        Path | None, typer.Option(help="Show this project's install instead of the personal one.")
    ] = None,
    config_dir: ConfigDirOption = None,
) -> None:
    """Show confirmed delivery separately from whether the hooks are installed.

    Also warns when the personal install and a project's own install both cover a project.
    """
    if config is None:
        config = configuration_path(project.expanduser().resolve() if project is not None else None, config_dir)
    try:
        configuration = load_configuration(config)
        status = read_status(config)
    except (OSError, ValueError):
        typer.echo(f"No configuration could be read at {config}. Run setup, or pass the path setup printed.", err=True)
        raise typer.Exit(1) from None
    report = InstallationStatus(
        **status.model_dump(),
        scope="personal" if configuration.project is None else "project",
        hook_file=hook_file(configuration),
        hooks_installed=hooks_installed(configuration),
        opted_out=configuration.opted_out,
    )
    typer.echo(report.model_dump_json(indent=2))
    if not report.hooks_installed:
        typer.echo(
            "Warning: Copilot's hook file for this installation is missing, changed, disabled or holds other entries. "
            "Move other hooks to their own file and run setup again.",
            err=True,
        )
    try:
        unbound = hooks_without_server(config.expanduser().resolve(), configuration)
    except (OSError, ValueError):
        typer.echo(
            f"Warning: Status could not read {report.hook_file}, so it did not check which server its hooks name.",
            err=True,
        )
        unbound = False
    if unbound:
        typer.echo(
            "Warning: These hooks do not name their Watcher server, so they cannot refuse a configuration "
            "redirected to another server. Run setup again to update them.",
            err=True,
        )
    for warning in overlap_warnings(configuration, config.parent.parent):
        typer.echo(f"Warning: {warning}", err=True)


@app.command("remove")
def remove_command(
    project: Annotated[
        Path | None, typer.Option(help="Remove this project's install instead of the personal one.")
    ] = None,
    config_dir: ConfigDirOption = None,
) -> None:
    """Remove only this sample's hooks and configuration; keep credentials and unrelated hooks."""
    try:
        removed = remove_observer(project, config_dir)
    except (OSError, ValueError):
        typer.echo(
            "Removal failed. Re-run setup for this installation, or restore any hand-edited hook entry, "
            "then remove again.",
            err=True,
        )
        raise typer.Exit(1) from None
    typer.echo("Hooks removed." if removed else "No installation found.")


def terminal_confirms(action: str, root: Path) -> bool:
    """Whether ``action`` for ``root`` was confirmed at an interactive terminal by typing ``root``.

    Copilot gives the commands its shell tool runs no terminal, so without one on
    both stdin and stdout this refuses, which stops an agent's ordinary command
    from turning this sample off. It is not proof that a person confirmed: a
    process running as the user can still fake a terminal, or edit the private
    configuration directly. Each refusal prints why.
    """
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        typer.echo(
            f"{action} needs an interactive terminal, where you confirm it by typing the folder. Commands an agent "
            "runs through Copilot's shell tool have none, so they are refused, although a process running as you "
            "can still fake a terminal or edit the configuration. Run it yourself in a terminal. Nothing changed.",
            err=True,
        )
        return False
    typed = typer.prompt(f"Type {root} to confirm", default="", show_default=False)
    if typed.strip() != str(root):
        typer.echo("The folder you typed did not match. Nothing changed.", err=True)
        return False
    return True


@app.command("opt-out")
def opt_out_command(
    project: Annotated[
        Path, typer.Option(help="Project this sample's hooks should leave alone, its own install included.")
    ],
    config_dir: ConfigDirOption = None,
) -> None:
    """Stop this sample's hooks, personal and project alike, from recording or judging anything in this project.

    Asks for confirmation at an interactive terminal, which an agent's ordinary
    shell command does not have (see ``terminal_confirms``). The project root is
    found once, and exactly the root confirmed is written; a folder whose root
    cannot be found is refused.
    """
    try:
        root = project_root(project.expanduser().resolve(strict=True))
    except (OSError, RuntimeError):
        typer.echo("Opt-out failed. Name an existing folder whose project can be found.", err=True)
        raise typer.Exit(1) from None
    if not terminal_confirms("Opting a project out", root):
        raise typer.Exit(1)
    try:
        changed = set_opt_out(root, config_dir, opted_out=True)
    except (OSError, ValueError):
        typer.echo("Opt-out failed. Install the personal hooks first.", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"This sample's hooks now leave {root} alone." if changed else f"{root} was already opted out.")
    for warning in stale_install_warnings(configuration_path(None, config_dir).parent.parent, root):
        typer.echo(f"Warning: {warning}", err=True)


@app.command("opt-in")
def opt_in_command(
    project: Annotated[Path, typer.Option(help="Opted-out project this sample's hooks should cover again.")],
    config_dir: ConfigDirOption = None,
) -> None:
    """Let this sample's hooks record and judge this project again.

    Asks for confirmation at an interactive terminal, which an agent's ordinary
    shell command does not have (see ``terminal_confirms``). The project root is
    found once, and exactly the root confirmed is removed, even for a folder that
    no longer exists.
    """
    try:
        root = project_root(project.expanduser().resolve())
    except (OSError, RuntimeError):
        typer.echo("Opt-in failed. Name a folder whose project can be found.", err=True)
        raise typer.Exit(1) from None
    if not terminal_confirms("Opting a project back in", root):
        raise typer.Exit(1)
    try:
        changed = set_opt_out(root, config_dir, opted_out=False)
    except (OSError, ValueError):
        typer.echo("Opt-in failed. Install the personal hooks first.", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"This sample's hooks cover {root} again." if changed else f"{root} was not opted out.")


async def _replay(config: Path, session_id: UUID) -> RecordedSession | None:
    settings = watcher_settings(config)
    async with settings.create_client() as client:
        return await observe_callback(
            client, {"sessionId": str(session_id), "reason": "replay"}, grade=False, config=config
        )


@app.command("replay")
def replay_command(
    config: Annotated[Path, typer.Option(help="Configuration path printed by setup.")],
    session_id: Annotated[UUID, typer.Option(help="Native Copilot session ID to replay.")],
) -> None:
    """Resend the session as it stands, including subagents, using the same session identities."""
    try:
        recorded = asyncio.run(_replay(config, session_id))
    except PartialRecordingError as error:
        _print_recorded(session_id, error.recorded)
        typer.echo(f"Watcher recording was not confirmed. {error}", err=True)
        raise typer.Exit(1) from None
    except Exception as error:
        typer.echo(f"Watcher recording was not confirmed: {recording_failure(error)}.", err=True)
        raise typer.Exit(1) from None
    if recorded is None:
        typer.echo("Nothing to record yet: the session has no assistant reply.", err=True)
        raise typer.Exit(1)
    _print_recorded(session_id, recorded)
    _print_review_check(config, session_id)


def _print_recorded(session_id: UUID, recorded: RecordedSession) -> None:
    typer.echo(f"Recording confirmed: github-copilot-cli:{session_id} -> Watcher session {recorded.session}")
    for agent_id, stored in recorded.subagents.items():
        typer.echo(f"Subagent confirmed: github-copilot-cli:{session_id}:agent:{agent_id} -> Watcher session {stored}")


def _print_review_check(config: Path, session_id: UUID) -> None:
    """Show the read-back of the gate's stored judgments, which a confirmed transcript does not imply."""
    try:
        check = read_status(config).last_review_check
    except (OSError, ValueError):
        check = None
    if check is None or check.native_session != session_id:
        typer.echo("Stored judgments: not checked; see the diagnostics beside the configuration.")
        return
    typer.echo(
        f"Stored judgments: {check.confirmed} confirmed, {check.unconfirmed} unconfirmed, "
        f"{check.skipped} not stored while paused"
    )
    typer.echo(
        f"Calls judged without storing: {check.gaps} in this session, {check.unscoped_gaps} in an unknown session"
    )
    if check.failure == "authentication":
        typer.echo("Watcher rejected the credential while reading judgments back. Sign in again, then replay.")
    elif check.failure == "review":
        typer.echo("Some stored judgments did not match the gate's answer, or could not be read back in time.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
