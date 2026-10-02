"""Run contracts once during observation and report each isolated native scenario.

The shell launcher supplies a fresh /evidence mount for every scenario. Contract
suites run only in the observation container; every native driver retains its own
effect and refusal assertions. A failing suite or driver makes the container fail.
"""

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

EVIDENCE = Path("/evidence")


def requirements_content_sha256(path: Path) -> str:
    """Hash dependency pins, markers and hashes without export comments or blank lines."""
    lines = (line.strip() for line in path.read_text().splitlines())
    content = "\n".join(line for line in lines if line and not line.startswith("#"))
    return hashlib.sha256(content.encode()).hexdigest()


def record_environment(slug: str) -> None:
    """Retain installed versions, consumed locks and the actual native npm graph."""
    upstreams = {
        "opencode": ["opencode-ai"],
        "pi": ["@earendil-works/pi-coding-agent"],
        "cline": ["cline", "@cline/core"],
        "kilocode": ["@kilocode/cli"],
    }[slug]
    versions = {
        name: json.loads((Path("/opt/native/node_modules") / name / "package.json").read_text())["version"]
        for name in upstreams
    }
    wheel = Path("/opt/fixture") / f"watcher_sdk-{importlib.metadata.version('watcher-sdk')}-py3-none-any.whl"
    environment = {
        "platform": platform.platform(),
        "runtimes": {
            "python": platform.python_version(),
            "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        },
        "upstream_versions": versions,
        "watcher_sdk": {
            "version": importlib.metadata.version("watcher-sdk"),
            "revision": None,
            "artifact_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        },
        "native_lock_sha256": hashlib.sha256(Path("/opt/native/package-lock.json").read_bytes()).hexdigest(),
        "python_requirements_content_sha256": requirements_content_sha256(Path("/opt/fixture/requirements.txt")),
        "python_distributions": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
    }
    (EVIDENCE / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    shutil.copyfile("/opt/native/dependency-graph.json", EVIDENCE / "native-dependency-graph.json")
    shutil.copyfile("/opt/adapter/locked-node-install.json", EVIDENCE / "adapter-dependency-graph.json")


def write_native_result(slug: str, scenario: str, elapsed: float, failure: str | None) -> None:
    """Write one scenario case; unfinished or nonzero drivers are recorded as failures."""
    suite = ET.Element("testsuite", name=slug + "-native", tests="1", failures=str(int(failure is not None)))
    case = ET.SubElement(suite, "testcase", classname=slug, name=scenario, time=f"{elapsed:.6f}")
    if failure is not None:
        ET.SubElement(case, "failure", message=failure)
    ET.ElementTree(suite).write(EVIDENCE / "native.xml", encoding="utf-8", xml_declaration=True)


def main() -> int:
    """Execute one scenario and return failure if its contracts or native driver fail."""
    slug = os.environ["SDK50_HARNESS"]
    scenario = os.environ["WATCHER_EXAMPLE_SCENARIO"]
    started = time.monotonic()
    write_native_result(slug, scenario, 0, "Native fixture did not complete")
    try:
        record_environment(slug)
        statuses = []
        if scenario == "observe":
            tests = subprocess.run(
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
                    *[str(p) for p in sorted(Path(".").glob("test_*.py"))],
                ],
                env={**os.environ, "SDK50_PROCESS_TEST_EVIDENCE": "/evidence/process-cleanup.jsonl"},
                check=False,
            )
            statuses.append(tests.returncode)
            if Path("test_plugin.mjs").exists():
                tests = subprocess.run(
                    [
                        "node",
                        "--test",
                        "--test-reporter=junit",
                        "--test-reporter-destination=/evidence/node.xml",
                        "test_plugin.mjs",
                    ],
                    check=False,
                )
                statuses.append(tests.returncode)
        driver = os.environ["WATCHER_NATIVE_DRIVER"]
        if driver not in {"native_probe.py", "run_fixture.py", "run_synchronous.py"}:
            raise ValueError("Unknown native fixture driver")
        native_started = time.monotonic()
        result = subprocess.run([sys.executable, driver], check=False, timeout=600)
        write_native_result(
            slug,
            scenario,
            time.monotonic() - native_started,
            f"Native driver exit {result.returncode}; inspect run.log" if result.returncode else None,
        )
        statuses.append(result.returncode)
        return int(any(statuses))
    except Exception as error:
        write_native_result(slug, scenario, time.monotonic() - started, f"{type(error).__name__}: {error}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
