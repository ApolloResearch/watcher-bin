"""Sign in and manage SDK integrations without a local Watcher application."""

import asyncio
from collections.abc import Callable
from functools import partial, wraps
from pathlib import Path
from typing import Annotated

import httpx
from pydantic import ValidationError

try:
    import typer
except ModuleNotFoundError as error:
    if error.name != "typer":
        raise
    raise SystemExit(
        "The Watcher SDK CLI needs optional dependencies. Reinstall your SDK wheel or source with [cli]."
    ) from None

from watcher_sdk.cli_auth import CommandError, choose_profile, server_url, show_authorization
from watcher_sdk.errors import WatcherAuthenticationError, WatcherError
from watcher_sdk.integration_auth import CLOUD_URL, discover_logins, verify_integration_auth
from watcher_sdk.local_auth import InsecureLoginURLError, LinkedCredentialFolderError, UnsafeLoginStoreError
from watcher_sdk.login import login, logout

app = typer.Typer(no_args_is_help=True, invoke_without_command=True, pretty_exceptions_enable=False)
auth_app = typer.Typer(no_args_is_help=True, invoke_without_command=True, pretty_exceptions_enable=False)
integrations_app = typer.Typer(no_args_is_help=True, invoke_without_command=True, pretty_exceptions_enable=False)
app.add_typer(auth_app, name="auth", help="Manage SDK-owned browser logins.")
app.add_typer(integrations_app, name="integrations", help="Manage integrations for every session or one project.")

ProjectOption = Annotated[
    Path | None,
    typer.Option(help="Use this project's own install instead of the personal one, which covers every session."),
]
ConfigDirOption = Annotated[Path | None, typer.Option(help="Private adapter configuration root.")]


# Refusals whose messages are fixed SDK text without paths or credentials, so the
# command shows them instead of a generic hint: they name the exact cause to fix.
DISPLAYABLE_ERRORS = (InsecureLoginURLError, LinkedCredentialFolderError, UnsafeLoginStoreError)


def displayable_error(error: Exception) -> Exception | None:
    """The refusal with fixed text behind ``error`` (see ``DISPLAYABLE_ERRORS``), including one inside validation."""
    if isinstance(error, DISPLAYABLE_ERRORS):
        return error
    if isinstance(error, ValidationError):
        for detail in error.errors():
            cause = detail.get("ctx", {}).get("error")
            if isinstance(cause, DISPLAYABLE_ERRORS):
                return cause
    return None


def command_errors[**P](function: Callable[P, None]) -> Callable[P, None]:
    """Keep external exceptions and credential values out of terminal diagnostics."""

    @wraps(function)
    def run(*args: P.args, **kwargs: P.kwargs) -> None:
        message: str
        try:
            function(*args, **kwargs)
            return
        except CommandError as error:
            message = str(error)
        except WatcherAuthenticationError:
            message = (
                "Authentication or permission check failed. Sign in to the selected server and credential store "
                "again, or check the API key's permissions. No alternative credential was selected."
            )
        except (httpx.HTTPError, WatcherError, TimeoutError):
            message = "The Watcher request failed. Check the server URL, connection and login, then retry."
        except ImportError:
            message = "The Copilot package is unavailable. Install it using the SDK release installer."
        except (OSError, ValueError, KeyError) as error:
            # These refusals are fixed SDK text, so they are shown; other errors may quote external data.
            displayable = displayable_error(error)
            message = (
                str(displayable)
                if displayable is not None
                else "Check the project, server URL, private credential source and hook ownership, then retry."
            )
        except (TypeError, AttributeError):
            # A defect in the SDK or adapter, such as a version skew after an update;
            # reporting it as a connection problem would send the user the wrong way.
            message = "The Watcher SDK hit an unexpected error. Re-run the SDK release installer, then retry."
        typer.echo(message, err=True)
        raise typer.Exit(1)

    return run


@app.command("help", hidden=True)
@auth_app.command("help", hidden=True)
@integrations_app.command("help", hidden=True)
def help_command(ctx: typer.Context) -> None:
    typer.echo(ctx.parent.get_help() if ctx.parent is not None else ctx.get_help())


@auth_app.command("login")
@command_errors
def login_command(
    cloud: Annotated[bool, typer.Option(help="Use Watcher Cloud.")] = False,
    url: Annotated[str | None, typer.Option(help="Self-hosted Watcher server URL.")] = None,
    state_dir: Annotated[Path | None, typer.Option(help="Private SDK credential directory.")] = None,
) -> None:
    """Sign in through the browser and store an SDK-owned login."""
    target = server_url(cloud, url) or CLOUD_URL
    profile = asyncio.run(login(target, partial(show_authorization, target), state_dir=state_dir))
    typer.echo(f"Signed in to {profile.base_url}. SDK credentials: {profile.state_dir}")


@auth_app.command("status")
@command_errors
def auth_status_command(
    cloud: bool = False,
    url: str | None = None,
    state_dir: Path | None = None,
) -> None:
    """List saved SDK and Watcher logins, and verify each selected server."""
    candidates = discover_logins(server_url(cloud, url), state_dir=state_dir)
    if not candidates:
        typer.echo("No saved login found. Run watcher-sdk auth login --cloud or --url URL.")
        return
    has_failure = False
    for profile in candidates:
        typer.echo(f"{profile.base_url} ({profile.kind}, {profile.state_dir})")
        try:
            asyncio.run(verify_integration_auth(profile))
        except WatcherAuthenticationError:
            typer.echo("Server access: authentication or permission check failed.", err=True)
            has_failure = True
        except (httpx.HTTPError, WatcherError, TimeoutError, OSError, ValueError, KeyError):
            typer.echo("Server access: request failed. Check the server URL, connection and login.", err=True)
            has_failure = True
        else:
            typer.echo("Server access: verified")
    if has_failure:
        raise typer.Exit(1)


@auth_app.command("logout")
@command_errors
def logout_command(cloud: bool = False, url: str | None = None, state_dir: Path | None = None) -> None:
    """End the SDK login's server session and remove it; a browser or app sharing that session may sign out too."""
    target = server_url(cloud, url)
    if target is None:
        candidates = [profile for profile in discover_logins(state_dir=state_dir) if profile.kind == "sdk_login"]
        if not candidates:
            typer.echo("No SDK login found. Watcher app logins are unchanged.")
            return
        selected = choose_profile(candidates)
        target, state_dir = selected.base_url, selected.state_dir
    removed = asyncio.run(logout(target, state_dir=state_dir))
    typer.echo(
        "SDK login removed. The Watcher app's saved login file was left in place." if removed else "No SDK login found."
    )


def require_copilot(integration: str) -> None:
    if integration != "copilot":
        raise CommandError("Supported integration: copilot.")


@integrations_app.command("install")
@command_errors
def install_command(
    integration: Annotated[str, typer.Argument(help="Integration name: copilot.")],
    project: Annotated[
        Path | None,
        typer.Option(help="Install in this project only. By default, hooks cover every Copilot session of this user."),
    ] = None,
    cloud: Annotated[bool, typer.Option(help="Use Watcher Cloud.")] = False,
    url: Annotated[str | None, typer.Option("--url", "--watcher-url", help="Self-hosted server URL.")] = None,
    watcher_auth: Annotated[bool, typer.Option(help="Use the local Watcher app's saved login.")] = False,
    fresh_login: Annotated[bool, typer.Option("--login", help="Create or replace an SDK-owned browser login.")] = False,
    state_dir: Annotated[Path | None, typer.Option(help="Private SDK credential directory.")] = None,
    watcher_state_dir: Annotated[Path | None, typer.Option(help="Watcher app credential directory.")] = None,
    config_dir: ConfigDirOption = None,
    record_only: Annotated[bool, typer.Option(help="Record without tool review.")] = False,
    enforce: Annotated[bool, typer.Option(help="Enable tool review. New installs enable it by default.")] = False,
    version: Annotated[str | None, typer.Option(hidden=True)] = None,
) -> None:
    """Verify access and install hooks for every Copilot session, or one project's, preserving mode and credentials."""
    from watcher_sdk.cli_copilot import install

    require_copilot(integration)
    install(
        project,
        server_url(cloud, url),
        config_dir=config_dir,
        watcher_auth=watcher_auth,
        fresh_login=fresh_login,
        state_dir=state_dir,
        watcher_state_dir=watcher_state_dir,
        enforce=enforce,
        record_only=record_only,
    )


@integrations_app.command("status")
@command_errors
def status_command(integration: str, project: ProjectOption = None, config_dir: ConfigDirOption = None) -> None:
    """Show the installed hooks, confirmed transcript delivery and stored judgments, and any duplicate install."""
    from watcher_sdk.cli_copilot import status

    require_copilot(integration)
    status(project, config_dir, verify=False)


@integrations_app.command("doctor")
@command_errors
def doctor_command(integration: str, project: ProjectOption = None, config_dir: ConfigDirOption = None) -> None:
    """Check hooks, credentials and server access, and read stored judgments back without grading anything."""
    from watcher_sdk.cli_copilot import status

    require_copilot(integration)
    status(project, config_dir, verify=True)


@integrations_app.command("logs")
@command_errors
def logs_command(
    integration: str,
    project: ProjectOption = None,
    config_dir: ConfigDirOption = None,
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 20,
) -> None:
    """Show recent sanitized hook events, including detached recording failures."""
    from watcher_sdk.cli_copilot import logs

    require_copilot(integration)
    logs(project, config_dir, limit)


@integrations_app.command("remove")
@command_errors
def remove_command(integration: str, project: ProjectOption = None, config_dir: ConfigDirOption = None) -> None:
    """Remove the owned hooks, retaining unrelated hooks and saved logins; personal removal deletes opt-outs."""
    from watcher_sdk.cli_copilot import remove

    require_copilot(integration)
    remove(project, config_dir)


@integrations_app.command("update")
@command_errors
def update_command(
    integration: str,
    project: ProjectOption = None,
    config_dir: ConfigDirOption = None,
    version: str | None = None,
    cloud: Annotated[bool, typer.Option(help="Reinstall against Watcher Cloud.")] = False,
    url: Annotated[
        str | None, typer.Option("--url", "--watcher-url", help="Reinstall against this self-hosted server.")
    ] = None,
) -> None:
    """Install the server's SDK release and update the hooks, against the installed server unless one is named."""
    from watcher_sdk.cli_copilot import update

    require_copilot(integration)
    update(project, config_dir, version, server_url(cloud, url))


@integrations_app.command("opt-out")
@command_errors
def opt_out_command(
    integration: str,
    project: Annotated[Path, typer.Option(help="Project the hooks should leave alone, its own install included.")],
    config_dir: ConfigDirOption = None,
) -> None:
    """Stop every installed Copilot hook from recording or judging anything in this project.

    Asks you to confirm at an interactive terminal by typing the project folder.
    An agent's ordinary shell command has no terminal, so it is refused, although
    a process running as you can still fake one or edit the configuration.
    """
    from watcher_sdk.cli_copilot import opt_out

    require_copilot(integration)
    opt_out(project, config_dir, opted_out=True)


@integrations_app.command("opt-in")
@command_errors
def opt_in_command(
    integration: str,
    project: Annotated[Path, typer.Option(help="Opted-out project the hooks should cover again.")],
    config_dir: ConfigDirOption = None,
) -> None:
    """Let the installed Copilot hooks record and judge this project again.

    Asks you to confirm at an interactive terminal by typing the project folder,
    as opt-out does.
    """
    from watcher_sdk.cli_copilot import opt_out

    require_copilot(integration)
    opt_out(project, config_dir, opted_out=False)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
