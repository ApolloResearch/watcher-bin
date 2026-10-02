"""Check the demo against installed wheels and frozen runtime-only dependencies.

Run inside the network-isolated container's clean runtime venv. No development
dependency or editable source path is present. Missing configuration must fail
before any client sends a request, while every demo import resolves successfully.
"""

import importlib.metadata
import json
import runpy
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx
import pydantic
import structlog
import watcher_google_security_operations

import watcher_sdk


def main() -> None:
    """Save installed-package provenance and the demo's configuration failure."""
    assert sys.prefix == "/opt/example-runtime"
    installed = {
        distribution.metadata["Name"]: distribution.version for distribution in importlib.metadata.distributions()
    }
    assert "pytest" not in installed and "pytest-asyncio" not in installed and "types-protobuf" not in installed
    distribution = importlib.metadata.distribution("watcher-google-security-operations-example")
    requirements = distribution.requires
    assert requirements is not None and "structlog==26.1.0" in requirements
    for package in (watcher_google_security_operations, watcher_sdk, structlog, httpx, pydantic):
        assert package.__file__ is not None and Path(package.__file__).is_relative_to(sys.prefix)
    verified = 0
    for wheel in Path("/fixture/wheels").glob("*.whl"):
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if name.startswith(
                    ("watcher_google_security_operations/", "watcher_sdk/", "watcher_transcript_transport/")
                ) and not name.endswith("/"):
                    installed_file = distribution.locate_file(name)
                    assert Path(str(installed_file)).read_bytes() == archive.read(name)
                    verified += 1
    assert verified > 0
    runpy.run_path("/fixture/demo/export.py", run_name="demo_import_check")
    result = subprocess.run(
        [sys.executable, "/fixture/demo/export.py"],
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    Path("/evidence/runtime-demo.stdout.txt").write_text(result.stdout)
    Path("/evidence/runtime-demo.stderr.txt").write_text(result.stderr)
    assert result.returncode == 1 and "KeyError: 'WATCHER_URL'" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr and "ImportError" not in result.stderr
    receipt = {
        "python": sys.executable,
        "installed_distributions": installed,
        "example_requires_dist": requirements,
        "installed_wheel_files_verified": verified,
        "demo_import": "passed",
        "missing_configuration": "WATCHER_URL",
        "demo_exit_code": result.returncode,
    }
    Path("/evidence/runtime-demo.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
