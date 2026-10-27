"""Build an installed Node/Python backend-test image without running an agent.

Preparation may download pinned toolchains and dependencies. Runtime fixtures are
launched separately by the Watcher backend test runner with networking disabled.
Every invocation creates a fresh artifact directory and retains failed builds.
"""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[2]
NODE_VERSION = "24.22.1"
NODE_SHA256 = "6c172a9ab6718f7b801fb5a7bd486af2ee5e32758086a04b84fcce2aa77095e6"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], log: Path, *, env: dict[str, str] | None = None, cwd: Path | None = None) -> None:
    """Retain complete command output, including failures, in this build's directory."""
    with log.open("w") as output:
        subprocess.run(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)


def verify_python_wheels(container: str, wheels: Path, destination: Path) -> list[dict]:
    """Compare the full installed Python file sets and origins with their retained wheels."""
    receipts = []
    for wheel in sorted(wheels.glob("*.whl")):
        with zipfile.ZipFile(wheel) as archive:
            expected = {
                name: archive.read(name)
                for name in archive.namelist()
                if not name.endswith("/") and ".dist-info/" not in name and ".data/" not in name
            }
            metadata = next(name.split("/")[0] for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
        installed = destination / wheel.stem
        installed.mkdir()
        for package in {Path(name).parts[0] for name in expected}:
            subprocess.run(
                [
                    "docker",
                    "cp",
                    f"{container}:/usr/local/lib/python3.12/site-packages/{package}",
                    str(installed / package),
                ],
                check=True,
            )
        actual = {
            str(path.relative_to(installed)): path.read_bytes()
            for path in installed.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        }
        assert actual == expected, f"Installed source differs from {wheel.name}"
        origin = destination / (wheel.stem + ".origin.json")
        subprocess.run(
            [
                "docker",
                "cp",
                f"{container}:/usr/local/lib/python3.12/site-packages/{metadata}/direct_url.json",
                str(origin),
            ],
            check=True,
        )
        origin_data = json.loads(origin.read_text())
        assert origin_data["archive_info"]["hashes"]["sha256"] == sha(wheel)
        assert origin_data["url"] == "file:///opt/wheels/" + wheel.name
        receipts.append(
            {
                "wheel": wheel.name,
                "sha256": sha(wheel),
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in actual.items()},
            }
        )
    return receipts


def main() -> None:
    """Prepare locked packages, build an image, then inspect its filesystem without starting it."""
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("This fixture image recipe requires Linux x86_64")
    parent = Path(os.environ.get("WATCHER_EXAMPLE_RUN_DIR", tempfile.gettempdir())).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix=f"watcher-{EXAMPLE.name}-image.", dir=parent))
    print(f"Prepared image artifacts: {output}", flush=True)
    context = output / "context"
    context.mkdir()
    project = EXAMPLE / "packages/python"
    files = [
        project / "pyproject.toml",
        project / "uv.lock",
        EXAMPLE / "packages/node/package.json",
        EXAMPLE / "packages/node/package-lock.json",
    ]
    for folder in (project / "src", EXAMPLE / "packages/node/src", EXAMPLE / "tests/native"):
        files.extend(
            path
            for path in folder.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        )
    sources = {str(path.relative_to(EXAMPLE)): sha(path) for path in sorted(files)}
    support = EXAMPLE.parent / "_test_support/readback.py"
    shared_sources = {"_test_support/readback.py": sha(support)}
    wheels = context / "wheels"
    wheels.mkdir()
    supplied_sdk = os.environ.get("WATCHER_SDK_WHEEL")
    if supplied_sdk:
        sdk = Path(supplied_sdk).resolve(strict=True)
        shutil.copy2(sdk, wheels / sdk.name)
    else:
        run(["uv", "build", str(EXAMPLE.parents[1]), "--wheel", "--out-dir", str(wheels)], output / "sdk-build.log")
    run(["uv", "build", str(project), "--wheel", "--out-dir", str(wheels)], output / "wheel-build.log")
    run(
        [
            "uv",
            "export",
            "--project",
            str(project),
            "--frozen",
            "--no-emit-project",
            "--no-emit-package",
            "watcher-sdk",
            "--output-file",
            str(context / "requirements.txt"),
        ],
        output / "requirements.log",
    )
    (sdk,) = wheels.glob("watcher_sdk-*.whl")
    (bridge,) = [path for path in wheels.glob("*.whl") if path != sdk]
    with zipfile.ZipFile(bridge) as packed:
        for path in (project / "src").rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                assert packed.read(str(path.relative_to(project / "src"))) == path.read_bytes()

    node_archive = output / "node.tar.xz"
    cached_node = os.environ.get("WATCHER_NATIVE_NODE_ARCHIVE")
    if cached_node:
        shutil.copy2(Path(cached_node).resolve(strict=True), node_archive)
    else:
        with (
            urllib.request.urlopen(
                f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-linux-x64.tar.xz", timeout=120
            ) as response,
            node_archive.open("wb") as target,
        ):
            shutil.copyfileobj(response, target)
    assert sha(node_archive) == NODE_SHA256, "Node archive checksum differs"
    toolchain = output / "node-toolchain"
    with tarfile.open(node_archive) as archive:
        archive.extractall(toolchain, filter="data")
    node_root = toolchain / f"node-v{NODE_VERSION}-linux-x64"
    environment = dict(os.environ, PATH=str(node_root / "bin") + os.pathsep + os.environ["PATH"])
    node = node_root / "bin/node"
    assert subprocess.check_output([str(node), "--version"], text=True).strip() == "v" + NODE_VERSION
    shutil.copy2(node, context / "node")
    artifacts = context / "artifacts"
    artifacts.mkdir()
    run(
        [
            str(node_root / "bin/npm"),
            "pack",
            str(EXAMPLE / "packages/node"),
            "--pack-destination",
            str(artifacts),
            "--ignore-scripts",
        ],
        output / "npm-pack.log",
        env=environment,
    )
    (archive,) = artifacts.glob("*.tgz")
    installed = output / "installed"
    run(
        [
            str(node),
            str(EXAMPLE / "tests/native/install-node-package.mjs"),
            str(EXAMPLE / "packages/node/package.json"),
            str(EXAMPLE / "packages/node/package-lock.json"),
            str(archive),
            str(installed),
        ],
        output / "npm-install.log",
        env=environment,
    )
    package = json.loads((EXAMPLE / "packages/node/package.json").read_text())
    name = package["name"]
    with tarfile.open(archive) as packed:
        for member in packed.getmembers():
            if member.isdir():
                continue
            assert member.isfile() and not Path(member.name).is_absolute() and ".." not in Path(member.name).parts
            relative = Path(member.name).relative_to("package")
            stream = packed.extractfile(member)
            assert stream is not None
            data = stream.read()
            assert (installed / "node_modules" / name / relative).read_bytes() == data
            assert (EXAMPLE / "packages/node" / relative).read_bytes() == data
    shutil.copytree(installed / "node_modules", context / "node_modules", symlinks=True)
    for filename in ("package.json", "package-lock.json", "locked-node-install.json"):
        shutil.copy2(installed / filename, context / filename)
    shutil.copytree(EXAMPLE / "tests/native", context / "native", ignore=shutil.ignore_patterns("__pycache__"))
    (context / "native/_test_support").mkdir()
    shutil.copy2(support, context / "native/_test_support/readback.py")
    (context / "python-project").mkdir()
    for filename in ("pyproject.toml", "uv.lock"):
        shutil.copy2(project / filename, context / "python-project" / filename)
    (context / "package-proof.json").write_text(
        json.dumps(
            {
                "package_name": name,
                "installed_package": "/opt/node-app/node_modules/" + name,
                "archive": "/opt/node-app/artifacts/" + archive.name,
                "archive_sha256": sha(archive),
            },
            indent=2,
        )
    )
    (context / "Dockerfile").write_text("""FROM python:3.12.13-slim-bookworm
WORKDIR /opt/node-app
COPY requirements.txt /opt/requirements.txt
RUN pip install --no-cache-dir --require-hashes --no-deps -r /opt/requirements.txt
COPY wheels /opt/wheels
RUN --network=none pip install --no-index --no-deps /opt/wheels/*.whl && pip check
COPY node /usr/local/bin/node
COPY node_modules /opt/node-app/node_modules
COPY package.json package-lock.json locked-node-install.json package-proof.json /opt/node-app/
COPY artifacts /opt/node-app/artifacts
COPY native /opt/node-app/tests/native
COPY python-project /opt/node-app/python-project
ENV PATH=/opt/node-app/node_modules/.bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin
ENV PYTHONDONTWRITEBYTECODE=1 OTEL_SDK_DISABLED=true DO_NOT_TRACK=1 LANGSMITH_TRACING=false
RUN useradd --uid 1000 --create-home probe
USER probe
""")
    run(["docker", "build", "--iidfile", str(output / "image.id"), str(context)], output / "build.log")
    assert sources == {relative: sha(EXAMPLE / relative) for relative in sources}, "Source changed during preparation"
    assert shared_sources == {"_test_support/readback.py": sha(support)}, (
        "Shared test support changed during preparation"
    )
    image = (output / "image.id").read_text().strip()
    (output / "image-inspect.json").write_bytes(subprocess.check_output(["docker", "inspect", image]))
    container = subprocess.check_output(
        ["docker", "create", "--network", "none", "--entrypoint", "/bin/true", image], text=True
    ).strip()
    (output / "stopped-container.json").write_bytes(subprocess.check_output(["docker", "inspect", container]))
    proof = output / "source-proof"
    proof.mkdir()
    mapping = {
        "/opt/node-app/tests/native/" + path.name: path
        for path in (EXAMPLE / "tests/native").iterdir()
        if path.is_file()
    }
    mapping["/opt/node-app/tests/native/_test_support/readback.py"] = support
    for path in [EXAMPLE / "packages/node/package.json", *sorted((EXAMPLE / "packages/node/src").rglob("*"))]:
        if path.is_file():
            mapping["/opt/node-app/node_modules/" + name + "/" + str(path.relative_to(EXAMPLE / "packages/node"))] = (
                path
            )
    measurements = {}
    try:
        wheel_proof = verify_python_wheels(container, wheels, proof)
        for index, (target, source) in enumerate(mapping.items()):
            copied = proof / (str(index) + "-" + source.name)
            subprocess.run(["docker", "cp", container + ":" + target, str(copied)], check=True)
            assert sha(copied) == sha(source)
            measurements[target] = {
                "source": str(source),
                "source_sha256": sha(source),
                "image_sha256": sha(copied),
                "copied_artifact": str(copied),
            }
    finally:
        removed = subprocess.run(["docker", "rm", "-v", container], capture_output=True, text=True)
        inspected = subprocess.run(["docker", "inspect", container], capture_output=True, text=True)
        (output / "cleanup.json").write_text(
            json.dumps(
                {"container": container, "remove_exit": removed.returncode, "inspect_exit": inspected.returncode},
                indent=2,
            )
        )
        assert removed.returncode == 0 and inspected.returncode != 0
    receipt = {
        "slug": EXAMPLE.name,
        "image": image,
        "command": ["python", "/opt/node-app/tests/native/backend_probe.py"],
        "source_sha256": sources,
        "shared_source_sha256": shared_sources,
        "sdk_wheel_sha256": sha(sdk),
        "wheels": wheel_proof,
        "node_version": NODE_VERSION,
        "node_toolchain_sha256": NODE_SHA256,
        "node_binary_sha256": sha(node),
        "node_archive_sha256": sha(archive),
        "source_correspondence": measurements,
        "runtime_started": False,
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Prepared image: {image}", flush=True)


if __name__ == "__main__":
    main()
