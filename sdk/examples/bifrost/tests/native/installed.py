"""Verify installed wheel bytes, then run gateway unit and native protocol checks."""

import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from artifacts import verify_native_artifacts


def installed_runtimes() -> dict[str, str]:
    """Measure interpreters present in this image without promoting build declarations.

    Compiler versions remain in the retained build provenance. A Node runtime is
    reported only when its installed executable supplies its own version banner.
    """
    runtimes = {"python": platform.python_version()}
    node = shutil.which("node")
    if node is not None:
        runtimes["node"] = subprocess.check_output([node, "--version"], text=True).strip()
    return runtimes


def main() -> None:
    provenance = json.loads(Path("/opt/provenance.json").read_text())
    slug = provenance["slug"]
    reports = Path("/evidence/reports")
    reports.mkdir(exist_ok=True)
    assert sorted(os.listdir("/sys/class/net")) == ["lo"]
    verify_native_artifacts(Path("/opt/provenance.json"), reports / "native-artifacts.json")
    installed = {}
    for wheel in Path("/opt/wheels").glob("*.whl"):
        package = "watcher_sdk" if wheel.name.startswith("watcher_sdk-") else "watcher_" + slug
        spec = importlib.util.find_spec(package)
        assert spec is not None and spec.origin is not None
        site = Path(spec.origin).parent.parent
        archive_hash = hashlib.sha256(wheel.read_bytes()).hexdigest()
        assert archive_hash == provenance["wheel_sha256"][wheel.name]
        files = {}
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if not name.startswith(package + "/") or name.endswith("/"):
                    continue
                expected = hashlib.sha256(archive.read(name)).hexdigest()
                assert hashlib.sha256((site / name).read_bytes()).hexdigest() == expected, name
                files[name] = expected
        installed[package] = {"wheel": wheel.name, "artifact_sha256": archive_hash, "files": files}
    (reports / "installed-versions.json").write_text(json.dumps(installed, indent=2))
    (reports / "provenance.json").write_text(json.dumps(provenance, indent=2))
    sdk = installed["watcher_sdk"]
    environment = {
        "platform": platform.platform(),
        "runtimes": installed_runtimes(),
        "upstream_versions": provenance["upstream_versions"],
        "watcher_sdk": {
            "version": importlib.metadata.version("watcher-sdk"),
            "artifact_sha256": sdk["artifact_sha256"],
        },
    }
    (reports / "environment.json").write_text(json.dumps(environment, indent=2))
    if slug == "bifrost":
        binary = Path("/opt/bifrost/watcher-tests")
        assert hashlib.sha256(binary.read_bytes()).hexdigest() == provenance["plugin_tests_sha256"]
        shutil.copy2(binary, reports / "watcher-tests")
        names = subprocess.check_output([str(binary), "-test.list", "."], text=True).splitlines()
        assert names and all(name.startswith("Test") for name in names)
        suite = ET.Element("testsuite", name="bifrost-plugin", tests=str(len(names)), errors="0", skipped="0")
        failures = 0
        for name in names:
            started = time.monotonic()
            result = subprocess.run(
                [str(binary), "-test.v", "-test.run", "^" + name + "$"], capture_output=True, text=True
            )
            (reports / (name + ".log")).write_text(result.stdout + result.stderr)
            case = ET.SubElement(
                suite, "testcase", classname="bifrost.plugin", name=name, time=str(time.monotonic() - started)
            )
            if result.returncode:
                failures += 1
                ET.SubElement(case, "failure", message="Plugin contract failed; inspect " + name + ".log")
        suite.set("failures", str(failures))
        ET.ElementTree(suite).write(reports / "plugin.xml", encoding="unicode")
        if failures:
            sys.exit(1)
    unit = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "pytest_asyncio.plugin",
            "-p",
            "no:cacheprovider",
            "--noconftest",
            "--rootdir",
            "/opt/tests",
            "--import-mode=importlib",
            "-o",
            "asyncio_mode=auto",
            "/opt/tests/test_bridge.py",
            "-q",
            "--junitxml=" + str(reports / "python.xml"),
        ],
        check=False,
    )
    if unit.returncode:
        sys.exit(unit.returncode)
    started = time.monotonic()
    protocol_evidence = reports / "protocol"
    protocol = subprocess.run(
        [
            sys.executable,
            "/opt/tests/native/probe.py",
            "--gateway",
            slug,
            "--protocol",
            "--evidence",
            str(protocol_evidence),
        ],
        check=False,
    )
    results = protocol_evidence / "results.json"
    cases = json.loads(results.read_text()) if results.exists() else []
    suite = ET.Element(
        "testsuite",
        name=slug + "-native-protocol",
        tests=str(len(cases) + bool(protocol.returncode)),
        failures=str(int(bool(protocol.returncode))),
        errors="0",
        skipped="0",
        time=str(time.monotonic() - started),
    )
    for case in cases:
        ET.SubElement(suite, "testcase", classname="native." + slug, name=str(case["case"]))
    if protocol.returncode:
        failed = ET.SubElement(suite, "testcase", classname="native." + slug, name="protocol_completion")
        ET.SubElement(failed, "failure", message="Native protocol driver failed; inspect native.log and protocol logs")
    ET.ElementTree(suite).write(reports / "native.xml", encoding="unicode")
    sys.exit(protocol.returncode)


if __name__ == "__main__":
    main()
