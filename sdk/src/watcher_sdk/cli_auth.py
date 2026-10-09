"""Resolve an explicit setup choice without changing identities after a request fails."""

import asyncio
import sys
import webbrowser
from functools import partial
from pathlib import Path

import httpx
import typer

from watcher_sdk.integration_auth import CLOUD_URL, IntegrationAuth, SDKLoginAuth, discover_logins
from watcher_sdk.local_auth import _api_url
from watcher_sdk.login import DeviceLoginPrompt, login


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


def resolve_profile(
    target: str | None,
    existing: IntegrationAuth | None,
    *,
    project: Path | None,
    watcher_auth: bool,
    fresh_login: bool,
    state_dir: Path | None,
    watcher_state_dir: Path | None,
) -> IntegrationAuth:
    """Select credentials once during setup; preserve a compatible existing choice.

    Integrations authenticate only with a user's own sign-in: an SDK sign-in or a
    saved Watcher sign-in. An existing API-key choice from an earlier version is
    never reused or rebuilt into a sign-in; its server is the destination only when
    ``target`` names none, and is checked then like any other. Explicit sources
    require a destination, either supplied or already installed. An explicit
    destination change never carries the previous credential across. Discovery
    occurs only without a saved choice. Only interactive setup starts browser
    sign-in; unattended installations must sign in in advance. A browser sign-in's
    store is checked to lie outside ``project``, when one is given, before
    anything is saved.
    """
    if watcher_auth and fresh_login:
        raise CommandError("Choose one credential source.")
    if watcher_state_dir is not None and not watcher_auth:
        raise CommandError("Use --watcher-auth with --watcher-state-dir.")
    selected_url = target or (existing.base_url if existing is not None else None)
    if existing is not None and existing.kind not in {"sdk_login", "watcher_login"}:
        existing = None
    if (watcher_auth or fresh_login) and selected_url is None:
        raise CommandError("Choose --cloud or --url for the selected credential source.")
    if watcher_auth:
        assert selected_url is not None
        return IntegrationAuth(base_url=selected_url, kind="watcher_login", state_dir=watcher_state_dir)
    if not fresh_login:
        if existing is not None and existing.base_url == selected_url:
            return existing
        candidates = discover_logins(selected_url, state_dir=state_dir)
        if candidates:
            return choose_profile(candidates)
    if not sys.stdin.isatty():
        if fresh_login:
            raise CommandError(
                "Browser sign-in needs an interactive terminal. Run watcher-sdk auth login --cloud or --url URL "
                "first, then repeat setup without --login."
            )
        raise CommandError("No selected sign-in is available. Run watcher-sdk auth login --cloud or --url URL first.")
    if selected_url is None:
        selected_url = str(_api_url(typer.prompt("Watcher server URL", default=CLOUD_URL)))
    if project is not None:
        SDKLoginAuth(selected_url, state_dir=state_dir).validate_project_location(project)
    return asyncio.run(login(selected_url, partial(show_authorization, selected_url), state_dir=state_dir))
