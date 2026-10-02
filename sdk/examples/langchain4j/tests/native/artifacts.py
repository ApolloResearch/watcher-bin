"""Verify the installed Java/Python components against their build receipt."""

import hashlib
import importlib.metadata
import json
import zipfile
from pathlib import Path


def verify_native_artifacts(destination):
    """Refuse traffic if native JARs, launcher or installed wheel bytes changed."""
    provenance = json.loads(Path("/opt/native-provenance.json").read_text())
    measured = {}
    for filename, expected in provenance["artifact_sha256"].items():
        actual = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError("Installed native artifact differs: " + filename)
        measured[filename] = actual
    for distribution, wheel in provenance["python_wheels"].items():
        installed = importlib.metadata.distribution(distribution)
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if not name.endswith(".py"):
                    continue
                if Path(str(installed.locate_file(name))).read_bytes() != archive.read(name):
                    raise RuntimeError("Installed wheel bytes differ: " + name)
    destination.write_text(json.dumps({**provenance, "measured_artifact_sha256": measured}, indent=2) + "\n")
