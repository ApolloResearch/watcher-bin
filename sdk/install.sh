#!/usr/bin/env bash
# Install the SDK Copilot integration and its private runtime.
set -euo pipefail
umask 077

SDK_VERSION="__WATCHER_SDK_VERSION__"
# The release stamp identifies this bootstrap; the server selects the SDK package.
UV_VERSION="0.12.15"
PYTHON_VERSION="3.12.14"
ROOT="${WATCHER_SDK_INSTALL_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/watcher-sdk}"
TARGET=""
VERSION=""
SERVER_SELECTED=0
ARGS=("$@")

if [[ "${1:-}" != copilot ]]; then
    echo 'Usage: install-sdk.sh copilot --cloud|--url URL [--project PATH] [--record-only]'
    echo 'Without --project, the hooks cover every Copilot session of this user.'
    exit 1
fi
shift
while [[ $# -gt 0 ]]; do
    case "$1" in
        --cloud) [[ -z "$TARGET" ]] || { echo "Choose one server." >&2; exit 1; }; TARGET="https://app.apolloresearch.ai/api"; shift ;;
        --url|--watcher-url) [[ -z "$TARGET" ]] || { echo "Choose one server." >&2; exit 1; }; TARGET="${2:?--url requires a server URL}"; shift 2 ;;
        --version) VERSION="${2:?--version requires a release version}"; shift 2 ;;
        *) shift ;;
    esac
done
if [[ -z "$TARGET" ]]; then
    echo 'Choose --cloud or --url URL for the initial installation.' >&2
    exit 1
fi
# The server's reply selects the release to install, so plain HTTP is accepted only
# for a server on this machine, the same rule the SDK applies to sign-ins. This runs
# before anything is downloaded or written.
refuse_server() { echo 'The Watcher server URL must use HTTPS unless the server runs on this machine.' >&2; exit 1; }
SERVER=$(printf '%s' "$TARGET" | tr '[:upper:]' '[:lower:]')
AUTHORITY=${SERVER#*://}
AUTHORITY=${AUTHORITY%%[/?#]*}
case "$SERVER" in
    https://*) ;;
    http://*)
        case "$AUTHORITY" in
            *@*) refuse_server ;;
            localhost|localhost:*|127.0.0.1|127.0.0.1:*|'[::1]'|'[::1]:'*) ;;
            *) refuse_server ;;
        esac ;;
    *) refuse_server ;;
esac
# The download override replaces the public release as the source of both the archive
# and its checksum, so it must use HTTPS or local files, and using it is never silent.
case "${WATCHER_SDK_DOWNLOAD_BASE:-}" in
    '') ;;
    https://*|file://*) echo 'Downloading the SDK from WATCHER_SDK_DOWNLOAD_BASE instead of the public release.' >&2 ;;
    *) echo 'WATCHER_SDK_DOWNLOAD_BASE must be an https:// or file:// URL.' >&2; exit 1 ;;
esac
case "$ROOT" in /*) ;; *) echo 'WATCHER_SDK_INSTALL_ROOT must be an absolute path.' >&2; exit 1 ;; esac
mkdir -p "$ROOT/runtime" "$ROOT/releases"
TEMP=$(mktemp -d "$ROOT/.bootstrap.XXXXXX")
trap 'rm -rf -- "$TEMP"' EXIT

case "$(uname -s)-$(uname -m)" in
    Darwin-arm64) PLATFORM=aarch64-apple-darwin; UV_SHA=dc304b9ed1b24174572290fba60ac3f6fe63c73a671f0439e62a91375841964d ;;
    Darwin-x86_64) PLATFORM=x86_64-apple-darwin; UV_SHA=e9ca61775532368fe518ab03e7a354c7ecab8ccb3c7d941c775fcc4a362b801b ;;
    Linux-x86_64) PLATFORM=x86_64-unknown-linux-gnu; UV_SHA=f97935763c04be3e692460a7aaeaaab8fc3b78fcf8b389da820b38ae7423a638 ;;
    Linux-aarch64) PLATFORM=aarch64-unknown-linux-gnu; UV_SHA=0e9a3499b0587d449c9ff684c0160da607826e4af1cee220bc87f378702d3e08 ;;
    *) echo 'Supported platforms: macOS and glibc Linux on arm64 or x86_64.' >&2; exit 1 ;;
esac
UV="$ROOT/runtime/uv-$UV_VERSION"
if [[ ! -x "$UV" ]]; then
    echo "Installing the private SDK runtime (bootstrap $SDK_VERSION)..."
    curl -fsSL --connect-timeout 10 --max-time 120 "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$PLATFORM.tar.gz" -o "$TEMP/uv.tar.gz"
    if command -v shasum >/dev/null; then ACTUAL=$(shasum -a 256 "$TEMP/uv.tar.gz" | awk '{print $1}')
    else ACTUAL=$(sha256sum "$TEMP/uv.tar.gz" | awk '{print $1}'); fi
    [[ "$ACTUAL" == "$UV_SHA" ]] || { echo 'uv checksum verification failed.' >&2; exit 1; }
    tar -xzf "$TEMP/uv.tar.gz" -C "$TEMP"
    mv "$TEMP/uv-$PLATFORM/uv" "$UV"
fi
export UV_PYTHON_INSTALL_DIR="$ROOT/runtime/python"
export UV_PYTHON_BIN_DIR="$ROOT/runtime/bin"
# Each run gets its own uv cache, deleted on exit, and the sync below copies packages into
# the environment. uv otherwise hardlinks cached files into environments, so with a cache
# kept between runs, a package edited in place in the environment would also change the
# cached copy, and the next rebuild would link the edited file straight back in.
export UV_CACHE_DIR="$TEMP/cache"
# Reinstalling the base Python on every run replaces any file added to or changed in it,
# such as a sitecustomize.py that every hook would otherwise import at startup. A failed
# download keeps the installed Python.
UV_NO_CONFIG=1 "$UV" python install --reinstall --no-bin "$PYTHON_VERSION"
PYTHON=$(UV_NO_CONFIG=1 "$UV" python find --system --managed-python "$PYTHON_VERSION")

if [[ -z "$VERSION" ]]; then
    SERVER_SELECTED=1
    VERSION=$("$PYTHON" -I - "$TARGET" <<'PY'
import json, sys, urllib.error, urllib.parse, urllib.request
url = urllib.parse.urlsplit(sys.argv[1])
if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
    raise SystemExit("Invalid Watcher server URL.")
base = sys.argv[1].rstrip("/")
if not base.endswith("/api"):
    base += "/api"


class KeepServerRule(urllib.request.HTTPRedirectHandler):
    # urllib follows a redirect to plain HTTP on any host, where anyone on the network
    # could answer the version check, so a redirect must pass the same rule as --url.
    def redirect_request(self, request, fp, code, message, headers, new_url):
        target = urllib.parse.urlsplit(new_url)
        local = target.hostname in {"localhost", "127.0.0.1", "::1"} and not target.username and not target.password
        if target.scheme != "https" and not (target.scheme == "http" and local):
            raise SystemExit("The Watcher server redirected the version check to plain HTTP on another machine.")
        return super().redirect_request(request, fp, code, message, headers, new_url)


try:
    with urllib.request.build_opener(KeepServerRule).open(base + "/v1/version", timeout=15) as response:
        body = json.load(response)
except (OSError, ValueError):
    raise SystemExit("Cannot read the Watcher server version. Check --url and the server connection.") from None
if not isinstance(body, dict) or not isinstance(body.get("version"), str):
    raise SystemExit("Watcher did not return a server version.")
print(body["version"])
PY
    )
fi
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'Use a released server version, or select --version for a development server.' >&2; exit 1; }
BASE="${WATCHER_SDK_DOWNLOAD_BASE:-https://github.com/ApolloResearch/watcher-bin/releases/download/v$VERSION}"
ARCHIVE="watcher_sdk-$VERSION-source.tar.gz"
DEST="$ROOT/releases/$VERSION"
echo "Downloading Watcher SDK $VERSION..."
# checksums.txt comes from the same release as the archive, so this check catches a
# damaged or incomplete download but not someone who can replace both release files.
# Closing that gap needs signed or immutable releases, not a change to this script.
# curl follows redirects to plain HTTP by default, where anyone on the network could
# swap both files, so a redirect may only lead to another HTTPS address.
curl -fsSL --proto-redir =https --connect-timeout 10 --max-time 120 "$BASE/$ARCHIVE" -o "$TEMP/$ARCHIVE"
curl -fsSL --proto-redir =https --connect-timeout 10 --max-time 120 "$BASE/checksums.txt" -o "$TEMP/checksums.txt"
PROJECT="$DEST/sdk/examples/github-copilot-cli"
# Project setup below runs this release's command, so another install of the same release
# must not rebuild it until this install exits. The build step locks this file through
# descriptor 9, which this shell keeps open, and so locked, until it exits.
mkdir -p "$DEST"
exec 9>>"$DEST/.install.lock"
# Hooks in every project run this one release environment, so a file added or edited in
# it would bypass review everywhere. Every install therefore rebuilds the release tree
# from the verified archive and its environment from freshly downloaded, lock-checked
# packages copied into place, rather than trusting existing files. Together with the
# Python reinstall above, only the uv binary, checked when first downloaded, is reused.
# The new tree takes the release's fixed path before its environment is built, because
# project hooks and the environment's own scripts name that path. Other projects on this
# release therefore cannot run their hooks until the build finishes.
"$PYTHON" -I - "$TEMP/$ARCHIVE" "$TEMP/checksums.txt" "$DEST" "$UV" "$PYTHON_VERSION" "$SERVER_SELECTED" <<'PY'
import fcntl, hashlib, os, pathlib, re, shutil, signal, subprocess, sys, tarfile, tempfile, tomllib
archive, checksums, destination = map(pathlib.Path, sys.argv[1:4])
uv, python_version, server_selected = sys.argv[4:]
release = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
# A release tree gets this mark once its environment is fully built, before the backup of
# the tree it replaced is deleted. A tree a killed install left without it, or no tree at
# all, is what the recovery below replaces with that backup.
COMPLETE = ".build-complete"
signalled = 0
interruptible = True


def stop(signum, frame):
    # Only the first signal unwinds this step, and only until the swap and environment
    # build below end, whether they return or raise. Any other one just fails the step
    # once it has finished, so no signal can stop the restore below halfway.
    global signalled, interruptible
    signalled = signalled or signum
    if interruptible:
        interruptible = False
        raise SystemExit(128 + signum)


# Closing the terminal or a kill would otherwise end this step without any cleanup, so
# they unwind like Ctrl-C does, and all three go through stop. A signal the caller
# already ignores, as nohup does for hangups, stays ignored.
for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    if signal.getsignal(signum) is not signal.SIG_IGN:
        signal.signal(signum, stop)
matches = [line.split()[0] for line in checksums.read_text().splitlines() if len(line.split()) == 2 and line.split()[1].lstrip("*") == archive.name]
if len(matches) != 1 or hashlib.file_digest(archive.open("rb"), "sha256").hexdigest() != matches[0]:
    raise SystemExit("SDK checksum verification failed.")
# Descriptor 9 is the shell's release lock, so an install of the same release waits here
# until any other one has exited. Take it before .extract.lock, because the last step
# takes .extract.lock while this install still holds the release lock.
try:
    fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print(f"Waiting for another install of SDK release {destination.name} to finish...", file=sys.stderr, flush=True)
    fcntl.flock(9, fcntl.LOCK_EX)
# The lock spans the downgrade check, the swap and the environment build, so concurrent
# installs never build into a tree another install is replacing.
with (destination.parent / ".extract.lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    # A staging folder exists only while the build that made it holds this lock, so one
    # found now was left by an install that was killed, or that could not put a release
    # back. Its backup returns first if its release has no finished tree, because then the
    # backup is that release's only working copy. Without a mark on either tree there is
    # no telling which one is good, so both stay unless the release path is empty. The
    # staging folder's name gives its release; older names fall back to the backup's own.
    for stale in destination.parent.glob("tmp*"):
        if stale.is_symlink() or not stale.is_dir():
            continue
        kept = stale / "previous"
        named = re.fullmatch(r"tmp-([0-9]+\.[0-9]+\.[0-9]+)-.+", stale.name)
        try:
            version = named[1] if named else tomllib.loads((kept / "pyproject.toml").read_text())["project"]["version"]
        except (OSError, ValueError, KeyError, TypeError):
            version = None
        if not isinstance(version, str) or not release.fullmatch(version):
            if not os.path.lexists(kept):
                shutil.rmtree(stale, ignore_errors=True)
            continue
        home = destination.parent / version / "sdk"
        finished = (home / COMPLETE).is_file()
        if os.path.lexists(kept) and not finished and ((kept / COMPLETE).is_file() or not os.path.lexists(home)):
            try:
                home.parent.mkdir(exist_ok=True)
                if os.path.lexists(home):
                    os.replace(home, stale / "unfinished")
                os.replace(kept, home)
            except OSError:
                continue
        if not os.path.lexists(kept) or finished:
            shutil.rmtree(stale, ignore_errors=True)
    # A server reply must not move this machine to an older release than one already
    # installed; only an explicit --version can. Checking under the lock also counts a
    # newer release that another install finished while this one was downloading.
    # Versions compare numerically, and a release counts only once its sdk tree carries
    # the build mark: a tree a killed first install left half built never worked, and no
    # hooks use it, so it must not make every later install look like a downgrade.
    installed_releases = [
        (tuple(map(int, path.name.split("."))), path.name)
        for path in destination.parent.iterdir()
        if release.fullmatch(path.name) and (path / "sdk" / COMPLETE).is_file()
    ]
    if server_selected == "1" and installed_releases:
        newest = max(installed_releases)
        if tuple(map(int, destination.name.split("."))) < newest[0]:
            raise SystemExit(
                f"The server selected SDK release {destination.name}, older than installed release {newest[1]}. "
                f"To install it anyway, rerun with --version {destination.name}."
            )
    staging_folder = tempfile.TemporaryDirectory(dir=destination.parent, prefix=f"tmp-{destination.name}-", delete=False)
    staging = pathlib.Path(staging_folder.name)
    installed = destination / "sdk"
    previous = staging / "previous"
    built = None
    try:
        with tarfile.open(archive) as source:
            for member in source.getmembers():
                path = pathlib.PurePosixPath(member.name)
                if not path.parts or path.parts[0] != "sdk" or ".." in path.parts or not (member.isfile() or member.isdir()):
                    raise SystemExit("Unsafe SDK archive entry.")
            source.extractall(staging / "new", filter="data")
        sdk = staging / "new/sdk"
        if not (sdk / "src/watcher_sdk/cli.py").is_file() or not (sdk / "examples/github-copilot-cli/uv.lock").is_file():
            raise SystemExit("This server release does not contain the SDK integration installer. Upgrade the server first.")
        version = tomllib.loads((sdk / "pyproject.toml").read_text())["project"]["version"]
        if version != destination.name:
            raise SystemExit("SDK archive version does not match the selected release.")
        # Anything moved into the staging folder is deleted when this block exits, except a
        # previous release that an unfinished build could not put back.
        try:
            if os.path.lexists(installed):
                os.replace(installed, previous)
            os.replace(sdk, installed)
            # uv and the processes it starts share this step's hold on the lock, so if this
            # step is killed during the sync, no other install recovers or replaces releases
            # while the sync still writes into this one.
            built = subprocess.run(
                [uv, "sync", "--project", str(installed / "examples/github-copilot-cli"), "--python", python_version,
                 "--managed-python", "--locked", "--no-dev", "--no-editable", "--link-mode", "copy"],
                stdin=subprocess.DEVNULL,
                pass_fds=(lock.fileno(),),
                check=False,
            )
            # Keep this inside the try: a signal that arrives just before it must still
            # unwind into the restore, and one that arrives after it must not stop it.
            interruptible = False
            if not built.returncode:
                (installed / COMPLETE).touch()
        finally:
            # The swap or the build may have raised instead of returning, for example
            # when uv cannot start, so stop stops raising here as well.
            interruptible = False
            if built is None or built.returncode:
                # Any unfinished build, including one stopped by Ctrl-C or a closing terminal,
                # puts the previous release back before the staging folder holding it is
                # deleted, so the command and every project's hooks keep a usable release.
                # The exit can land anywhere in the swap, so the restore looks at where the
                # trees are: a new tree no longer in staging sits at the release path and
                # moves out, then a previous release still in staging moves back. stop no
                # longer raises here, so no signal can stop the restore halfway.
                if not os.path.lexists(sdk) and os.path.lexists(installed):
                    os.replace(installed, staging / "failed")
                if os.path.lexists(previous):
                    os.replace(previous, installed)
    finally:
        if os.path.lexists(previous) and (built is None or built.returncode):
            print(
                f"Could not put the previous SDK release back at {installed}; the next install will. "
                f"It is kept at {previous}.",
                file=sys.stderr,
            )
        else:
            staging_folder.cleanup()
    if built.returncode:
        raise SystemExit(built.returncode)
if signalled:
    raise SystemExit(128 + signalled)
PY
CLI="$PROJECT/.venv/bin/watcher-sdk"
BIN="${WATCHER_SDK_BIN_DIR:-$HOME/.local/bin}"
mkdir -p "$BIN"
"$PYTHON" -I - "$BIN/watcher-sdk" "$ROOT/releases" "$CLI" <<'CHECK'
import pathlib, sys
target, releases, source = map(pathlib.Path, sys.argv[1:])
if (target.exists() or target.is_symlink()) and (not target.is_symlink() or not target.resolve().is_relative_to(releases.resolve())):
    raise SystemExit("The watcher-sdk command path belongs to another installation.")
if not target.exists() and not target.is_symlink():
    target.symlink_to(source)
CHECK
# The command needs no release lock, and closing its copy keeps anything it leaves
# running from holding the lock after this install exits.
if (: </dev/tty) 2>/dev/null; then
    "$CLI" integrations install "${ARGS[@]}" </dev/tty 9>&-
else
    "$CLI" integrations install "${ARGS[@]}" </dev/null 9>&-
fi
"$PYTHON" -I - "$CLI" "$BIN/watcher-sdk" "$ROOT/releases" "$VERSION" "$SERVER_SELECTED" <<'PY'
import fcntl, os, pathlib, re, sys
source, target, releases = map(pathlib.Path, sys.argv[1:4])
version, server_selected = sys.argv[4:]
with (releases / ".extract.lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    if (target.exists() or target.is_symlink()) and (not target.is_symlink() or not target.resolve().is_relative_to(releases.resolve())):
        raise SystemExit("The watcher-sdk command path belongs to another installation.")
    # Another install may have moved the command to a newer release after this one
    # checked for one. A server-selected release then leaves the command there, the
    # same result as if this install had finished first; only --version moves it back.
    current = next(iter(target.resolve().relative_to(releases.resolve()).parts), "") if target.is_symlink() else ""
    if (
        server_selected == "1"
        and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", current)
        and (releases / current / "sdk").is_dir()
        and tuple(map(int, current.split("."))) > tuple(map(int, version.split(".")))
    ):
        print(f"The watcher-sdk command stays on newer release {current}; the Copilot hooks just installed use release {version}.")
    else:
        temporary = target.with_name(target.name + "." + str(os.getpid()))
        temporary.symlink_to(source)
        os.replace(temporary, target)
PY
echo "Installed command: $BIN/watcher-sdk"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "Add $BIN to PATH to use watcher-sdk in new terminals." ;; esac
