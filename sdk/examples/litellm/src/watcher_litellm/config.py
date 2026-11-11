"""Write the packaged LiteLLM configuration to stdout for the proxy CLI.

Run ``watcher-litellm-config > config.yaml`` after installation and edit the
model list for your providers. Environment variable references stay literal;
credentials are read only by the running proxy.
"""

import sys
from importlib.resources import files


def main() -> None:
    """Emit the shipped YAML without modifying files or environment settings."""
    sys.stdout.write(files("watcher_litellm").joinpath("config.yaml").read_text())


def copilot_main() -> None:
    """Emit the native Copilot reference configuration without reading credentials."""
    sys.stdout.write(files("watcher_litellm").joinpath("copilot.yaml").read_text())
