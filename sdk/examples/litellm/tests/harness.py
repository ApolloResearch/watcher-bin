"""Start the installed ``litellm`` proxy CLI with the packaged callback, as a deployment would."""

import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import uvicorn
import yaml
from starlette.types import ASGIApp


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def serve_in_thread(app: ASGIApp) -> str:
    """Run an ASGI app on a free loopback port for the rest of the test session."""
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.02)
    return f"http://127.0.0.1:{port}"


@contextmanager
def litellm_proxy(
    model_list: list[dict[str, Any]],
    env: dict[str, str],
    workdir: Path,
    *,
    callback: str = "watcher_litellm.callback.watcher_callback",
) -> Iterator[str]:
    """Run ``litellm --config`` with the Watcher callback and yield its base URL.

    Only basic process variables and coverage instrumentation are inherited,
    plus ``env``, so a developer's database or LiteLLM settings cannot leak in.
    The log is ``workdir/proxy.log``.
    """
    config = workdir / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "model_list": model_list,
                "litellm_settings": {"callbacks": callback, "telemetry": False},
                "general_settings": {"disable_spend_logs": True},
            }
        )
    )
    inherited = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "TMPDIR", "LANG", "COVERAGE_PROCESS_CONFIG", "COVERAGE_CORE"}
    }
    # In its default DEV mode the CLI loads the nearest .env file, which inside
    # this checkout belongs to the Watcher server and names its database.
    full_env = {**inherited, "LITELLM_MODE": "PRODUCTION", "LITELLM_LOG": "ERROR", **env}
    port = free_port()
    log_path = workdir / "proxy.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(
            [
                str(Path(sys.executable).parent / "litellm"),
                "--config",
                str(config),
                "--port",
                str(port),
                "--host",
                "127.0.0.1",
            ],
            env=full_env,
            cwd=workdir,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 90
        try:
            while True:
                try:
                    if httpx.get(f"{url}/health/liveliness", timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError(f"LiteLLM proxy did not start; see {log_path}")
                time.sleep(0.25)
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
