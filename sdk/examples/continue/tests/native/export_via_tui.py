"""Drive Continue's public terminal export command in a disposable test workspace."""

import fcntl
import os
import pty
import select
import struct
import subprocess
import termios
import time
from pathlib import Path


def export_session(cli: str, config: Path, workspace: Path, environment: dict[str, str], evidence: Path) -> Path:
    """Resume the fixture session, use /export, and return the native JSON export."""
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
    process = subprocess.Popen(
        [cli, "--config", str(config), "--resume"],
        cwd=workspace,
        env={**environment, "TERM": "xterm-256color"},
        stdin=slave,
        stdout=slave,
        stderr=slave,
        start_new_session=True,
    )
    os.close(slave)
    captured = bytearray()
    deadline = time.monotonic() + 90
    stage = 0
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    block = os.read(master, 65536)
                except OSError:
                    break
                if not block:
                    break
                captured.extend(block)
                text = captured.decode(errors="replace")
                if stage == 0 and ("Fixture" in text or "gpt-4o" in text):
                    os.write(master, b"/export")
                    stage = 1
                elif stage == 1 and "/export" in text:
                    os.write(master, b"\r")
                    stage = 2
                elif stage == 2 and "Recent Sessions" in text and "You:" in text:
                    os.write(master, b"\r")
                    stage = 3
            exports = list(workspace.glob("continue-session-*.json"))
            if exports:
                assert len(exports) == 1
                os.write(master, b"\x03\x03")
                return exports[0]
            if process.poll() is not None:
                break
        raise RuntimeError(f"Native /export did not produce a JSON file; terminal stage={stage}")
    finally:
        (evidence / "tui-output.txt").write_bytes(captured)
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        os.close(master)
