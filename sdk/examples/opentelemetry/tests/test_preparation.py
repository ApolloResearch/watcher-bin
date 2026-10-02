"""A failed Collector download stops preparation before Docker is invoked."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(
    os.name != "posix"
    or not os.access("/bin/sh", os.X_OK)
    or any(shutil.which(tool) is None for tool in ("bash", "basename", "dirname", "mkdir", "mktemp", "cp", "touch")),
    reason="The preparation check requires POSIX, /bin/sh, bash and basic file utilities",
)
def test_collector_download_failure_stops_before_docker(tmp_path):
    commands = tmp_path / "commands"
    commands.mkdir()
    docker_marker = tmp_path / "docker-called"
    curl_marker = tmp_path / "curl-called"
    scripts = {
        "uv": "exit 0\n",
        "curl": 'touch "$CURL_MARKER"\nprintf "%s\\n" "curl: (22) Fixture download failed" >&2\nexit 22\n',
        "docker": 'touch "$DOCKER_MARKER"\nexit 99\n',
    }
    for name, body in scripts.items():
        path = commands / name
        path.write_text("#!/bin/sh\nset -eu\n" + body)
        path.chmod(0o755)
    wheel = tmp_path / "watcher_sdk-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"unused: preparation stops before installation")
    environment = dict(
        os.environ,
        PATH=str(commands) + os.pathsep + os.environ["PATH"],
        WATCHER_SDK_WHEEL=str(wheel),
        WATCHER_EXAMPLE_RUN_DIR=str(tmp_path / "run"),
        DOCKER_MARKER=str(docker_marker),
        CURL_MARKER=str(curl_marker),
    )
    result = subprocess.run(
        ["bash", str(Path(__file__).parent / "native/run.sh")],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 22
    assert "curl: (22) Fixture download failed" in result.stderr
    assert curl_marker.exists()
    assert not docker_marker.exists()
