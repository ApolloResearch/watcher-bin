"""Run installed-package contracts and one real native scenario inside containment."""

import hashlib
import importlib.metadata
import json
import os
import platform
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

EVIDENCE = Path("/evidence")


def result(slug, scenario, start, error):
    """Retain an explicit failing case if the native proof does not finish."""
    suite = ET.Element("testsuite", name=slug, tests="1", failures=str(int(error is not None)))
    case = ET.SubElement(
        suite, "testcase", classname=slug + ".native", name=scenario, time=str(time.monotonic() - start)
    )
    if error is not None:
        ET.SubElement(case, "failure", message=error)
    ET.ElementTree(suite).write(EVIDENCE / "native.xml", encoding="utf-8", xml_declaration=True)


def main():
    """Record the actual installed SDK artifact and fail if any test or fixture fails."""
    slug = Path("slug.txt").read_text().strip()
    scenario = os.environ["WATCHER_EXAMPLE_SCENARIO"]
    start = time.monotonic()
    result(slug, scenario, start, "Native fixture did not finish")
    assert str(Path.home()) == "/home/probe"
    assert {
        name for _, name in socket.if_nameindex() if int((Path("/sys/class/net") / name / "flags").read_text(), 16) & 1
    } == {"lo"}
    wheel = next(Path.cwd().glob("watcher_sdk-*.whl"))
    sdk = importlib.metadata.distribution("watcher-sdk")
    matched = 0
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if not name.endswith("/") and name.startswith(("watcher_sdk/", "watcher_transcript_transport/")):
                assert sdk.locate_file(name).read_bytes() == archive.read(name)
                matched += 1
    assert matched > 0
    upstream = "openclaw" if slug == "openclaw" else "@github/copilot"
    version = json.loads((Path("/opt/native/node_modules") / upstream / "package.json").read_text())["version"]
    environment = {
        "platform": platform.platform(),
        "runtimes": {
            "python": platform.python_version(),
            "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        },
        "upstream_versions": {upstream: version},
        "watcher_sdk": {
            "version": sdk.version,
            "revision": None,
            "artifact_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        },
        "sdk_files_verified": matched,
    }
    (EVIDENCE / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    if scenario == "observe":
        contracts = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--noconftest",
                "-c",
                "pytest.ini",
                "-p",
                "no:cacheprovider",
                "--junitxml=/evidence/python.xml",
                *[str(p) for p in sorted(Path.cwd().glob("test_*.py"))],
            ],
            check=False,
        )
        if contracts.returncode:
            result(slug, scenario, start, "Installed package contracts failed")
            return 1
    try:
        run = subprocess.run([sys.executable, "native_fixture.py"], check=False, timeout=240)
        error = None if run.returncode == 0 else "Native fixture failed; inspect run.log"
    except Exception as exc:
        error = type(exc).__name__ + ": " + str(exc)
    result(slug, scenario, start, error)
    return int(error is not None)


if __name__ == "__main__":
    raise SystemExit(main())
