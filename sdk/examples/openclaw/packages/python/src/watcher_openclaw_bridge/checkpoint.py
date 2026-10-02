"""Bound checkpoint filesystem work in a disposable process, without storing content.

The worker owns the nonblocking session lock. A stalled filesystem cannot retain
an observation callback indefinitely: each exchange has a two-second deadline,
and the caller kills and reaps its own worker on completion or interruption.
"""

import asyncio
import hashlib
import json
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from filelock import FileLock, Timeout

MAX_STATE_BYTES = 4 * 1024 * 1024


def state_path(identity: str, destination: str, api_key: str) -> Path:
    """Separate destinations and credentials without retaining either value on disk."""
    root = Path(os.environ.get("WATCHER_OBSERVATION_STATE_DIR", str(Path.home() / ".local/state/watcher-sdk-examples")))
    key = hashlib.sha256(json.dumps([identity, destination.rstrip("/"), api_key]).encode()).hexdigest()
    return root / (key + ".json")


def call_fingerprint(call: dict) -> str:
    """Match the native ID, name and arguments used by the SDK's recorded-call reuse."""
    value = {key: call[key] for key in ("id", "function", "arguments")}
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def valid_hashes(values: object) -> set[str]:
    """Refuse corrupt progress instead of silently treating it as completed work."""
    if not isinstance(values, list) or any(
        not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
        for value in values
    ):
        raise ValueError("Invalid observation checkpoint")
    return {value for value in values if isinstance(value, str)}


async def exchange(worker: asyncio.subprocess.Process, payload: dict) -> dict:
    """Bound filesystem/protocol waits; no transcript or credential enters this channel."""
    assert worker.stdin is not None and worker.stdout is not None
    async with asyncio.timeout(2):
        worker.stdin.write(json.dumps(payload).encode() + b"\n")
        await worker.stdin.drain()
        response = json.loads(await worker.stdout.readline())
    if "error" in response:
        raise ValueError(response["error"])
    return response


class Checkpoint:
    """Advance only after matching judgments and SDK recording confirmation."""

    def __init__(self, worker: asyncio.subprocess.Process | None, completed: set[str]):
        self.worker = worker
        self.completed = completed

    async def save(self, completed: set[str]) -> None:
        """Persist before acknowledging local progress; a failed write remains retryable."""
        if self.worker is not None:
            response = await exchange(self.worker, {"add": sorted(completed)})
            if response != {"ok": True}:
                raise ValueError("Checkpoint did not confirm progress")
        self.completed.update(completed)


@asynccontextmanager
async def open_checkpoint(path: Path | None):
    """Hold one session lock without unbounded event-loop or thread shutdown waits.

    Filesystem operations happen in a child process, not an executor thread that
    can survive cancellation. Shutdown has a separate two-second cleanup budget.
    """
    if path is None:
        yield Checkpoint(None, set())
        return
    worker = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        __name__,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        limit=MAX_STATE_BYTES + 1024,
    )
    try:
        response = await exchange(worker, {"path": str(path)})
        yield Checkpoint(worker, valid_hashes(response["completed"]))
    finally:
        if worker.returncode is None:
            worker.kill()
        await asyncio.wait_for(worker.wait(), 2)


def save_hashes(path: Path, completed: set[str]) -> None:
    """Replace one owner-private checkpoint atomically after a completed SDK response."""
    data = json.dumps(sorted(completed))
    if len(data.encode()) > MAX_STATE_BYTES:
        raise ValueError("Observation checkpoint reached its size limit")
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        output.write(data)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def worker_main() -> None:
    """Serve hash-only progress while holding the same nonblocking file lock."""
    try:
        request = json.loads(sys.stdin.readline())
        path = Path(request["path"])
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with FileLock(str(path) + ".lock", timeout=0):
            completed = set()
            if path.exists():
                with path.open("rb") as source:
                    data = source.read(MAX_STATE_BYTES + 1)
                if len(data) > MAX_STATE_BYTES:
                    raise ValueError("Observation checkpoint reached its size limit")
                completed = valid_hashes(json.loads(data))
            sys.stdout.write(json.dumps({"completed": sorted(completed)}) + "\n")
            sys.stdout.flush()
            for line in sys.stdin:
                completed.update(valid_hashes(json.loads(line)["add"]))
                save_hashes(path, completed)
                sys.stdout.write('{"ok": true}\n')
                sys.stdout.flush()
    except Timeout:
        sys.stdout.write('{"error": "Another observation is still checking this session"}\n')
        sys.stdout.flush()
    except Exception:
        sys.stdout.write('{"error": "Observation checkpoint could not be used"}\n')
        sys.stdout.flush()


if __name__ == "__main__":
    worker_main()
