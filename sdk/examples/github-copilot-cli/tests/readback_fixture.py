"""Serve the public-API readback that confirms a recorded snapshot, for mocked Watcher transports."""

import json
from collections.abc import Awaitable, Callable, Coroutine
from pathlib import Path

import httpx

SESSION_ID = "65dc89f8-e94d-4f54-8503-cb218d015a18"
Handler = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]


def serve_readback(handler: Handler) -> Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]:
    """Answer session search and trajectory reads from the last accepted snapshot; pass other requests on."""
    stored: list[list[object]] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/sessions/search"):
            sessions = (
                [
                    {
                        "session_id": SESSION_ID,
                        "agent_platform": "other",
                        "trajectory_count": 1,
                        "message_count": len(stored[-1]),
                        "started_at": "2026-09-29T12:00:00Z",
                        "ended_at": "2026-09-29T12:00:01Z",
                        "latest_trajectory_id": "stored-trajectory",
                    }
                ]
                if stored
                else []
            )
            return httpx.Response(200, json={"sessions": sessions, "total": len(sessions), "limit": 2, "offset": 0})
        if "/trajectories/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "trajectory_id": "stored-trajectory",
                    "session_id": SESSION_ID,
                    "source": "watcher-hook",
                    "messages": stored[-1],
                    "grades": [],
                    "metadata": {},
                    "created_at": "2026-09-29T12:00:01Z",
                },
            )
        pending_response = handler(request)
        response = pending_response if isinstance(pending_response, httpx.Response) else await pending_response
        if request.url.path.endswith("/hooks/pre-tool-use") and response.status_code == 200:
            body = json.loads(request.content)
            if not body["input"]:
                stored.append(body["messages"])
        return response

    return respond


def save_watcher_login(state_dir: Path, watcher_url: str, token: str = "fixture-login") -> Path:
    """Write a saved Watcher login for ``watcher_url`` under ``state_dir``, where the Watcher app keeps it."""
    from watcher_sdk.local_auth import WatcherLoginAuth

    path = WatcherLoginAuth(watcher_url, state_dir=state_dir).credential_file
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps({"access_token": token, "refresh_token": "fixture-refresh", "xylon_url": watcher_url}))
    path.chmod(0o600)
    return path


def login_configuration(
    path: Path, project: Path, watcher_url: str, *, gate_timeout: int | None = None, token: str = "fixture-login"
) -> Path:
    """Write a hook configuration at ``path`` that authenticates with a saved Watcher login beside it.

    The login store is ``path``'s sibling ``watcher`` directory. With
    ``gate_timeout`` the configuration also records an installed gate's timeout.
    """
    state_dir = path.parent / "watcher"
    save_watcher_login(state_dir, watcher_url, token)
    document: dict[str, object] = {
        "project": str(project),
        "watcher_url": watcher_url,
        "watcher_auth": True,
        "watcher_state_dir": str(state_dir),
        "hook": {"exec": "/python", "args": []},
    }
    if gate_timeout is not None:
        document["gate"] = {"exec": "/python", "args": [], "timeoutSec": gate_timeout}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document))
    return path
