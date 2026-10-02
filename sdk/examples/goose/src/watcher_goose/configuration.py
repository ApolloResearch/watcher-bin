"""Render installed hook assets without changing host configuration."""

import json
import shlex
import sys
from importlib.resources import files

ASSETS = {"observe": "hooks.json", "enforce": "enforce.example.json"}


def render_settings(*, enforce: bool) -> str:
    """Return mode settings bound to this installed interpreter, preserving native hook policy.

    The caller writes and explicitly loads the returned configuration. Existing
    host hooks are never modified. Shell and JSON/TOML quoting preserve spaces
    and special characters in virtual-environment paths.
    """
    name = ASSETS["enforce" if enforce else "observe"]
    template = files("watcher_goose").joinpath("assets", name).read_text()
    interpreter = json.dumps(shlex.quote(sys.executable))[1:-1]
    return template.replace("__WATCHER_PYTHON__", interpreter)


def observe_settings() -> None:
    """Print observation configuration; the caller chooses where to load it."""
    sys.stdout.write(render_settings(enforce=False))


def enforce_settings() -> None:
    """Print pre-tool and completion configuration without installing host hooks."""
    sys.stdout.write(render_settings(enforce=True))


def plugin_manifest() -> None:
    """Print the packaged plugin identity for an explicitly chosen plugin directory."""
    sys.stdout.write(files("watcher_goose").joinpath("assets", "plugin.json").read_text())
