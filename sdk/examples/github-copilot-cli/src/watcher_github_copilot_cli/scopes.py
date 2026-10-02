"""Leave Copilot callbacks alone in opted-out projects, and find projects that two installs cover.

Copilot runs the personal hooks in every folder and a project's own hooks beside
them, so in a project with both installs, both record and judge each call. Every
callback, personal or project, reads the opt-out list in the personal install's
private configuration, so opting a project out turns off all of this sample's
hooks in it.

These checks read only which folder an installation covers and its opt-outs,
and for warnings its hook commands, never its server or credential, so they
also read a configuration its hooks refuse to use, one redirected to another
server, naming an API key or holding a credential nothing accepts (see
``load_scope`` and ``load_hooks``). An opt-out therefore holds even then, and an
installation whose hooks Copilot still runs still counts as an overlap.
"""

import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from pydantic import JsonValue

from watcher_github_copilot_cli.configuration import (
    InstallationScope,
    configuration_path,
    load_hooks,
    load_scope,
    project_root,
)
from watcher_github_copilot_cli.diagnostics import SkipReason


def personal_install(config_root: Path) -> InstallationScope | None:
    """The personal install's scope in ``config_root``, or ``None`` when there is none or it cannot be read."""
    try:
        return load_scope(configuration_path(None, config_root))
    except (OSError, ValueError):
        return None


def skip_reason(config_path: Path, payload: Mapping[str, JsonValue]) -> SkipReason | None:
    """Why the hook configured at ``config_path`` should leave this callback alone, or ``None`` to handle it.

    A callback is left alone when the payload's ``cwd`` is an absolute folder whose
    project (see ``project_root``) the personal install lists as opted out. That
    list is read from the configuration root holding ``config_path``, found after
    resolving it, so a relative or symlinked ``--config`` finds the same root. A
    path that cannot be resolved, such as a symlink to itself, is made absolute
    without following symlinks instead. The hook's own configuration is not read
    here, so an opted-out project stays untouched even when that configuration is
    missing or damaged. When the list or the project cannot be determined, this
    returns ``None``, so the hook records and judges the call instead of leaving
    it to nobody.
    """
    try:
        config_path = config_path.resolve()
    except (OSError, RuntimeError):
        try:
            config_path = Path(os.path.abspath(config_path))
        except OSError:
            return None
    personal = personal_install(config_path.parent.parent)
    cwd = payload.get("cwd")
    if personal is None or not personal.opted_out or not isinstance(cwd, str) or not Path(cwd).is_absolute():
        return None
    try:
        root = project_root(Path(cwd))
    except (OSError, RuntimeError):
        return None
    return "opted_out" if root in personal.opted_out else None


def project_installs(config_root: Path) -> list[Path]:
    """The projects with their own install in ``config_root``, sorted; unreadable configurations are left out."""
    config_root = config_root.expanduser().resolve()
    projects: list[Path] = []
    for path in config_root.glob("*/config.json"):
        try:
            project = load_scope(path).project
        except (OSError, ValueError):
            continue
        if project is not None and configuration_path(project, config_root) == path:
            projects.append(project)
    return sorted(projects)


def _opted_out(personal: InstallationScope, project: Path) -> bool:
    try:
        return project_root(project) in personal.opted_out
    except (OSError, RuntimeError):
        return False


def sample_command(name: str, project: Path) -> str:
    """This sample's own command ``name`` for ``project``, as ``overlap_warnings`` suggests it."""
    return f"{name} --project {project}"


def _other_python(config_path: Path) -> str | None:
    """The interpreter of a hook configured at ``config_path`` when it is outside this Python's environment, or ``None``.

    Setup writes each hook with the Python it ran under. A hook whose interpreter
    sits in another folder, such as an older checkout's virtual environment, runs
    that checkout's code, which may be a version of this sample that ignores
    opt-outs. Only the hook commands are read (see ``load_hooks``), so this also
    works for a configuration its hooks refuse; one whose commands cannot be read
    gives ``None``.
    """
    try:
        commands = load_hooks(config_path)
    except (OSError, ValueError):
        return None
    current = Path(sys.executable).absolute().parent
    for command in (commands.hook, commands.gate):
        if command is not None and Path(command.exec).absolute().parent != current:
            return command.exec
    return None


def _may_ignore_opt_out(project: Path, interpreter: str, command: Callable[[str, Path], str]) -> str:
    return (
        f"{project} is opted out, but its own install runs its hooks with another Python, {interpreter}, which may"
        " be a version of this sample that ignores opt-outs, so the opt-out may not apply to it."
        f" Run {command('setup', project)} with this version."
    )


def stale_install_warnings(
    config_root: Path, root: Path, *, command: Callable[[str, Path], str] = sample_command
) -> list[str]:
    """Warnings for ``opt-out`` about project installs in ``root`` whose hooks run another Python (see ``_other_python``).

    ``command`` spells the command a warning suggests, as for ``overlap_warnings``.
    """
    warnings: list[str] = []
    for project in project_installs(config_root):
        interpreter = _other_python(configuration_path(project, config_root))
        try:
            in_root = project_root(project) == root
        except (OSError, RuntimeError):
            in_root = False
        if in_root and interpreter is not None:
            warnings.append(_may_ignore_opt_out(project, interpreter, command))
    return warnings


def overlap_warnings(
    config: InstallationScope, config_root: Path, *, command: Callable[[str, Path], str] = sample_command
) -> list[str]:
    """Warnings, for setup and status, about projects that both the personal install and their own install cover.

    Copilot runs both installs in such a project, so both record each turn and
    Watcher judges each tool call twice. ``config`` is either installation, and
    the other is looked up in the same ``config_root``. The personal install
    lists every overlapping project install with the command that removes it; a
    project install warns about the personal one. A project that is opted out
    runs neither install, so it never overlaps, and its own install says so
    instead. When that install's hooks run another Python (see
    ``_other_python``), both say the opt-out may not apply to it. Nothing is
    removed. ``command`` spells the ``remove``, ``opt-in`` and ``setup`` commands
    a warning suggests, given the command's name and the project, so another
    tool that manages these installs can name its own.
    """
    if config.project is None:
        warnings: list[str] = []
        for project in project_installs(config_root):
            interpreter = _other_python(configuration_path(project, config_root))
            if not _opted_out(config, project):
                warnings.append(
                    f"A project install also covers {project}, so both run there and Watcher judges each"
                    f" tool call twice. Run {command('remove', project)} to keep only the personal install."
                )
            elif interpreter is not None:
                warnings.append(_may_ignore_opt_out(project, interpreter, command))
        return warnings
    personal = personal_install(config_root)
    if personal is None:
        return []
    if _opted_out(personal, config.project):
        interpreter = _other_python(configuration_path(config.project, config_root))
        if interpreter is not None:
            return [_may_ignore_opt_out(config.project, interpreter, command)]
        return [
            f"{config.project} is opted out of this sample's hooks, so this install's hooks, which run this version"
            f" of the sample, leave it alone. Run {command('opt-in', config.project)} to turn it back on."
        ]
    return [
        "The personal install also covers this project, so both run in it and Watcher judges each tool call twice."
        f" Run {command('remove', config.project)} to keep only the personal install."
    ]
