"""Opt-in, unrecorded Watcher judgments for documented Windsurf pre-hook actions.

Windsurf does not supply a model tool ID or complete current transcript on these
hooks. This module deliberately uses ephemeral evaluation with no invented ID;
integration.py remains the separate completed-transcript archive.
"""

import asyncio
import json
import math
import os
import sys

from watcher_sdk import AsyncWatcherClient


def validate_json(value: object) -> None:
    """Refuse non-JSON/coerced arguments before evaluating the native action."""
    if value is None or type(value) in {str, bool, int}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Non-finite arguments are not supported")
        return
    if type(value) is list:
        for item in value:
            validate_json(item)
        return
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("JSON keys must be strings")
        for item in value.values():
            validate_json(item)
        return
    raise ValueError("Only JSON values are supported")


async def apply_policy(client: AsyncWatcherClient, payload: dict) -> None:
    """Apply inherited Watcher policy to the exact documented pre-hook action.

    This does not record a decision. Valid observe/paused deferrals preserve
    native dispatch; denials, escalations and malformed outcomes withhold it. Native
    call/result linkage and intent-in-conversation are unavailable. Full grading
    has a 420-second default budget, configurable with WATCHER_TIMEOUT_SECONDS.
    The native hook deadline is unknown: verify that it can accommodate this
    request plus startup before using the example in an IDE.
    """
    event = payload["agent_action_name"]
    required = {
        "pre_read_code": {"file_path"},
        "pre_write_code": {"file_path", "edits"},
        "pre_run_command": {"command_line", "cwd"},
        "pre_mcp_tool_use": {"mcp_server_name", "mcp_tool_name", "mcp_tool_arguments"},
    }
    if event not in required:
        raise ValueError("Only documented pre-tool actions are supported")
    arguments = payload["tool_info"]
    if not isinstance(arguments, dict) or not required[event] <= arguments.keys():
        raise ValueError("The pending action is incomplete")
    for key in required[event] - {"edits", "mcp_tool_arguments"}:
        if not isinstance(arguments[key], str) or not arguments[key]:
            raise ValueError("Native action identifiers must be nonempty strings")
    if event == "pre_write_code":
        if not isinstance(arguments["edits"], list) or any(
            not isinstance(edit, dict)
            or not isinstance(edit.get("old_string"), str)
            or not isinstance(edit.get("new_string"), str)
            for edit in arguments["edits"]
        ):
            raise ValueError("Unsupported native edit shape")
    if event == "pre_mcp_tool_use" and not isinstance(arguments["mcp_tool_arguments"], dict):
        raise ValueError("MCP arguments must be an object")
    validate_json(arguments)
    timeout = float(os.environ.get("WATCHER_TIMEOUT_SECONDS", "420"))
    if not math.isfinite(timeout) or not 0 < timeout <= 420:
        raise ValueError("Invalid SDK deadline")
    submitted = {"tool_name": event, "tool_input": arguments}
    if "cwd" in arguments:
        submitted["cwd"] = arguments["cwd"]
    response = await client.pre_tool_use_hook(
        input=submitted,
        messages=[],
        ephemeral=True,
        mode="full",
        timeout=timeout,
    )
    if isinstance(response, list):
        raise PermissionError("Watcher returned an unexpected batch response")
    serialize = getattr(response, "to_dict", None)
    if not callable(serialize):
        raise PermissionError("Watcher returned an invalid tool outcome")
    outcome = serialize()
    if outcome.get("tool_use_id") is not None:
        raise PermissionError("Watcher returned another call's decision")
    source, failure = outcome.get("decision_source"), outcome.get("grading_error")
    if source == "grading_error":
        if (
            not isinstance(failure, dict)
            or failure.get("code")
            not in {"timeout", "at_capacity", "allowance_exhausted", "grader_failed", "no_result"}
            or not isinstance(failure.get("message"), str)
        ):
            raise PermissionError("Watcher returned invalid grading-failure provenance")
    elif failure is not None:
        raise PermissionError("Watcher returned inconsistent grading provenance")
    decision, mode = outcome.get("decision"), outcome.get("enforcement_mode")
    if decision == "deferred":
        if mode == "paused" and source == "bypass" and outcome.get("judged_decision") is None:
            return
        if (
            mode == "observe"
            and source in {"threshold", "rule", "triage", "policy_gateway", "grading_error"}
            and outcome.get("judged_decision") in {"allow", "deny", "escalate"}
        ):
            return
        raise PermissionError("Watcher returned an inconsistent deferred decision")
    if (
        mode != "enforce"
        or source not in {"threshold", "rule", "triage", "policy_gateway", "grading_error"}
        or decision not in {"allow", "deny", "escalate"}
        or outcome.get("judged_decision") != decision
    ):
        raise PermissionError("Watcher returned an inconsistent applied decision")
    if decision != "allow":
        raise PermissionError("Watcher withheld this call; no human approval interface is configured")


async def run_hook(payload: dict) -> None:
    """Use a session's explicitly configured Watcher credentials without policy overrides."""
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as client:
        await apply_policy(client, payload)


def main() -> int:
    """Use the documented native exit-2 veto for every judgment or bridge failure."""
    try:
        asyncio.run(run_hook(json.load(sys.stdin)))
    except Exception:
        sys.stderr.write("Watcher did not confirm approval; action withheld.\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
