"""Build the installed LangChain4j backend-test image without running an agent.

Toolchain downloads and Maven resolution happen during preparation. Native tool
execution belongs to the separately launched, network-isolated backend fixture.
Failed runs are retained alongside their logs and downloaded artifacts.
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
JDK_URL = "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.20.1%2B1/OpenJDK17U-jdk_x64_linux_hotspot_17.0.20.1_1.tar.gz"
JDK_SHA256 = "3808d1d15e3ec6bd5b84057fb5d84c33d8a1536a258146bcea2e603fc726e08e"
MAVEN_URL = "https://archive.apache.org/dist/maven/maven-3/3.9.11/binaries/apache-maven-3.9.11-bin.tar.gz"
MAVEN_SHA512 = "bcfe4fe305c962ace56ac7b5fc7a08b87d5abd8b7e89027ab251069faebee516b0ded8961445d6d91ec1985dfe30f8153268843c89aa392733d1a3ec956c9978"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], log: Path, *, env: dict[str, str] | None = None) -> None:
    """Keep complete build output without using the source checkout as a build directory."""
    with log.open("w") as output:
        subprocess.run(command, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)


def toolchain(url: str, cached: str | None, destination: Path, checksum: str, algorithm: str) -> None:
    """Retain and validate the pinned archive before extracting any executable files."""
    if cached:
        shutil.copy2(Path(cached).resolve(strict=True), destination)
    else:
        with urllib.request.urlopen(url, timeout=120) as response, destination.open("wb") as target:
            shutil.copyfileobj(response, target)
    assert hashlib.new(algorithm, destination.read_bytes()).hexdigest() == checksum, "Toolchain checksum differs"
    with tarfile.open(destination) as archive:
        archive.extractall(destination.parent / destination.stem, filter="data")


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
    """Build pinned JARs and wheels, then verify the installed image through a stopped container."""
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("This fixture image recipe requires Linux x86_64")
    parent = Path(os.environ.get("WATCHER_EXAMPLE_RUN_DIR", tempfile.gettempdir())).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="watcher-langchain4j-image.", dir=parent))
    print(f"Prepared image artifacts: {output}", flush=True)
    context = output / "context"
    context.mkdir()
    project = EXAMPLE / "packages/python"
    files = [project / "pyproject.toml", project / "uv.lock", EXAMPLE / "packages/java/pom.xml"]
    for folder in (project / "src", EXAMPLE / "packages/java/src", EXAMPLE / "tests/native"):
        files.extend(
            path
            for path in folder.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        )
    sources = {str(path.relative_to(EXAMPLE)): sha(path) for path in sorted(files)}
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
            "--no-dev",
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
    toolchain(JDK_URL, os.environ.get("WATCHER_NATIVE_JDK_ARCHIVE"), output / "jdk.tar.gz", JDK_SHA256, "sha256")
    toolchain(
        MAVEN_URL, os.environ.get("WATCHER_NATIVE_MAVEN_ARCHIVE"), output / "maven.tar.gz", MAVEN_SHA512, "sha512"
    )
    jdk = output / "jdk.tar/jdk-17.0.20.1+1"
    maven = output / "maven.tar/apache-maven-3.9.11/bin/mvn"
    environment = dict(os.environ, JAVA_HOME=str(jdk), PATH=str(jdk / "bin") + os.pathsep + os.environ["PATH"])
    java_project = output / "java-project"
    shutil.copytree(EXAMPLE / "packages/java", java_project, ignore=shutil.ignore_patterns("target"))
    lib = context / "lib"
    lib.mkdir()
    run(
        [
            str(maven),
            "-B",
            "-f",
            str(java_project / "pom.xml"),
            "-Dmaven.repo.local=" + str(output / "m2"),
            "-DskipTests",
            "package",
            "dependency:copy-dependencies",
            "-DoutputDirectory=" + str(lib),
        ],
        output / "maven-build.log",
        env=environment,
    )
    expected_dependencies = json.loads((EXAMPLE / "tests/native/java-dependencies.json").read_text())
    measured_dependencies = {path.name: sha(path) for path in lib.glob("*.jar")}
    assert measured_dependencies == expected_dependencies, (
        "Resolved Maven runtime dependencies differ from the verified set"
    )
    (jar,) = (java_project / "target").glob("*.jar")
    shutil.copy2(jar, lib / jar.name)
    classes = context / "test-classes"
    classes.mkdir()
    run(
        [
            str(jdk / "bin/javac"),
            "-J-Xmx256m",
            "-cp",
            str(lib) + "/*",
            "-d",
            str(classes),
            str(EXAMPLE / "tests/native/HumanApprovalProbe.java"),
        ],
        output / "javac.log",
        env=environment,
    )
    shutil.copytree(jdk, context / "jdk", symlinks=True)
    for name in ("probe.py", "artifacts.py", "HumanApprovalProbe.java"):
        shutil.copy2(EXAMPLE / "tests/native" / name, context / name)
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copy2(project / name, context / name)
    artifact_hashes = {"/opt/java/lib/" + path.name: sha(path) for path in lib.glob("*.jar")}
    artifact_hashes.update(
        {"/opt/java/test-classes/" + str(path.relative_to(classes)): sha(path) for path in classes.rglob("*.class")}
    )
    artifact_hashes.update({"/opt/wheels/" + path.name: sha(path) for path in wheels.glob("*.whl")})
    artifact_hashes.update(
        {"/opt/watcher-langchain4j/" + name: sha(context / name) for name in ("probe.py", "artifacts.py")}
    )
    artifact_hashes["/opt/jdk/bin/java"] = sha(jdk / "bin/java")
    provenance = {
        "slug": "langchain4j",
        "source_sha256": sources,
        "jdk_archive_sha256": JDK_SHA256,
        "maven_archive_sha512": MAVEN_SHA512,
        "sdk_wheel_sha256": sha(sdk),
        "artifacts": {path.name: sha(path) for path in [*lib.glob("*.jar"), *wheels.glob("*.whl")]},
        "artifact_sha256": artifact_hashes,
        "python_wheels": {
            "watcher-sdk": "/opt/wheels/" + sdk.name,
            "watcher-langchain4j-bridge": "/opt/wheels/" + bridge.name,
        },
    }
    (context / "native-provenance.json").write_text(json.dumps(provenance, indent=2))
    (context / "Dockerfile").write_text("""FROM python:3.12.13-slim-bookworm
COPY requirements.txt pyproject.toml uv.lock /opt/java/
RUN pip install --no-cache-dir --require-hashes --no-deps -r /opt/java/requirements.txt
COPY wheels /opt/wheels
RUN --network=none pip install --no-index --no-deps /opt/wheels/*.whl && pip check
COPY jdk /opt/jdk
COPY lib /opt/java/lib
COPY test-classes /opt/java/test-classes
COPY HumanApprovalProbe.java /opt/java/HumanApprovalProbe.java
COPY probe.py artifacts.py /opt/watcher-langchain4j/
COPY native-provenance.json /opt/native-provenance.json
ENV JAVA_BIN=/opt/jdk/bin/java WATCHER_JAVA_CLASSPATH=/opt/java/lib/*:/opt/java/test-classes WATCHER_PYTHON=/usr/local/bin/python
ENV PYTHONDONTWRITEBYTECODE=1
RUN useradd --uid 1000 --create-home probe
USER probe
WORKDIR /tmp
""")
    run(["docker", "build", "--iidfile", str(output / "image.id"), str(context)], output / "build.log")
    assert sources == {relative: sha(EXAMPLE / relative) for relative in sources}, "Source changed during preparation"
    image = (output / "image.id").read_text().strip()
    (output / "image-inspect.json").write_bytes(subprocess.check_output(["docker", "inspect", image]))
    container = subprocess.check_output(
        ["docker", "create", "--network", "none", "--entrypoint", "/bin/true", image], text=True
    ).strip()
    (output / "stopped-container.json").write_bytes(subprocess.check_output(["docker", "inspect", container]))
    proof = output / "source-proof"
    proof.mkdir()
    measurements = {}
    try:
        wheel_proof = verify_python_wheels(container, wheels, proof)
        for index, (target, expected) in enumerate(artifact_hashes.items()):
            copied = proof / (str(index) + "-" + Path(target).name)
            subprocess.run(["docker", "cp", container + ":" + target, str(copied)], check=True)
            assert sha(copied) == expected
            measurements[target] = {
                "expected_sha256": expected,
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
        **provenance,
        "image": image,
        "command": [
            "python",
            "/opt/watcher-langchain4j/probe.py",
            "--case",
            "/evidence/input.json",
            "--evidence",
            "/evidence",
        ],
        "wheels": wheel_proof,
        "artifact_correspondence": measurements,
        "runtime_started": False,
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Prepared image: {image}", flush=True)


if __name__ == "__main__":
    main()
