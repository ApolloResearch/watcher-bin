"""Verify containment and the installed SDK before starting any CrewAI process.

The Docker entrypoint runs native_fixture.py and the regression suite serially.
Only /evidence persists; native state is confined to the fresh HOME and tmpfs.
"""

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from importlib.metadata import distribution, distributions, version
from pathlib import Path

EVIDENCE = Path("/evidence")
FIXTURE = Path("/opt/fixture")


def verify_boundary():
    """Fail before native imports unless only loopback and fresh task state exist."""
    interfaces = [name for _, name in socket.if_nameindex()]
    assert interfaces == ["lo"], interfaces
    ipv4_routes = Path("/proc/net/route").read_text().splitlines()[1:]
    assert not ipv4_routes, ipv4_routes
    ipv6_routes = Path("/proc/net/ipv6_route").read_text().splitlines()
    assert all(route.split()[-1] == "lo" for route in ipv6_routes), ipv6_routes
    assert Path.home() == Path("/home/probe")
    assert not list(Path.home().iterdir()), "Fixture HOME must start empty"
    assert not Path("/var/run/docker.sock").exists()
    process = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines())
    assert os.geteuid() != 0
    assert int(process["CapEff"].strip(), 16) == 0
    assert process["NoNewPrivs"].strip() == "1"
    for key, value in {
        "OTEL_SDK_DISABLED": "true",
        "CREWAI_TELEMETRY_DISABLED": "true",
        "CREWAI_TESTING": "true",
        "CREWAI_TRACING_ENABLED": "false",
    }.items():
        assert os.environ[key] == value
    boundary = {
        "interfaces": interfaces,
        "ipv4_routes": ipv4_routes,
        "ipv6_routes": ipv6_routes,
        "uid": os.geteuid(),
        "effective_capabilities": 0,
        "no_new_privileges": True,
    }
    (EVIDENCE / "network.json").write_text(json.dumps(boundary, indent=2))
    return boundary


def verify_sdk():
    """Compare every installed public SDK package file with the archived wheel."""
    revision = None
    package = distribution("watcher-sdk")
    origin_text = package.read_text("direct_url.json")
    assert origin_text is not None
    origin = json.loads(origin_text)
    assert origin["url"].endswith(f"/watcher_sdk-{importlib.metadata.version('watcher-sdk')}-py3-none-any.whl")
    assert not origin.get("dir_info", {}).get("editable", False)
    wheel = FIXTURE / f"watcher_sdk-{importlib.metadata.version('watcher-sdk')}-py3-none-any.whl"
    verified = []
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.endswith("/") or not name.startswith(("watcher_sdk/", "watcher_transcript_transport/")):
                continue
            source = archive.read(name)
            assert Path(str(package.locate_file(name))).read_bytes() == source, name
            verified.append({"path": name, "sha256": hashlib.sha256(source).hexdigest()})
    expected_files = {item["path"] for item in verified}
    installed_files = {
        str(path.relative_to(Path(str(package.locate_file("")))))
        for folder in ("watcher_sdk", "watcher_transcript_transport")
        for path in Path(str(package.locate_file(folder))).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert "watcher_sdk/__init__.py" in expected_files
    assert installed_files == expected_files, installed_files ^ expected_files
    (EVIDENCE / "sdk-files.json").write_text(json.dumps(verified, indent=2))
    return {
        "sdk_revision": revision,
        "sdk_noneditable": True,
        "sdk_files_verified": len(verified),
        "sdk_wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
    }


def verify_integration():
    """Reject an editable/source install and compare the integration wheel's files."""
    package = distribution("watcher-crewai-example")
    origin_text = package.read_text("direct_url.json")
    assert origin_text is not None
    origin = json.loads(origin_text)
    assert not origin.get("dir_info", {}).get("editable", False)
    wheel = FIXTURE / "watcher_crewai_example-0.1.0-py3-none-any.whl"
    count = 0
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith("watcher_crewai/") and not name.endswith("/"):
                installed = Path(str(package.locate_file(name)))
                assert not installed.resolve().is_relative_to(FIXTURE), installed
                assert installed.read_bytes() == archive.read(name), name
                count += 1
    assert count == 4, count
    return {
        "integration_files_verified": count,
        "integration_wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
    }


def execute(command, name, workspace):
    """Run one contained process to completion and preserve its full output."""
    with (EVIDENCE / f"{name}.log").open("w") as output:
        result = subprocess.run(
            command,
            cwd=workspace,
            stdout=output,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            timeout=180,
            check=False,
        )
    (EVIDENCE / f"{name}-exit.txt").write_text(str(result.returncode) + "\n")
    assert result.returncode == 0, f"{name} failed: inspect /evidence/{name}.log"


def main():
    boundary = verify_boundary()
    sdk = verify_sdk()
    integration = verify_integration()
    assert version("crewai") == "1.3.0"
    environment = {
        "platform": platform.platform(),
        "runtimes": {"python": platform.python_version()},
        "upstream_versions": {item.metadata["Name"]: item.version for item in distributions()},
        "watcher_sdk": {
            "version": version("watcher-sdk"),
            "revision": sdk["sdk_revision"],
            "artifact_sha256": sdk["sdk_wheel_sha256"],
        },
    }
    (EVIDENCE / "environment.json").write_text(json.dumps(environment, indent=2))
    installed = subprocess.run(
        [sys.executable, "-m", "pip", "freeze", "--all"], capture_output=True, text=True, timeout=30, check=True
    )
    (EVIDENCE / "installed-packages.txt").write_text(installed.stdout)
    workspace = Path("/tmp/native-workspace")
    workspace.mkdir(mode=0o700)
    for name in ("demo", "tests"):
        shutil.copytree(FIXTURE / name, workspace / name)
    shutil.copyfile(FIXTURE / "pyproject.toml", workspace / "pyproject.toml")
    shutil.copyfile(FIXTURE / "tests/native/native_fixture.py", workspace / "native_fixture.py")
    execute([sys.executable, str(workspace / "native_fixture.py")], "native", workspace)
    execute(
        [
            sys.executable,
            "-m",
            "pytest",
            "--noconftest",
            "-c",
            str(workspace / "pyproject.toml"),
            "-p",
            "no:cacheprovider",
            "--junitxml=/evidence/tests.xml",
            "-q",
            str(workspace / "tests/test_adapter.py"),
            str(workspace / "tests/test_observation.py"),
            str(workspace / "tests/test_trace.py"),
            str(workspace / "tests/test_synchronous.py"),
            str(workspace / "tests/test_configured_policy.py"),
        ],
        "tests",
        workspace,
    )
    suite = ET.parse(EVIDENCE / "tests.xml").getroot().find("testsuite")
    assert suite is not None and suite.attrib["failures"] == suite.attrib["errors"] == suite.attrib["skipped"] == "0"
    native = json.loads((EVIDENCE / "native-summary.json").read_text())
    summary = {
        **native,
        **sdk,
        **integration,
        "tests_passed": int(suite.attrib["tests"]),
        "runtime_network": "Docker --network none",
        **boundary,
    }
    (EVIDENCE / "summary.json").write_text(json.dumps(summary, indent=2))
    sys.stdout.write(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
