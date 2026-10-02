"""Measure the installed Node adapter against its retained npm archive before execution."""

import hashlib
import json
import tarfile
from pathlib import Path, PurePosixPath


def verify_node_package(evidence: Path) -> None:
    """Retain installed package bytes and reject any difference from the packed artifact.

    The build receipt locates the archive and package, but identity comes from the
    actual installed package.json and file bytes. Nested dependency directories
    are separate packages and are excluded from this adapter's file-set check.
    """
    proof = json.loads(Path("/opt/node-app/package-proof.json").read_text())
    archive = Path(proof["archive"])
    installed = Path(proof["installed_package"])
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert archive_hash == proof["archive_sha256"]
    destination = evidence / "installed-node-package"
    destination.mkdir()
    measured = {}
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            path = PurePosixPath(member.name)
            assert not path.is_absolute() and path.parts[0] == "package" and ".." not in path.parts
            if member.isdir():
                continue
            assert member.isfile(), "The native adapter archive must not contain links or special files"
            relative = Path(*path.parts[1:])
            stream = source.extractfile(member)
            assert stream is not None
            packed = stream.read()
            actual_path = installed / relative
            assert actual_path.is_file() and not actual_path.is_symlink()
            contents = actual_path.read_bytes()
            assert contents == packed, str(relative)
            copied = destination / relative
            copied.parent.mkdir(parents=True, exist_ok=True)
            copied.write_bytes(contents)
            measured[str(relative)] = {
                "installed_path": str(actual_path),
                "sha256": hashlib.sha256(contents).hexdigest(),
            }
    actual_files = {
        str(path.relative_to(installed))
        for path in installed.rglob("*")
        if path.is_file() and "node_modules" not in path.relative_to(installed).parts
    }
    assert actual_files == set(measured), "Installed adapter file set differs from its packed archive"
    package = json.loads((installed / "package.json").read_text())
    assert package["name"] == proof["package_name"]
    (evidence / "installed-node-package.json").write_text(
        json.dumps(
            {
                "package_json": package,
                "installed_path": str(installed),
                "archive": str(archive),
                "archive_sha256": archive_hash,
                "files": measured,
            },
            indent=2,
        )
    )
