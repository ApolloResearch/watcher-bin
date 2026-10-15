"""Hermes shell-hook commands: gate tool calls, record sessions and print hook configuration.

Hermes runs each configured shell hook as a subprocess with a JSON payload on
stdin and reads a JSON directive from stdout (see ``hooks:`` in the profile's
``config.yaml``). This module provides the three commands the README installs:

- ``gate`` for ``pre_tool_call``: reads the session's stored history, asks Watcher
  to judge the pending call, and prints a Hermes directive. Every failure prints
  a block directive, so a gate that cannot reach Watcher never lets a call run.
- ``record`` for ``on_session_end``, which Hermes fires after every turn,
  including interrupted ones: sends the session's history to Watcher. Failures
  never affect the agent.
- ``hooks``: prints the ``config.yaml`` block that wires the two commands to this
  installed interpreter. It changes no file.

Diagnostics go to stderr as fixed text: transcripts, tool arguments, paths,
credentials and server error bodies are never echoed.
"""

import asyncio
import json
import math
import os
import shlex
import sys
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit

import typer

from watcher_hermes.policy import block, directive
from watcher_hermes.transcript import convert, export_session, external_ids, with_pending_call
from watcher_sdk import AsyncWatcherClient
from watcher_sdk.local_auth import async_client_from_watcher

app = typer.Typer(
    invoke_without_command=True, no_args_is_help=False, add_completion=False, pretty_exceptions_enable=False
)

DEFAULT_TIMEOUT_SECONDS = 240.0
MAX_TIMEOUT_SECONDS = 270.0
"""Watcher's grading deadline must leave room for the export inside Hermes's 300-second hook cap."""

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}

GATE_HOOK_TIMEOUT_SECONDS = 300
RECORD_HOOK_TIMEOUT_SECONDS = 60
RECORD_TIMEOUT_SECONDS = 30.0

UrlOption = Annotated[
    str | None, typer.Option("--watcher-url", envvar="WATCHER_URL", help="Watcher API URL, ending in /api.")
]
AuthOption = Annotated[
    bool, typer.Option("--watcher-auth", help="Use the installed Watcher app's saved sign-in instead of an API key.")
]
StateOption = Annotated[
    Path | None, typer.Option("--watcher-state-dir", help="Watcher app home holding the saved sign-in.")
]
EscalateOption = Annotated[
    bool,
    typer.Option("--escalate-as-block", help="Block calls Watcher escalates instead of asking in Hermes's prompt."),
]
HermesOption = Annotated[
    str | None, typer.Option("--hermes-bin", help="The hermes command that reads this profile's sessions.")
]


@app.callback()
def main_callback(ctx: typer.Context) -> None:
    """Connect Hermes Agent to Watcher through shell hooks."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command("help", hidden=True)
def help_command(ctx: typer.Context) -> None:
    """Show the commands without reading a hook payload."""
    parent = ctx.parent
    typer.echo((parent if parent is not None else ctx).get_help())


def watcher_client(url: str | None, *, watcher_auth: bool, state_dir: Path | None) -> AsyncWatcherClient:
    """Build an SDK client from the saved sign-in or ``WATCHER_API_KEY``.

    A missing URL or credential raises rather than falling back to another
    server or credential. Only a Watcher on this machine (a development stack
    that accepts unauthenticated requests) may be reached without one.
    """
    if not url:
        raise ValueError("Set --watcher-url or WATCHER_URL")
    if watcher_auth:
        return async_client_from_watcher(url, state_dir=state_dir, timeout=MAX_TIMEOUT_SECONDS + 10)
    key = os.environ.get("WATCHER_API_KEY")
    if not key and urlsplit(url).hostname not in LOOPBACK_HOSTS:
        raise ValueError("Set WATCHER_API_KEY or pass --watcher-auth")
    return AsyncWatcherClient(url, api_key=key or None, timeout=MAX_TIMEOUT_SECONDS + 10)


def grading_timeout() -> float:
    """Read ``WATCHER_TIMEOUT_SECONDS``; it must fit inside Hermes's hook deadline."""
    timeout = float(os.environ.get("WATCHER_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    if not math.isfinite(timeout) or not 0 < timeout <= MAX_TIMEOUT_SECONDS:
        raise ValueError(f"WATCHER_TIMEOUT_SECONDS must be greater than zero and at most {MAX_TIMEOUT_SECONDS:.0f}")
    return timeout


def pending_call(payload: dict[str, Any]) -> tuple[str, dict[str, Any], str | None]:
    """Return the session ID, pending call and working directory from a ``pre_tool_call`` payload."""
    if payload.get("hook_event_name") != "pre_tool_call":
        raise ValueError("The gate handles pre_tool_call only")
    extra = payload.get("extra")
    if not isinstance(extra, dict):
        extra = {}
    call_id, name, arguments = extra.get("tool_call_id"), payload.get("tool_name"), payload.get("tool_input")
    if not isinstance(call_id, str) or not call_id or not isinstance(name, str) or not name:
        raise ValueError("Hermes did not name the pending tool call")
    if not isinstance(arguments, dict):
        raise ValueError("Hermes tool arguments must be an object")
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Hermes did not name the session")
    cwd = payload.get("cwd")
    return (
        session_id,
        {"id": call_id, "function": name, "arguments": arguments},
        cwd if isinstance(cwd, str) and cwd else None,
    )


async def judge(
    payload: dict[str, Any],
    client: AsyncWatcherClient,
    *,
    hermes_bin: str | None = None,
    escalate_as_block: bool = False,
) -> dict[str, Any]:
    """Ask Watcher to judge the pending call in its stored context and return the Hermes directive.

    The request is a full, recorded evaluation under the organization's policy,
    so the decision and the history up to this call are stored in Watcher.
    """
    session_id, call, cwd = pending_call(payload)
    timeout = grading_timeout()
    messages = with_pending_call(convert(await export_session(session_id, hermes_bin=hermes_bin)), call)
    submitted: dict[str, Any] = {
        "tool_use_id": call["id"],
        "tool_name": call["function"],
        "tool_input": call["arguments"],
    }
    if cwd is not None:
        submitted["cwd"] = cwd
    outcomes = await client.pre_tool_use_hook(
        input=[submitted], messages=messages, external_ids=external_ids(session_id), mode="full", timeout=timeout
    )
    if not isinstance(outcomes, list) or len(outcomes) != 1:
        raise PermissionError("Watcher's answer was incomplete")
    serialize = getattr(outcomes[0], "to_dict", None)
    if not callable(serialize):
        raise PermissionError("Watcher could not judge this call")
    return directive(serialize(), call["id"], escalate_as_block=escalate_as_block)


async def record_session(payload: dict[str, Any], client: AsyncWatcherClient, *, hermes_bin: str | None = None) -> None:
    """Send the session's stored history to Watcher without judging any call.

    Watcher appends only messages it has not stored, so recording after every
    turn never duplicates history.
    """
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Hermes did not name the session")
    messages = convert(await export_session(session_id, hermes_bin=hermes_bin))
    if not messages:
        return
    outcomes = await client.pre_tool_use_hook(
        input=[], messages=messages, external_ids=external_ids(session_id), timeout=RECORD_TIMEOUT_SECONDS
    )
    if outcomes != []:
        raise ValueError("Recording returned unexpected outcomes")


def _read_payload() -> dict[str, Any]:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("Hook payload must be an object")
    return payload


@app.command("gate")
def gate_command(
    watcher_url: UrlOption = None,
    watcher_auth: AuthOption = False,
    watcher_state_dir: StateOption = None,
    hermes_bin: HermesOption = None,
    escalate_as_block: EscalateOption = False,
) -> None:
    """Judge one pending tool call (Hermes ``pre_tool_call``); always prints a directive."""

    async def run() -> dict[str, Any]:
        payload = _read_payload()
        async with watcher_client(watcher_url, watcher_auth=watcher_auth, state_dir=watcher_state_dir) as client:
            return await judge(payload, client, hermes_bin=hermes_bin, escalate_as_block=escalate_as_block)

    try:
        result = asyncio.run(run())
    except Exception:
        sys.stderr.write("Watcher did not confirm this tool call; it was blocked.\n")
        result = block("Watcher could not check this tool call, so it was blocked. Try again later.")
    sys.stdout.write(json.dumps(result) + "\n")


@app.command("record")
def record_command(
    watcher_url: UrlOption = None,
    watcher_auth: AuthOption = False,
    watcher_state_dir: StateOption = None,
    hermes_bin: HermesOption = None,
) -> None:
    """Send the session history to Watcher (Hermes ``on_session_end``); never affects the agent."""

    async def run() -> None:
        payload = _read_payload()
        async with watcher_client(watcher_url, watcher_auth=watcher_auth, state_dir=watcher_state_dir) as client:
            await record_session(payload, client, hermes_bin=hermes_bin)

    try:
        asyncio.run(run())
    except Exception:
        sys.stderr.write("Watcher recording failed; this turn was not confirmed recorded.\n")
    sys.stdout.write("{}\n")


def render_hooks(
    *,
    watcher_url: str,
    record_only: bool,
    watcher_auth: bool,
    watcher_state_dir: Path | None,
    hermes_bin: str | None,
    escalate_as_block: bool = False,
) -> str:
    """Return the ``config.yaml`` block that wires this interpreter's commands into Hermes.

    Commands are shell-quoted (Hermes splits them with ``shlex``) and then
    written as YAML double-quoted strings. ``plugins.hook_callback_timeout``
    is raised because Hermes otherwise abandons a ``pre_tool_call`` hook after
    30 seconds and refuses the call, whatever the hook's own ``timeout`` says.
    """
    options = ["--watcher-url", watcher_url]
    if watcher_auth:
        options.append("--watcher-auth")
    if watcher_state_dir is not None:
        options += ["--watcher-state-dir", str(watcher_state_dir)]
    if hermes_bin is not None:
        options += ["--hermes-bin", hermes_bin]

    def command(name: str, *extra: str) -> str:
        return json.dumps(shlex.join([sys.executable, "-m", "watcher_hermes", name, *options, *extra]))

    lines = ["hooks:"]
    if not record_only:
        lines += [
            "  pre_tool_call:",
            f"    - command: {command('gate', *(['--escalate-as-block'] if escalate_as_block else []))}",
            f"      timeout: {GATE_HOOK_TIMEOUT_SECONDS}",
            "      fail_closed: true",
        ]
    lines += [
        "  on_session_end:",
        f"    - command: {command('record')}",
        f"      timeout: {RECORD_HOOK_TIMEOUT_SECONDS}",
    ]
    if not record_only:
        lines += ["plugins:", f"  hook_callback_timeout: {GATE_HOOK_TIMEOUT_SECONDS}"]
    return "\n".join(lines) + "\n"


@app.command("hooks")
def hooks_command(
    watcher_url: Annotated[
        str, typer.Option("--watcher-url", envvar="WATCHER_URL", help="Watcher API URL, ending in /api.")
    ],
    record_only: Annotated[
        bool, typer.Option("--record-only", help="Record sessions without gating tool calls.")
    ] = False,
    watcher_auth: AuthOption = False,
    watcher_state_dir: StateOption = None,
    hermes_bin: HermesOption = None,
    escalate_as_block: EscalateOption = False,
) -> None:
    """Print the hooks block to merge into Hermes's config.yaml; changes no file."""
    sys.stdout.write(
        render_hooks(
            watcher_url=watcher_url,
            record_only=record_only,
            watcher_auth=watcher_auth,
            watcher_state_dir=watcher_state_dir,
            hermes_bin=hermes_bin,
            escalate_as_block=escalate_as_block,
        )
    )


def main() -> None:
    """Run the ``watcher-hermes`` command."""
    app()
