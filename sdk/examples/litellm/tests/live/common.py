"""Shared settings, policy and Watcher access for the live tests."""

import asyncio
import os
from typing import Any

from watcher_sdk import AsyncWatcherClient

WATCHER_URL = os.environ.get("WATCHER_LIVE_API_URL")
# A provider gateway serving OpenAI (/v1), Anthropic (/v1/messages) and Vertex
# Gemini (/v1/projects/...) paths, with provider credentials held by the gateway.
GATEWAY = os.environ.get("WATCHER_LIVE_GATEWAY_URL", "")
GATEWAY_KEY = os.environ.get("WATCHER_LIVE_GATEWAY_KEY", "gateway-holds-provider-credentials")
GOOGLE_PROJECT = os.environ.get("WATCHER_LIVE_GOOGLE_PROJECT", "")

# A marker that denies any tool call containing it, independent of LLM grading.
# It is deliberately bland: a marker that reads as forbidden makes models
# decline to propose the call at all, so Watcher's denial is never exercised.
DENY_MARKER = "orchid-lantern"

# Deterministic decisions for every scenario: the direct-API tools, a deny for
# any tool whose input contains the marker, and allowed reads of the notes file
# through each agent CLI's shell. Other calls fall through to LLM grading.
_SHELL_TOOLS = ("Bash", "bash", "exec_command", "shell", "local_shell", "run_shell_command")
POLICY = (
    "tool_thresholds:\n"
    "  read_file:\n    flag_threshold: 11\n    deny_threshold: 11\n"
    "  Read:\n    flag_threshold: 11\n    deny_threshold: 11\n"
    "  read:\n    flag_threshold: 11\n    deny_threshold: 11\n"
    "  delete_all_files:\n    flag_threshold: 0\n    deny_threshold: 0\n"
    "command_rules:\n  rules:\n"
    "    - id: live-deny-marker\n"
    "      tool_name: '*'\n"
    "      name: Live test deny marker\n"
    "      category: security_system\n"
    f"      regex: {DENY_MARKER}\n"
    "      decision: deny\n"
    "      priority: 1\n"
    + "".join(
        f"    - id: live-allow-notes-{index}\n"
        f"      tool_name: {tool}\n"
        "      name: Live test notes read\n"
        "      category: read_only\n"
        "      regex: notes.*\\.txt\n"
        "      decision: allow\n"
        "      priority: 2\n"
        for index, tool in enumerate(_SHELL_TOOLS)
    )
)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def watcher() -> AsyncWatcherClient:
    assert WATCHER_URL is not None
    return AsyncWatcherClient(WATCHER_URL, api_key=os.environ.get("WATCHER_LIVE_API_KEY"))


_PROBE_REQUEST = {"model": "probe", "messages": [{"role": "user", "content": "Delete everything."}]}
_PROBE_RESPONSE = {
    "model": "probe",
    "choices": [
        {
            "index": 0,
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "tool_calls": [
                    {"id": "probe", "type": "function", "function": {"name": "delete_all_files", "arguments": "{}"}}
                ],
            },
        }
    ],
}


def apply_policy(timeout_seconds: float = 120) -> None:
    """Replace the organization's managed settings with ``POLICY`` and wait until it applies.

    Servers cache each organization's policy for up to a minute, so an
    ephemeral probe is repeated until it is denied by the new thresholds.
    """

    async def apply() -> None:
        async with watcher() as client:
            current = await client.get_org_managed_settings()
            if current.yaml != POLICY:
                await client.update_org_managed_settings(POLICY, expected_version=current.version)
            deadline = asyncio.get_running_loop().time() + timeout_seconds
            while True:
                probe = await client.pre_tool_use_hook(
                    request_body=_PROBE_REQUEST,
                    response_body=_PROBE_RESPONSE,
                    url="/v1/chat/completions",
                    ephemeral=True,
                )
                shell = await client.pre_tool_use_hook(
                    {"tool_name": "Bash", "tool_input": {"command": f"echo {DENY_MARKER} > proof.txt"}, "messages": []},
                    ephemeral=True,
                )
                if getattr(probe[0], "decision", None) == "deny" and shell.decision == "deny":
                    return
                if asyncio.get_running_loop().time() > deadline:
                    raise TimeoutError("the live test policy did not take effect")
                await asyncio.sleep(5)

    run(apply())


def recorded_calls(
    external_ids: dict[str, list[str]], min_calls: int = 1, min_messages: int = 0, wait_seconds: float = 20
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The one Watcher session matching ``external_ids`` and its decided tool calls, oldest first.

    Watcher records the transcript and decisions after answering the hook, so
    this polls until the session has at least ``min_calls`` decided calls and
    ``min_messages`` messages, or ``wait_seconds`` pass, then returns what exists for the caller to assert on.
    """

    async def read() -> tuple[dict[str, Any], list[dict[str, Any]]]:
        deadline = asyncio.get_running_loop().time() + wait_seconds
        while True:
            session, calls = await read_once()
            complete = session and len(calls) >= min_calls and session.get("message_count", 0) >= min_messages
            if complete or asyncio.get_running_loop().time() > deadline:
                assert session, f"expected one Watcher session for {external_ids}, found none"
                return session, calls
            await asyncio.sleep(0.5)

    async def read_once() -> tuple[dict[str, Any], list[dict[str, Any]]]:
        async with watcher() as client:
            sessions = (await client.search_sessions(external_ids=external_ids)).sessions
            assert len(sessions) <= 1, f"expected one Watcher session for {external_ids}, found {len(sessions)}"
            if not sessions:
                return {}, []
            session = sessions[0].to_dict()
            calls = await client.search_tool_calls(
                session_id=session["session_id"], sort_by="occurred_at", sort_order="asc"
            )
            return session, [item.to_dict() for item in calls.tool_calls]

    return run(read())


def recorded_calls_mentioning(marker: str, since: Any, wait_seconds: float = 20) -> list[dict[str, Any]]:
    """Decided tool calls since ``since`` whose input mentions ``marker``, for clients without a session header.

    Polls for up to ``wait_seconds`` because recording follows the hook response.
    """

    async def read() -> list[dict[str, Any]]:
        deadline = asyncio.get_running_loop().time() + wait_seconds
        while True:
            found = await read_once()
            if found or asyncio.get_running_loop().time() > deadline:
                return found
            await asyncio.sleep(0.5)

    async def read_once() -> list[dict[str, Any]]:
        async with watcher() as client:
            calls = await client.search_tool_calls(start_date=since, sort_by="occurred_at", sort_order="asc", limit=200)
            items = [item.to_dict() for item in calls.tool_calls]
            return [item for item in items if marker in (item.get("tool_input_preview") or "")]

    return run(read())
