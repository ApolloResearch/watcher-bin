"""Bind gateway source/build provenance to the executable files used by a fixture."""

import hashlib
import json
import os
import shutil
from pathlib import Path


def verify_native_artifacts(provenance_path: Path, destination: Path) -> dict:
    """Measure installed native files and reject any mismatch before model traffic.

    The build receipt binds source hashes to compiled artifacts; this runtime
    receipt supplies the independently measured binary/plugin/launcher hashes.
    The caller's container inspection supplies the authoritative image identity.
    Optional WATCHER_NATIVE_IMAGE_ID records that same ID inside the fixture.
    """
    provenance = json.loads(provenance_path.read_text())
    slug = provenance["slug"]
    if slug == "bifrost":
        expected = {
            os.environ["BIFROST_BINARY"]: provenance["gateway_sha256"],
            os.environ["BIFROST_PLUGIN"]: provenance["plugin_sha256"],
        }
        source = {"gateway/main.go": provenance["source_sha256"]["gateway/main.go"]}
    elif slug == "portkey":
        node = shutil.which(os.environ.get("NODE_BINARY", "node"))
        if node is None:
            raise RuntimeError("Pinned Node executable is missing")
        expected = {
            node: provenance["runtime_binary_sha256"],
            os.environ["PORTKEY_WATCHER_LAUNCHER"]: provenance["source_sha256"]["gateway/server.mjs"],
        }
        source = {"gateway/server.mjs": provenance["source_sha256"]["gateway/server.mjs"]}
    else:
        raise ValueError("Unknown native gateway")
    measured = {}
    for filename, digest in expected.items():
        actual = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
        if actual != digest:
            raise RuntimeError("Installed native artifact differs from its build receipt: " + filename)
        measured[filename] = actual
    receipt = {
        "schema_version": 1,
        "slug": slug,
        "image_id": os.environ.get("WATCHER_NATIVE_IMAGE_ID"),
        "source_sha256": source,
        "artifact_sha256": measured,
        "build_provenance_sha256": hashlib.sha256(provenance_path.read_bytes()).hexdigest(),
        "upstream_versions": provenance["upstream_versions"],
    }
    destination.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt
