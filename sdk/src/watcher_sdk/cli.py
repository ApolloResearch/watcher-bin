"""Manage SDK browser sign-ins without a local Watcher application."""

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
app.add_typer(auth_app, name="auth", help="Manage SDK-owned browser sign-ins.")


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
            message = "The Watcher request failed. Check the server URL, connection and sign-in, then retry."
        except ImportError:
            message = "A required SDK dependency is unavailable. Reinstall the SDK with [cli]."
        except (OSError, ValueError, KeyError) as error:
            # These refusals are fixed SDK text, so they are shown; other errors may quote external data.
            displayable = displayable_error(error)
            message = (
                str(displayable)
                if displayable is not None
                else "Check the server URL and private credential source, then retry."
            )
        except (TypeError, AttributeError):
            # A defect in the SDK, such as a version skew after an update;
            # reporting it as a connection problem would send the user the wrong way.
            message = "The Watcher SDK hit an unexpected error. Reinstall the SDK, then retry."
        typer.echo(message, err=True)
        raise typer.Exit(1)

    return run


@app.command("help", hidden=True)
@auth_app.command("help", hidden=True)
def help_command(ctx: typer.Context) -> None:
    typer.echo(ctx.parent.get_help() if ctx.parent is not None else ctx.get_help())


@auth_app.command("login")
@command_errors
def login_command(
    cloud: Annotated[bool, typer.Option(help="Use Watcher Cloud.")] = False,
    url: Annotated[str | None, typer.Option(help="Self-hosted Watcher server URL.")] = None,
    state_dir: Annotated[Path | None, typer.Option(help="Private SDK credential directory.")] = None,
) -> None:
    """Sign in through the browser and save SDK-owned credentials."""
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
    """List saved SDK and Watcher sign-ins, and verify each selected server."""
    candidates = discover_logins(server_url(cloud, url), state_dir=state_dir)
    if not candidates:
        typer.echo("No saved sign-in found. Run watcher-sdk auth login --cloud or --url URL.")
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
            typer.echo("Server access: request failed. Check the server URL, connection and sign-in.", err=True)
            has_failure = True
        else:
            typer.echo("Server access: verified")
    if has_failure:
        raise typer.Exit(1)


@auth_app.command("logout")
@command_errors
def logout_command(cloud: bool = False, url: str | None = None, state_dir: Path | None = None) -> None:
    """End the SDK sign-in's server session and remove it; a browser or app sharing that session may sign out too."""
    target = server_url(cloud, url)
    if target is None:
        candidates = [profile for profile in discover_logins(state_dir=state_dir) if profile.kind == "sdk_login"]
        if not candidates:
            typer.echo("No SDK sign-in found. Watcher app sign-ins are unchanged.")
            return
        selected = choose_profile(candidates)
        target, state_dir = selected.base_url, selected.state_dir
    removed = asyncio.run(logout(target, state_dir=state_dir))
    typer.echo(
        "SDK sign-in removed. The Watcher app's saved sign-in file was left in place."
        if removed
        else "No SDK sign-in found."
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
