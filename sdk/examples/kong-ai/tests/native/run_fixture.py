"""Verify installed wheels, unit contracts and the actual proxy without external networking."""

import hashlib
import importlib.metadata
import json
import os
import platform
import socket
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def check_wheel(name: str, wheel: Path, prefix: str) -> int:
    """Require every installed package byte to match the supplied wheel artifact."""
    package = importlib.metadata.distribution(name)
    origin_text = package.read_text("direct_url.json")
    assert origin_text is not None
    origin = json.loads(origin_text)
    assert origin["url"].endswith(".whl") and not origin.get("dir_info", {}).get("editable", False)
    count = 0
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.namelist():
            if member.startswith(prefix) and not member.endswith("/"):
                assert Path(str(package.locate_file(member))).read_bytes() == archive.read(member), member
                count += 1
    assert count > 0
    return count


def main() -> int:
    """Keep source identity and raw failures alongside every package/proxy result."""
    root = Path("/opt/fixture")
    evidence = Path("/evidence")
    assert {name for _, name in socket.if_nameindex()} == {"lo"}
    assert Path.home() == Path("/home/probe")
    assert not Path("/var/run/docker.sock").exists()
    with socket.socket() as connection:
        connection.settimeout(1)
        assert connection.connect_ex(("1.1.1.1", 443)) != 0
    sdk_wheel = next(root.glob("watcher_sdk-*.whl"))
    example_wheel = next(root.glob("watcher_kong_ai_example-*.whl"))
    sdk_files = check_wheel("watcher-sdk", sdk_wheel, "watcher_sdk/")
    example_files = check_wheel("watcher-kong-ai-example", example_wheel, "watcher_kong_ai/")
    environment = {
        "platform": platform.platform(),
        "runtimes": {"python": platform.python_version()},
        "upstream_versions": {"kong": (evidence / "kong-version.txt").read_text().strip()},
        "watcher_sdk": {
            "version": importlib.metadata.version("watcher-sdk"),
            "revision": None,
            "artifact_sha256": hashlib.sha256(sdk_wheel.read_bytes()).hexdigest(),
        },
        "sdk_files_verified": sdk_files,
        "integration_files_verified": example_files,
    }
    (evidence / "environment.json").write_text(json.dumps(environment, indent=2))
    env = {**os.environ, "DO_NOT_TRACK": "1"}
    with (evidence / "unit.log").open("w") as stream:
        unit = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--confcutdir=/opt/fixture",
                "-c",
                "pyproject.toml",
                "tests",
                "--junitxml=/evidence/python.xml",
            ],
            cwd=root,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )
    protocol_dir = evidence
    with (evidence / "protocol.log").open("w") as stream:
        protocol = subprocess.run(
            [sys.executable, str(root / "tests/native/probe.py"), "--protocol", "--evidence", str(protocol_dir)],
            cwd=root,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )
    results_file = protocol_dir / "results.json"
    results = json.loads(results_file.read_text()) if results_file.exists() else []
    suite = ET.Element(
        "testsuite",
        name="installed-kong_ai-proxy",
        tests=str(len(results) + int(protocol.returncode != 0)),
        failures=str(int(protocol.returncode != 0)),
        errors="0",
    )
    for result in results:
        ET.SubElement(suite, "testcase", name=result["case"])
    if protocol.returncode:
        case = ET.SubElement(suite, "testcase", name="native-protocol-completion")
        ET.SubElement(case, "failure", message="Inspect protocol.log and retained native artifacts")
    ET.ElementTree(suite).write(evidence / "native.xml", encoding="unicode")
    summary = {
        "unit_exit": unit.returncode,
        "protocol_exit": protocol.returncode,
        "native_cases_completed": len(results),
        "network": "none",
    }
    (evidence / "summary.json").write_text(json.dumps(summary, indent=2))
    return int(unit.returncode != 0 or protocol.returncode != 0)


if __name__ == "__main__":
    raise SystemExit(main())
