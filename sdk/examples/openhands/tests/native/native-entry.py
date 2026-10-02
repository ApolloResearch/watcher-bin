"""Verify installed artifacts and run one native fixture inside a network-none container."""

import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from importlib.metadata import distribution, version
from pathlib import Path

ROOT = Path("/opt/fixture")
EVIDENCE = Path("/evidence")
assert Path.home() == Path("/home/probe")
assert {name for _, name in socket.if_nameindex()} == {"lo"}
config = json.loads((ROOT / "native-config.json").read_text())
scenario = os.environ["WATCHER_EXAMPLE_SCENARIO"]
receipts = []
for name in ["watcher-sdk", config["distribution"]]:
    installed = distribution(name)
    origin = json.loads(installed.read_text("direct_url.json"))
    wheel = ROOT / origin["url"].rsplit("/", 1)[-1]
    assert wheel.suffix == ".whl" and not origin.get("dir_info", {}).get("editable", False)
    count = 0
    with zipfile.ZipFile(wheel) as archive:
        for filename in archive.namelist():
            if not filename.endswith("/") and ".dist-info/" not in filename:
                assert installed.locate_file(filename).read_bytes() == archive.read(filename)
                count += 1
    assert count
    receipts.append(
        {
            "distribution": name,
            "version": installed.version,
            "files_verified": count,
            "artifact_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "noneditable": True,
        }
    )
(EVIDENCE / "installed-wheels.json").write_text(json.dumps(receipts, indent=2))
upstream: dict[str, str | None] = {name: version(name) for name in config["upstream_distributions"]}
runtimes = {"python": platform.python_version()}
version_home = Path(tempfile.mkdtemp(prefix="native-version-home-"))
version_environment = {
    **os.environ,
    "HOME": str(version_home),
    "XDG_CONFIG_HOME": str(version_home / ".config"),
    "XDG_CACHE_HOME": str(version_home / ".cache"),
    "XDG_DATA_HOME": str(version_home / ".local/share"),
    "XDG_STATE_HOME": str(version_home / ".local/state"),
}
for name, command in config["version_commands"].items():
    result = subprocess.run(
        command, cwd=version_home, env=version_environment, capture_output=True, text=True, timeout=30, check=False
    )
    (EVIDENCE / f"{name}-version.stdout").write_text(result.stdout)
    (EVIDENCE / f"{name}-version.stderr").write_text(result.stderr)
    (EVIDENCE / f"{name}-version.exit").write_text(str(result.returncode))
    observed = result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None
    if name == "node":
        if observed is not None:
            runtimes[name] = observed
    else:
        upstream[name] = observed
environment = {
    "platform": platform.platform(),
    "runtimes": runtimes,
    "upstream_versions": upstream,
    "watcher_sdk": {
        "version": receipts[0]["version"],
        "revision": None,
        "artifact_sha256": receipts[0]["artifact_sha256"],
    },
}
(EVIDENCE / "environment.json").write_text(json.dumps(environment, indent=2))
workspace = Path(tempfile.mkdtemp(prefix="installed-example-"))
if scenario == "unit":
    command = [
        sys.executable,
        "-m",
        "pytest",
        "--noconftest",
        "-c",
        str(ROOT / "pyproject.toml"),
        "-p",
        "no:cacheprovider",
        "--basetemp=/tmp/pytest-installed",
        "--junitxml=/evidence/tests.xml",
        "-q",
        str(ROOT / "tests"),
    ]
else:
    filename = config["observation_script"] if scenario == "observe" else config["enforcement_script"]
    command = [sys.executable, str(ROOT / filename)]
result = subprocess.run(command, cwd=workspace, check=False)
suite = ET.Element("testsuite", name=config["slug"] + "-native", tests="1", failures=str(int(result.returncode != 0)))
case = ET.SubElement(suite, "testcase", classname=config["slug"], name=scenario)
if result.returncode:
    ET.SubElement(case, "failure", message=f"Fixture exit {result.returncode}")
ET.ElementTree(suite).write(EVIDENCE / "native.xml", encoding="utf-8", xml_declaration=True)
raise SystemExit(result.returncode)
