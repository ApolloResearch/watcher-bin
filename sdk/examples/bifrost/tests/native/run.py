"""Build pinned gateway dependencies and test installed artifacts without networking.

WATCHER_EXAMPLE_RUN_DIR selects the parent evidence directory. Build-only and
run-only switches allow a scheduler to reserve the native runtime separately
from dependency downloads; a resumed run requires unchanged source hashes.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

PYTHON_IMAGE = "python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(url: str, destination: Path, expected: str) -> None:
    """Retain and verify every fetched source/toolchain archive before extraction."""
    if not destination.exists():
        with urllib.request.urlopen(url, timeout=120) as response, destination.open("wb") as output:
            shutil.copyfileobj(response, output)
    if sha(destination) != expected:
        raise ValueError("Archive checksum mismatch: " + destination.name)


def extract(archive: Path, destination: Path) -> Path:
    """Extract a fresh archive with path traversal and unsafe links rejected."""
    destination.mkdir()
    with tarfile.open(archive) as stream:
        stream.extractall(destination, filter="data")
    (root,) = destination.iterdir()
    return root


def run(command: list[str], *, cwd: Path, log: Path, env=None) -> int:
    with log.open("w") as output:
        return subprocess.run(
            command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, check=False
        ).returncode


def source_hashes(example: Path) -> dict[str, str]:
    selected = [example / "pyproject.toml", example / "uv.lock", example / "README.md"]
    for folder in ("src", "gateway", "tests", "demo"):
        selected.extend(p for p in (example / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    return {str(p.relative_to(example)): sha(p) for p in sorted(selected)}


def main() -> None:
    example = Path(__file__).resolve().parents[2]
    slug = example.name
    assert slug in {"bifrost", "portkey"}
    parent = Path(os.environ.get("WATCHER_EXAMPLE_RUN_DIR", tempfile.gettempdir()))
    parent.mkdir(parents=True, exist_ok=True)
    run_only = os.environ.get("WATCHER_NATIVE_RUN_ONLY") == "1"
    run_dir = (
        Path(os.environ["WATCHER_NATIVE_RUN_DIR"])
        if run_only
        else Path(tempfile.mkdtemp(prefix=f"watcher-{slug}-native.", dir=parent))
    )
    report_dir = run_dir / "installed/reports"
    current = source_hashes(example)
    if run_only:
        assert current == json.loads((run_dir / "source-before.json").read_text()), (
            "Source changed; rebuild the installed fixture"
        )
    else:
        report_dir.mkdir(parents=True)
        (run_dir / "source-before.json").write_text(json.dumps(current, indent=2))
        context = run_dir / "image"
        context.mkdir()
        wheels = context / "wheels"
        wheels.mkdir()
        sdk_wheel = os.environ.get("WATCHER_SDK_WHEEL")
        if sdk_wheel:
            shutil.copy2(sdk_wheel, wheels / Path(sdk_wheel).name)
        else:
            assert (
                run(
                    ["uv", "build", str(example.parents[1]), "--wheel", "--out-dir", str(wheels)],
                    cwd=example,
                    log=run_dir / "sdk-build.log",
                )
                == 0
            )
        assert (
            run(
                ["uv", "build", str(example), "--wheel", "--out-dir", str(wheels)],
                cwd=example,
                log=run_dir / "example-build.log",
            )
            == 0
        )
        assert (
            run(
                [
                    "uv",
                    "export",
                    "--frozen",
                    "--no-emit-project",
                    "--no-emit-package",
                    "watcher-sdk",
                    "--output-file",
                    str(context / "requirements.txt"),
                ],
                cwd=example,
                log=run_dir / "export.log",
            )
            == 0
        )
        shutil.copytree(example / "tests", context / "tests", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(example / "tests/native/installed.py", context / "installed.py")
        shutil.copy2(example / "tests/native/artifacts.py", context / "artifacts.py")
        provenance = {
            "slug": slug,
            "source_sha256": current,
            "base_image": PYTHON_IMAGE,
            "wheel_sha256": {p.name: sha(p) for p in wheels.glob("*.whl")},
        }
        dockerfile = [
            f"FROM {PYTHON_IMAGE}",
            "COPY requirements.txt /opt/requirements.txt",
            "RUN pip install --no-cache-dir --require-hashes -r /opt/requirements.txt",
            "COPY wheels /opt/wheels",
            "RUN pip install --no-deps /opt/wheels/*.whl",
            "COPY tests /opt/tests",
            "COPY installed.py artifacts.py provenance.json /opt/",
            "ENV PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
            "WORKDIR /opt",
        ]
        if slug == "bifrost":
            archive = run_dir / "go.tar.gz"
            download(
                "https://go.dev/dl/go1.27.0.linux-amd64.tar.gz",
                archive,
                "675c26c449cbb18fc24b74650de1eabbae6e16f64326fd85a283fb3b58280685",
            )
            go = extract(archive, run_dir / "go-toolchain")
            build = Path(os.environ.get("WATCHER_BIFROST_BUILD_DIR", str(run_dir / "native-build"))).resolve()
            env = dict(
                os.environ, PATH=str(go / "bin") + os.pathsep + os.environ["PATH"], WATCHER_BIFROST_BUILD_DIR=str(build)
            )
            assert (
                run([str(example / "tests/native/build.sh")], cwd=example, env=env, log=run_dir / "gateway-build.log")
                == 0
            )
            for name in ("gateway-build-info.txt", "plugin-build-info.txt", "sha256.txt"):
                shutil.copy2(build / name, run_dir / name)
            for name in ("bifrost-http", "watcher.so", "watcher-tests"):
                shutil.copy2(build / "bin" / name, context / name)
            provenance.update(
                upstream_versions={"bifrost": "048492cff9cf451baf7bfcb13bc0342383788f15"},
                build_toolchains={"go": "1.27.0"},
                gateway_sha256=sha(context / "bifrost-http"),
                plugin_sha256=sha(context / "watcher.so"),
                plugin_tests_sha256=sha(context / "watcher-tests"),
                toolchain_archive_sha256=sha(archive),
                upstream_archive_sha256=sha(build / "bifrost.tar.gz"),
                scope="Native HTTP API and plugin; no built dashboard",
            )
            dockerfile += [
                "COPY bifrost-http watcher.so watcher-tests /opt/bifrost/",
                "ENV BIFROST_BINARY=/opt/bifrost/bifrost-http BIFROST_PLUGIN=/opt/bifrost/watcher.so GOMAXPROCS=2 GOMEMLIMIT=768MiB",
            ]
        else:
            archive = run_dir / "portkey.tar.gz"
            download(
                "https://codeload.github.com/Portkey-AI/gateway/tar.gz/669825cbe89ee51569918b8f78a9db486fd69dd4",
                archive,
                "d69ce5369b2a9fd61beb44608c9f09458fbd2bf3bd5ef884348c19a17b26b8c1",
            )
            native = extract(archive, run_dir / "upstream")
            node_archive = run_dir / "node.tar.xz"
            download(
                "https://nodejs.org/dist/v24.11.1/node-v24.11.1-linux-x64.tar.xz",
                node_archive,
                "60e3b0a8500819514aca603487c254298cd776de0698d3cd08f11dba5b8289a8",
            )
            node = extract(node_archive, run_dir / "node-toolchain")
            env = dict(os.environ, PATH=str(node / "bin") + os.pathsep + os.environ["PATH"])
            assert (
                run(
                    [str(node / "bin/npm"), "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
                    cwd=native,
                    env=env,
                    log=run_dir / "npm-install.log",
                )
                == 0
            )
            portkey = context / "portkey"
            portkey.mkdir()
            for name in ("src", "plugins", "node_modules"):
                shutil.copytree(native / name, portkey / name, symlinks=True)
            for name in ("conf.json", "package.json"):
                shutil.copy2(native / name, portkey / name)
            shutil.copy2(node / "bin/node", context / "node")
            shutil.copy2(example / "gateway/server.mjs", context / "server.mjs")
            provenance.update(
                upstream_versions={"portkey": json.loads((native / "package.json").read_text())["version"]},
                upstream_revision="669825cbe89ee51569918b8f78a9db486fd69dd4",
                runtimes={"node": "24.11.1"},
                upstream_archive_sha256=sha(archive),
                toolchain_archive_sha256=sha(node_archive),
                runtime_binary_sha256=sha(context / "node"),
                scope="Native buffered gateway routes; dependency lifecycle scripts skipped; no configured retry path",
            )
            dockerfile += [
                "COPY node /usr/local/bin/node",
                "COPY portkey /opt/portkey",
                "COPY server.mjs /opt/server.mjs",
                "ENV PORTKEY_SOURCE=/opt/portkey PORTKEY_WATCHER_LAUNCHER=/opt/server.mjs",
            ]
        (context / "provenance.json").write_text(json.dumps(provenance, indent=2))
        (context / "Dockerfile").write_text("\n".join(dockerfile) + "\n")
        assert (
            run(
                ["docker", "build", "--iidfile", str(run_dir / "image.id"), str(context)],
                cwd=example,
                log=run_dir / "image-build.log",
            )
            == 0
        )
        assert current == source_hashes(example), "Source changed while packaging"
        (run_dir / "image.json").write_text(
            subprocess.check_output(
                ["docker", "image", "inspect", (run_dir / "image.id").read_text().strip()], text=True
            )
        )
    evidence = run_dir / "evidence"
    evidence.mkdir(exist_ok=True)
    shutil.copy2(run_dir / "image.id", evidence / "image.id")
    print("Installed-artifact test directory: " + str(run_dir), flush=True)
    if os.environ.get("WATCHER_NATIVE_BUILD_ONLY") == "1":
        return
    image_id = (run_dir / "image.id").read_text().strip()
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--memory",
        "1g",
        "--memory-swap",
        "1g",
        "--cpus",
        "1",
        "--env",
        "WATCHER_NATIVE_IMAGE_ID=" + image_id,
        "--pids-limit",
        "256",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=256m,mode=1777",
        "--mount",
        f"type=bind,src={run_dir / 'installed'},dst=/evidence",
        image_id,
        "python",
        "/opt/installed.py",
    ]
    (run_dir / "container-command.json").write_text(json.dumps(command, indent=2))
    status = run(command, cwd=example, log=run_dir / "native.log")
    print("Retained artifact test reports: " + str(report_dir), flush=True)
    sys.exit(status)


if __name__ == "__main__":
    main()
