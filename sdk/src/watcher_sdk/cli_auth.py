"""Select saved SDK sign-ins and display browser authorization instructions."""

import sys
import webbrowser

import httpx
import typer

from watcher_sdk.integration_auth import CLOUD_URL, IntegrationAuth
from watcher_sdk.local_auth import _api_url
from watcher_sdk.login import DeviceLoginPrompt


class CommandError(Exception):
    """An actionable, credential-free message safe to display in the terminal."""


def server_url(cloud: bool, url: str | None) -> str | None:
    if cloud and url is not None:
        raise CommandError("Choose --cloud or --url, not both.")
    selected = CLOUD_URL if cloud else url
    return str(_api_url(selected)) if selected is not None else None


def printable(text: str) -> str:
    """Drop characters that could move the cursor, recolor or reorder terminal text."""
    return "".join(character for character in text if character.isprintable())


def show_authorization(server: str, prompt: DeviceLoginPrompt) -> None:
    """Show device sign-in instructions that end by naming the server receiving the sign-in.

    A hostile server can relay another server's genuine approval page and code,
    and the approval page cannot tell the user who asked. Naming the destination
    in the terminal is the only place the user can spot that. The server line
    comes last, after the server-supplied link and code, so however long those
    are they cannot scroll it out of view. The host is shown in its ASCII form so
    look-alike Unicode names stand out, and server-supplied text loses
    non-printable characters so it cannot rewrite the terminal.
    """
    url = printable(prompt.url)
    typer.echo(
        f"Sign in at {url}\nApproval code: {printable(prompt.user_code)}\n"
        f"Signing in to the Watcher server at {printable(httpx.URL(server).netloc.decode('ascii'))}.\n"
        "Approve only if you started this sign-in and trust that server: it receives access to your account."
    )
    webbrowser.open(url)


def choose_profile(candidates: list[IntegrationAuth]) -> IntegrationAuth:
    """Require a terminal choice when more than one saved source matches."""
    if len(candidates) == 1:
        return candidates[0]
    if not sys.stdin.isatty():
        raise CommandError(
            "Several saved sign-ins match. Run in a terminal to choose one, or select an explicit source."
        )
    for index, candidate in enumerate(candidates, 1):
        typer.echo(f"{index}. {candidate.base_url} ({candidate.kind}, {candidate.state_dir})")

    def parse_selection(value: str) -> int:
        message = f"Choose a number from 1 to {len(candidates)}."
        try:
            selected = int(value)
        except ValueError:
            raise typer.BadParameter(message) from None
        if not 1 <= selected <= len(candidates):
            raise typer.BadParameter(message)
        return selected

    selected: int = typer.prompt("Use sign-in", value_proc=parse_selection)
    return candidates[selected - 1]
