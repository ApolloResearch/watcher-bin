"""Packaged settings launch installed hooks away from their source directory."""

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from watcher_cursor.configuration import render_settings


@pytest.mark.parametrize("enforce", [False, True])
def test_packaged_settings_commands_load_installed_hooks(tmp_path, enforce):
    """Exercise the commands handed to native settings without source-path imports."""
    text = render_settings(enforce=enforce)
    settings = json.loads(text)
    commands = []

    def collect(value):
        if isinstance(value, dict):
            if "command" in value:
                commands.append(value["command"])
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(settings)
    assert commands
    for command in commands:
        assert "__WATCHER_PYTHON__" not in command
        result = subprocess.run(
            shlex.split(command),
            cwd=tmp_path,
            input="PRIVATE INVALID JSON",
            text=True,
            capture_output=True,
            check=False,
        )
        if "watcher_cursor.integration" in shlex.split(command):
            assert result.returncode == 1
            assert result.stdout == ""
            assert "transcript was not confirmed recorded" in result.stderr
        else:
            assert result.returncode == 2
            assert json.loads(result.stdout)["permission"] == "deny"
        assert "No module named" not in result.stderr
        assert "PRIVATE INVALID JSON" not in result.stderr
        if result.stdout:
            assert isinstance(json.loads(result.stdout), dict)


@pytest.mark.parametrize(
    ("enforce", "filename"),
    [(False, "hooks.example.json"), (True, "hooks.enforce.example.json")],
)
def test_documented_templates_match_packaged_settings(monkeypatch, enforce, filename):
    """Keep copyable examples equivalent to settings loaded from the installed package."""
    monkeypatch.setattr(sys, "executable", "python")
    template = (Path(__file__).parents[1] / "demo" / filename).read_text()
    expected = json.loads(template.replace("__WATCHER_PYTHON__", "python"))
    assert json.loads(render_settings(enforce=enforce)) == expected
