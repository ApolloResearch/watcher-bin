"""Run the installed Copilot CLI fixture and preserve its package/environment checks."""

import os
import runpy
from pathlib import Path

if __name__ == "__main__":
    directory = Path(__file__).parent
    os.chdir(directory)
    runpy.run_path(str(directory / "entry.py"), run_name="__main__")
