import re
import subprocess
import sys
import tomllib
from pathlib import Path


def pin_key(name: str, version: str) -> str:
    return f"{re.sub(r'[-_.]+', '-', name).lower()}=={version}"


# pip check rejects every uv override by design; accept a conflict only when the installed version is an exact-pin override.
overrides = (
    tomllib.loads(Path("pyproject.toml").read_text()).get("tool", {}).get("uv", {}).get("override-dependencies", [])
)
pins = {pin_key(name, version) for name, pinned, version in (s.partition("==") for s in overrides) if pinned}
conflict = re.compile(r"^\S+ \S+ has requirement .+, but you have (?P<name>\S+) (?P<version>\S+)\.$")


def is_intended(line: str) -> bool:
    match = conflict.match(line)
    return match is not None and pin_key(match["name"], match["version"]) in pins


result = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True)
print(result.stdout, end="")
if result.stderr or result.returncode not in (0, 1):
    sys.exit(f"pip check exited {result.returncode}:\n{result.stderr}")
lines = result.stdout.splitlines()
if result.returncode == 0:
    if lines != ["No broken requirements found."]:
        sys.exit("pip check succeeded with unexpected output")
elif not lines:
    sys.exit("pip check failed without reporting a conflict")
elif unexpected := [line for line in lines if not is_intended(line)]:
    sys.exit("pip check found conflicts outside override-dependencies:\n" + "\n".join(unexpected))
