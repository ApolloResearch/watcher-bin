"""Run installed-package tests and retain SDK identity inside a network-free container."""

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


def main() -> int:
    """Verify installed SDK bytes, test behavior and save environment/JUnit receipts."""
    assert {name for _, name in socket.if_nameindex()} == {"lo"}
    evidence = Path("/evidence")
    Path.home().mkdir(parents=True, exist_ok=True)
    sdk = importlib.metadata.distribution("watcher-sdk")
    wheel = next(Path("wheels").glob("watcher_sdk-*.whl"))
    matched = 0
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith(("watcher_sdk/", "watcher_transcript_transport/")) and not name.endswith("/"):
                assert Path(str(sdk.locate_file(name))).read_bytes() == archive.read(name)
                matched += 1
    assert matched > 0
    direct_url = sdk.read_text("direct_url.json")
    assert direct_url is not None
    direct = json.loads(direct_url)
    assert direct.get("dir_info", {}).get("editable") is not True
    runtimes = {"python": platform.python_version()}
    runtimes["otelcol-contrib"] = subprocess.check_output(["otelcol-contrib", "--version"], text=True).strip()
    upstream = {
        "opentelemetry-proto": importlib.metadata.version("opentelemetry-proto"),
        "otelcol-contrib": runtimes["otelcol-contrib"].split()[-1],
    }
    environment = {
        "platform": platform.platform(),
        "runtimes": runtimes,
        "upstream_versions": upstream,
        "watcher_sdk": {
            "version": sdk.version,
            "revision": None,
            "artifact_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        },
        "sdk_files_verified": matched,
    }
    (evidence / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    tested = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            "pyproject.toml",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests",
            "--junitxml=/evidence/python.xml",
        ],
        check=False,
    )
    if tested.returncode:
        return tested.returncode
    environment_vars = dict(os.environ, COLLECTOR_TEST_OUTPUT="/evidence/collector")
    result = subprocess.run(
        [sys.executable, "tests/native/verify_collector.py"], env=environment_vars, check=False, timeout=300
    )
    suite = ET.Element(
        "testsuite", name="collector-configurations", tests="1", failures="0" if result.returncode == 0 else "1"
    )
    if result.returncode:
        case = ET.SubElement(suite, "testcase", classname="opentelemetry.collector", name="configuration-delivery")
        ET.SubElement(case, "failure", message="Collector fixture failed; inspect retained logs")
    else:
        verified = json.loads((evidence / "collector/result.json").read_text())
        suite.set("tests", str(len(verified["checks_passed"])))
        for name in verified["checks_passed"]:
            ET.SubElement(suite, "testcase", classname="opentelemetry.collector", name=name)
    ET.ElementTree(suite).write(evidence / "collector.xml", encoding="utf-8", xml_declaration=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
