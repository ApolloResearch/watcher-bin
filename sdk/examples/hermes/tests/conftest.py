"""Shared fixture: a stand-in ``hermes`` command that prints a captured session export."""

import stat
import sys

import pytest


@pytest.fixture
def fake_hermes(tmp_path):
    """Return a factory for a ``hermes`` executable that prints a given export.

    The script ignores its arguments except to record them, prints ``output``
    to stdout and exits with ``returncode`` after ``sleep`` seconds.
    """

    def make(output: str, *, returncode: int = 0, sleep: float = 0) -> str:
        data = tmp_path / "export.txt"
        data.write_text(output)
        script = tmp_path / "hermes"
        script.write_text(
            f"#!{sys.executable}\n"
            "import sys, time, pathlib\n"
            f"pathlib.Path({str(tmp_path / 'argv.json')!r}).write_text(__import__('json').dumps(sys.argv[1:]))\n"
            f"time.sleep({sleep})\n"
            f"sys.stdout.write(pathlib.Path({str(data)!r}).read_text())\n"
            f"sys.exit({returncode})\n"
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return str(script)

    return make
