"""Packaged Cline hooks retain their native response contracts after wheel installation."""

import json
import os
import subprocess
import sys
from importlib.resources import as_file, files

import pytest


@pytest.mark.parametrize(
    "hook,expected",
    [
        ("TaskComplete", {}),
        ("TaskCompleteMonitored", {}),
        ("PreToolUse", {"cancel": True, "errorMessage": "Watcher did not confirm approval"}),
    ],
)
def test_installed_hook_handles_invalid_input_without_source_siblings(hook, expected):
    resource = files("watcher_cline_bridge").joinpath("hooks", hook)
    with as_file(resource) as path:
        result = subprocess.run(
            ["sh", str(path)],
            input="private-invalid-json",
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
            env={"PATH": os.environ["PATH"], "WATCHER_PYTHON": sys.executable},
        )
    assert result.returncode == 0
    assert json.loads(result.stdout) == expected
    assert "private-invalid-json" not in result.stderr
    assert "Watcher" in result.stderr
