"""Exercise the recorded veto and its ephemeral fallbacks through real public SDK serialization."""

import asyncio
import json
import time
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from pydantic import JsonValue
from test_identity import MILLIS, hook_start
from watcher_github_copilot_cli import identity, integration
from watcher_github_copilot_cli.diagnostics import escalated_calls, read_review_evidence
from watcher_github_copilot_cli.identity import PendingTool, submitted_call
from watcher_github_copilot_cli.integration import Escalation, apply_policy
from watcher_github_copilot_cli.reviews import call_hash
from watcher_github_copilot_cli.transcript import convert_session

from watcher_sdk import AsyncWatcherClient, WatcherError

PAYLOAD: dict[str, JsonValue] = {
    "sessionId": "native-session",
    "toolName": "bash",
    "toolArgs": {"command": "pwd"},
    "cwd": "/workspace",
}


@pytest.fixture(autouse=True)
def short_identity_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    # A callback whose call never appears in the log waits for it; keep that short here.
    monkeypatch.setattr(identity, "IDENTITY_WAIT_SECONDS", 0.2)


@pytest.mark.parametrize(
    "failure", [None, "deny", "escalate", "deferred", "paused", "observe", "no-judgment", "unknown-source", "http"]
)
def test_only_complete_allow_permits_effect(tmp_path: Path, failure: str | None) -> None:
    marker = tmp_path / "effect"
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        assert body["ephemeral"] is True and body["messages"] == [] and "external_ids" not in body
        assert "settings_overrides" not in body and "tool_use_id" not in body["input"]
        outcome = {
            "decision": "allow",
            "judged_decision": "allow",
            "enforcement_mode": "enforce",
            "decision_source": "rule",
            "verdict": {},
            "latency_ms": 1,
        }
        if failure in {"deny", "escalate", "deferred"}:
            outcome["decision"] = failure
        if failure in {"paused", "observe"}:
            outcome["enforcement_mode"] = failure
        if failure == "no-judgment":
            outcome.pop("judged_decision")
        if failure == "unknown-source":
            outcome["decision_source"] = "unknown"
        return httpx.Response(
            503 if failure == "http" else 200, json={"error": {"message": "fixture"}} if failure == "http" else outcome
        )

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, PAYLOAD)
            marker.write_text("executed")

    if failure is None:
        asyncio.run(run())
        assert marker.exists()
    else:
        with pytest.raises((PermissionError, WatcherError, KeyError, TypeError, ValueError)):
            asyncio.run(run())
        assert not marker.exists()
    assert len(requests) == 1


@pytest.mark.parametrize("timeout", ["0", "-1", "421", "nan", "inf", "broken"])
def test_invalid_deadline_is_refused(monkeypatch: pytest.MonkeyPatch, timeout: str) -> None:
    monkeypatch.setenv("WATCHER_TIMEOUT_SECONDS", timeout)

    async def run():
        async with AsyncWatcherClient("http://fixture") as client:
            await apply_policy(client, PAYLOAD)

    with pytest.raises(ValueError):
        asyncio.run(run())


ALLOW: dict[str, JsonValue] = {
    "decision": "allow",
    "judged_decision": "allow",
    "enforcement_mode": "enforce",
    "decision_source": "rule",
    "verdict": {},
    "latency_ms": 1,
}


@pytest.mark.parametrize("raw", ["not a patch", "[]", "7"])
def test_freeform_tool_input_is_judged_as_raw_text(raw: str) -> None:
    received: list[JsonValue] = []

    def respond(request: httpx.Request) -> httpx.Response:
        received.append(json.loads(request.content)["input"])
        return httpx.Response(200, json=ALLOW)

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, {**PAYLOAD, "toolName": "apply_patch", "toolArgs": raw})

    asyncio.run(run())
    assert received == [{"tool_name": "apply_patch", "tool_input": {"input": raw}, "cwd": "/workspace"}]


MULTI_FILE_PATCH = (
    "*** Begin Patch\n*** Update File: status.txt\n@@\n-pending\n+complete\n"
    "*** Add File: sub/.watcher-ignore\n+skip\n*** End Patch\n"
)


@pytest.mark.parametrize("further,expected", [("allow", None), ("escalate", "escalate"), ("deny", "deny")])
def test_multi_file_patch_applies_the_strictest_decision_across_paths(further: str, expected: str | None) -> None:
    received: list[dict[str, JsonValue]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        received.append(body)
        is_further = body["input"]["tool_input"]["file_path"] != "status.txt"
        decision = further if is_further else "allow"
        return httpx.Response(200, json={**ALLOW, "decision": decision, "judged_decision": decision})

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            return await apply_policy(client, {**PAYLOAD, "toolName": "apply_patch", "toolArgs": MULTI_FILE_PATCH})

    if expected is None:
        assert asyncio.run(run()) == "allow"
    else:
        with pytest.raises(integration.Escalation if expected == "escalate" else integration.PolicyDenial):
            asyncio.run(run())
    inputs = [(body["input"]["tool_name"], body["input"]["tool_input"]["file_path"]) for body in received]
    # A withheld later path leaves nothing for the first path's judgment to change.
    assert inputs == [("Write", "sub/.watcher-ignore")] + ([] if expected == "deny" else [("Edit", "status.txt")])
    assert all(body["ephemeral"] is True for body in received)
    if expected != "deny":
        assert received[-1]["input"]["tool_input"]["file_paths"] == ["status.txt", "sub/.watcher-ignore"]


def test_a_batch_answer_for_a_later_patch_path_withholds_the_call() -> None:
    received: list[dict[str, JsonValue]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        received.append(json.loads(request.content))
        return httpx.Response(200, json=[ALLOW])

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, {**PAYLOAD, "toolName": "apply_patch", "toolArgs": MULTI_FILE_PATCH})

    with pytest.raises(ValueError, match="batch"):
        asyncio.run(run())
    assert [body["input"]["tool_input"]["file_path"] for body in received] == ["sub/.watcher-ignore"]


@pytest.mark.parametrize("protected_first", [True, False])
def test_a_write_deny_covers_an_added_file_in_any_position_of_a_patch(protected_first: bool) -> None:
    files = ["*** Add File: protected/new.txt\n+secret\n", "*** Add File: public.txt\n+hi\n"]
    patch = "*** Begin Patch\n" + "".join(files if protected_first else files[::-1]) + "*** End Patch\n"

    def respond(request: httpx.Request) -> httpx.Response:
        # A Write-only deny rule for protected/, as an administrator might write it.
        tool = json.loads(request.content)["input"]
        denied = tool["tool_name"] == "Write" and str(tool["tool_input"]["file_path"]).startswith("protected/")
        decision = "deny" if denied else "allow"
        return httpx.Response(200, json={**ALLOW, "decision": decision, "judged_decision": decision})

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            return await apply_policy(client, {**PAYLOAD, "toolName": "apply_patch", "toolArgs": patch})

    with pytest.raises(integration.PolicyDenial):
        asyncio.run(run())


def test_json_encoded_argument_object_is_decoded() -> None:
    received: list[JsonValue] = []

    def respond(request: httpx.Request) -> httpx.Response:
        received.append(json.loads(request.content)["input"]["tool_input"])
        return httpx.Response(200, json=ALLOW)

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, {**PAYLOAD, "toolArgs": '{"command": "pwd"}'})

    asyncio.run(run())
    assert received == [{"command": "pwd"}]


def test_slow_response_cannot_outlast_the_gate_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WATCHER_TIMEOUT_SECONDS", "0.2")

    async def respond(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json=ALLOW)

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, PAYLOAD)

    loop_started = asyncio.new_event_loop()
    try:
        started = loop_started.time()
        with pytest.raises(TimeoutError):
            loop_started.run_until_complete(run())
        assert loop_started.time() - started < 2
    finally:
        loop_started.close()


@pytest.mark.parametrize("arguments", [[], None, 7])
def test_invalid_argument_shapes_never_reach_transport(arguments: JsonValue) -> None:
    async def run():
        async with AsyncWatcherClient("http://fixture") as client:
            await apply_policy(client, {**PAYLOAD, "toolArgs": arguments})

    with pytest.raises(ValueError):
        asyncio.run(run())


def test_pending_decision_withholds_effect(tmp_path: Path) -> None:
    marker = tmp_path / "effect"

    async def run():
        entered = asyncio.Event()
        released = asyncio.Event()

        async def respond(request: httpx.Request) -> httpx.Response:
            entered.set()
            await released.wait()
            return httpx.Response(
                200,
                json={
                    "decision": "allow",
                    "judged_decision": "allow",
                    "enforcement_mode": "enforce",
                    "decision_source": "rule",
                    "verdict": {},
                    "latency_ms": 1,
                },
            )

        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:

            async def operation():
                await apply_policy(client, PAYLOAD)
                marker.write_text("executed")

            task = asyncio.create_task(operation())
            await entered.wait()
            assert not task.done() and not marker.exists()
            released.set()
            await task

    asyncio.run(run())
    assert marker.exists()


def judged(payload: dict[str, JsonValue], *, config: Path | None = None) -> dict[str, JsonValue]:
    """Send one payload through the gate and return the request body Watcher received."""
    received: list[dict[str, JsonValue]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        received.append(body)
        # Watcher echoes the named call's ID, as the real server does.
        return httpx.Response(200, json={**ALLOW, "tool_use_id": body["input"].get("tool_use_id")})

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, payload, config=config)

    asyncio.run(run())
    [body] = received
    return body


@pytest.mark.parametrize(
    "name,arguments,policy_name,policy_input",
    [
        (
            "bash",
            {"command": "rm -rf build", "description": "x"},
            "Bash",
            {"command": "rm -rf build", "description": "x"},
        ),
        ("view", {"path": "/home/u/.ssh/id_rsa"}, "Read", {"file_path": "/home/u/.ssh/id_rsa"}),
        ("create", {"path": "a.txt", "file_text": "hi"}, "Write", {"file_text": "hi", "file_path": "a.txt"}),
        (
            "edit",
            {"path": "a.txt", "old_str": "a", "new_str": "b"},
            "Edit",
            {"old_str": "a", "new_str": "b", "file_path": "a.txt"},
        ),
        ("glob", {"pattern": "*.py"}, "Glob", {"pattern": "*.py"}),
        ("rg", {"pattern": "key", "paths": ["."]}, "Grep", {"pattern": "key", "paths": ["."]}),
        ("view", {"path": 7}, "Read", {"path": 7}),
        (
            "write_bash",
            {"shellId": "0", "input": "rm -rf build\n", "command": "git status"},
            "Bash",
            {"command": "rm -rf build\n", "shellId": "0"},
        ),
        ("local_shell", {"command": "rm -rf build"}, "Bash", {"command": "rm -rf build"}),
        (
            "powershell",
            {"command": "Remove-Item -Recurse build", "description": "x"},
            "PowerShell",
            {"command": "Remove-Item -Recurse build", "description": "x"},
        ),
        (
            "write_powershell",
            {"shellId": "0", "input": "Remove-Item build\n", "command": "Get-Date"},
            "PowerShell",
            {"command": "Remove-Item build\n", "shellId": "0"},
        ),
        (
            "str_replace_editor",
            {"command": "create", "path": ".github/workflows/ci.yml", "file_text": "x"},
            "Write",
            {"command": "create", "file_path": ".github/workflows/ci.yml", "file_text": "x"},
        ),
        ("web_search", {"query": "release notes"}, "WebSearch", {"query": "release notes"}),
        (
            "lsp",
            {"operation": "findReferences", "file": "a.py", "line": 1, "character": 2},
            "LSP",
            {"operation": "findReferences", "filePath": "a.py", "line": 1, "character": 2},
        ),
        (
            "lsp",
            {"operation": "rename", "file": "a.py", "newName": "b"},
            "lsp",
            {"operation": "rename", "file": "a.py", "newName": "b"},
        ),
        ("report_intent", {"intent": "x"}, "report_intent", {"intent": "x"}),
    ],
)
def test_copilot_tools_reach_policy_under_claude_code_names(
    name: str, arguments: dict[str, JsonValue], policy_name: str, policy_input: dict[str, JsonValue]
) -> None:
    body = judged({**PAYLOAD, "toolName": name, "toolArgs": arguments})
    assert body["input"] == {"tool_name": policy_name, "tool_input": policy_input, "cwd": "/workspace"}


def test_a_payload_without_cwd_is_still_judged() -> None:
    body = judged({"toolName": "bash", "toolArgs": {"command": "pwd"}})
    assert body["input"] == {"tool_name": "Bash", "tool_input": {"command": "pwd"}}
    assert body["messages"] == [] and "external_ids" not in body


SESSION = "4f3b0c9e-1c7d-4a47-9a0e-3a4e2f9b6c11"
# A callback as current Copilot sends it, naming the session, directory and time
# that the hook record it wrote to the log also carries.
CALLBACK: dict[str, JsonValue] = {**PAYLOAD, "sessionId": SESSION, "timestamp": MILLIS}


def write_log(home: Path, events: list[dict[str, JsonValue]]) -> None:
    path = home / "session-state" / SESSION / "events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(event) + "\n" for event in events))


def gate_hook(call_id: str, name: str, arguments: JsonValue) -> dict[str, JsonValue]:
    """The hook record Copilot writes for one pending call before it runs the gate."""
    return hook_start([{"id": call_id, "name": name, "args": arguments}], invocation=f"hook-{call_id}")


def test_the_gate_sends_the_conversation_so_far(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    write_log(
        tmp_path,
        [
            {"type": "session.start", "data": {"sessionId": SESSION}},
            {"type": "user.message", "data": {"content": "Delete the build directory"}},
            {
                "type": "assistant.message",
                "data": {
                    "content": "",
                    "toolRequests": [{"toolCallId": "c1", "name": "bash", "arguments": {"command": "rm -rf build"}}],
                },
            },
            gate_hook("c1", "bash", {"command": "rm -rf build"}),
        ],
    )
    body = judged({**CALLBACK, "toolArgs": {"command": "rm -rf build"}})
    assert body["messages"] == [
        {"role": "user", "content": "Delete the build directory"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "function": "Bash", "arguments": {"command": "rm -rf build"}}],
        },
    ]
    assert body["external_ids"] == {"other": f"github-copilot-cli:{SESSION}"}
    # The decision is stored on the recorded call: the request is not ephemeral and names it.
    assert body.get("ephemeral") in (None, False)
    assert isinstance(body["input"], dict) and body["input"]["tool_use_id"] == "c1"


def test_the_gate_transcript_is_a_prefix_of_the_recording(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Watcher extends a stored trajectory only when each submission starts with the
    # previous one, so the gate must send exactly what the recording hooks later send.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    events: list[dict[str, JsonValue]] = [
        {"type": "session.start", "data": {"sessionId": SESSION}},
        {"type": "user.message", "data": {"content": "Read the notes\x00"}},
        {
            "type": "assistant.message",
            "data": {"content": "", "toolRequests": [{"toolCallId": "v1", "name": "view", "arguments": {"path": "a"}}]},
        },
        gate_hook("v1", "view", {"path": "a"}),
    ]
    write_log(tmp_path, events)
    body = judged({**CALLBACK, "toolName": "view", "toolArgs": {"path": "a"}})
    completed = [
        *events,
        {"type": "tool.execution_complete", "data": {"toolCallId": "v1", "success": True, "result": {"content": "x"}}},
        {"type": "assistant.message", "data": {"content": "Done"}},
    ]
    recorded = convert_session(completed).messages
    assert body["messages"] == recorded[: len(body["messages"])]
    assert body["input"] == {
        "tool_name": "Read",
        "tool_input": {"file_path": "a"},
        "cwd": "/workspace",
        "tool_use_id": "v1",
    }


def test_parallel_calls_name_the_one_with_matching_arguments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    requests: list[JsonValue] = [
        {"toolCallId": "p1", "name": "bash", "arguments": {"command": "ls"}},
        {"toolCallId": "p2", "name": "bash", "arguments": {"command": "pwd"}},
        {"toolCallId": "p3", "name": "view", "arguments": {"path": "a"}},
    ]
    write_log(
        tmp_path,
        [
            {"type": "session.start", "data": {"sessionId": SESSION}},
            {"type": "user.message", "data": {"content": "Look around"}},
            {"type": "assistant.message", "data": {"content": "", "toolRequests": requests}},
            {
                "type": "tool.execution_complete",
                "data": {"toolCallId": "p3", "success": True, "result": {"content": "x"}},
            },
            gate_hook("p1", "bash", {"command": "ls"}),
            {"type": "hook.end", "data": {"hookInvocationId": "hook-p1"}},
            gate_hook("p2", "bash", {"command": "pwd"}),
        ],
    )
    body = judged(CALLBACK)
    assert isinstance(body["input"], dict) and body["input"]["tool_use_id"] == "p2"


def test_an_answered_call_is_never_claimed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    config = tmp_path / "config" / "config.json"
    config.parent.mkdir()
    write_log(
        tmp_path,
        [
            {"type": "session.start", "data": {"sessionId": SESSION}},
            {"type": "user.message", "data": {"content": "Where am I"}},
            {
                "type": "assistant.message",
                "data": {
                    "content": "",
                    "toolRequests": [{"toolCallId": "done", "name": "bash", "arguments": {"command": "pwd"}}],
                },
            },
            {
                "type": "tool.execution_complete",
                "data": {"toolCallId": "done", "success": True, "result": {"content": "/"}},
            },
            gate_hook("done", "bash", {"command": "pwd"}),
        ],
    )
    body = judged(CALLBACK, config=config)
    assert body["ephemeral"] is True and isinstance(body["input"], dict) and "tool_use_id" not in body["input"]
    assert body["external_ids"] == {"other": f"github-copilot-cli:{SESSION}"}
    assert unrecorded_reasons(config) == ["tool_call_id_not_found"]


def test_a_conversation_over_the_budget_is_judged_without_storing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    config = tmp_path / "config" / "config.json"
    config.parent.mkdir()
    write_log(
        tmp_path,
        [
            {"type": "session.start", "data": {"sessionId": SESSION}},
            {"type": "user.message", "data": {"content": "x" * 3000}},
            {"type": "assistant.message", "data": {"content": "Sure"}},
            {"type": "user.message", "data": {"content": "Where am I"}},
            {
                "type": "assistant.message",
                "data": {
                    "content": "",
                    "toolRequests": [{"toolCallId": "c1", "name": "bash", "arguments": {"command": "pwd"}}],
                },
            },
            gate_hook("c1", "bash", {"command": "pwd"}),
        ],
    )
    monkeypatch.setattr(integration, "MAX_CONTEXT_BYTES", 1500)
    body = judged(CALLBACK, config=config)
    assert body["ephemeral"] is True and isinstance(body["input"], dict) and "tool_use_id" not in body["input"]
    assert isinstance(body["messages"], list) and body["messages"][0] == {"role": "user", "content": "Where am I"}
    assert unrecorded_reasons(config) == ["conversation_too_large"]


def unrecorded_reasons(config: Path) -> list[str]:
    events = [json.loads(line) for line in config.with_name("events.jsonl").read_text().splitlines()]
    return [event["reason"] for event in events if event["kind"] == "unrecorded_review"]


def test_long_context_keeps_its_recent_part_from_a_user_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    turns: list[dict[str, JsonValue]] = [{"type": "session.start", "data": {"sessionId": SESSION}}]
    for index in range(3):
        turn: list[dict[str, JsonValue]] = [
            {"type": "user.message", "data": {"content": f"prompt {index} " + "x" * 400}},
            {
                "type": "assistant.message",
                "data": {"content": "", "toolRequests": [{"toolCallId": f"c{index}", "name": "view", "arguments": {}}]},
            },
            {
                "type": "tool.execution_complete",
                "data": {"toolCallId": f"c{index}", "success": True, "result": {"content": "y" * 400}},
            },
        ]
        turns += turn
    write_log(tmp_path, turns)
    monkeypatch.setattr(integration, "MAX_CONTEXT_BYTES", 1500)
    messages = judged({**PAYLOAD, "sessionId": SESSION})["messages"]
    assert isinstance(messages, list) and isinstance(messages[0], dict)
    assert messages[0]["role"] == "user" and str(messages[0]["content"]).startswith("prompt 2")
    assert len(messages) == 3


def test_a_subagent_call_without_its_parents_log_is_judged_without_naming_a_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A subagent's preToolUse names the subagent, whose calls are in its parent's log.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    config = tmp_path / "config" / "config.json"
    config.parent.mkdir()
    body = judged({**CALLBACK, "sessionId": "3e91782e-35a1-4b0c-9f38-0a4b0e3c5d21"}, config=config)
    assert body["messages"] == [] and "external_ids" not in body and body["ephemeral"] is True
    assert unrecorded_reasons(config) == ["subagent_no_log"]


def test_an_unsupported_log_gives_no_context_instead_of_a_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    config = tmp_path / "config" / "config.json"
    config.parent.mkdir()
    hosted = {"content": "", "serverTools": {"provider": "openai", "toolCalls": [{"id": "hosted"}]}}
    write_log(
        tmp_path,
        [
            {"type": "session.start", "data": {"sessionId": SESSION}},
            {"type": "assistant.message", "data": hosted},
            gate_hook("c1", "bash", {"command": "pwd"}),
        ],
    )
    body = judged(CALLBACK, config=config)
    assert body["messages"] == [] and body["ephemeral"] is True
    assert unrecorded_reasons(config) == ["transcript_unsupported"]


@pytest.mark.parametrize("old", [True, False], ids=["old", "near-window"])
def test_a_broken_line_stops_storing_only_decisions_made_around_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old: bool
) -> None:
    # A broken line, appended by the agent or left by a crash, keeps the gate from
    # naming a call only while it could still hide that call's hook record.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    config = tmp_path / "config" / "config.json"
    config.parent.mkdir()
    stamp = "2026-09-30T11:59:00.000Z" if old else "2026-09-30T11:59:59.500Z"
    call = {"toolCallId": "c1", "name": "bash", "arguments": {"command": "pwd"}}
    events = [
        {"type": "session.start", "data": {"sessionId": SESSION}},
        {"type": "user.message", "timestamp": stamp, "data": {"content": "Show the directory"}},
        {"type": "assistant.message", "timestamp": stamp, "data": {"content": "", "toolRequests": [call]}},
        gate_hook("c1", "bash", {"command": "pwd"}),
    ]
    lines = [json.dumps(event) for event in events]
    lines.insert(1, "not an event")
    path = tmp_path / "session-state" / SESSION / "events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(lines) + "\n")

    body = judged(CALLBACK, config=config)

    assert body["messages"] != []
    if old:
        assert body["ephemeral"] is False and body["input"]["tool_use_id"] == "c1"
        assert unrecorded_reasons(config) == []
    else:
        assert body["ephemeral"] is True and "tool_use_id" not in body["input"]
        assert unrecorded_reasons(config) == ["transcript_unsupported"]


@pytest.mark.parametrize(
    "mode,further,first,outcome,stored_by,source",
    [
        ("enforce", "allow", "allow", "allow", "gate", "threshold"),
        ("enforce", "escalate", "allow", "escalate", "recording", "rule"),
        ("enforce", "deny", "allow", "deny", "recording", "rule"),
        # The first path's own deny is already the strictest judgment.
        ("enforce", "escalate", "deny", "deny", "recording", "threshold"),
        ("observe", "allow", "allow", "deferred", "gate", "threshold"),
        ("observe", "deny", "allow", "deferred", "recording", "rule"),
        ("observe", "escalate", "deny", "deferred", "recording", "threshold"),
    ],
)
def test_a_patch_keeps_its_strictest_judgment_for_the_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    further: str,
    first: str,
    outcome: str,
    stored_by: str,
    source: str,
) -> None:
    # Watcher stores a gate request only for the call as recorded, judged on the
    # first path. When a later path is judged stricter, storing the first path's
    # decision would show the call as allowed although the gate withheld or
    # escalated it, so the gate leaves the strictest judgment for recording to store.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    config = tmp_path / "config" / "config.json"
    config.parent.mkdir()
    patch_call = {"toolCallId": "patch-1", "name": "apply_patch", "arguments": MULTI_FILE_PATCH, "type": "custom"}
    write_log(
        tmp_path,
        [
            {"type": "session.start", "data": {"sessionId": SESSION}},
            {"type": "user.message", "data": {"content": "Finish the task"}},
            {"type": "assistant.message", "data": {"content": "", "toolRequests": [patch_call]}},
            gate_hook("patch-1", "apply_patch", MULTI_FILE_PATCH),
        ],
    )
    received: list[dict[str, JsonValue]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        received.append(body)
        # The first path and the later path are told apart by their decision source.
        is_first = body["input"]["tool_input"]["file_path"] == "status.txt"
        judgment = first if is_first else further
        return httpx.Response(
            200,
            json={
                **ALLOW,
                "decision": judgment if mode == "enforce" else "deferred",
                "judged_decision": judgment,
                "enforcement_mode": mode,
                "decision_source": "threshold" if is_first else "rule",
                "tool_use_id": body["input"].get("tool_use_id"),
            },
        )

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            payload = {**CALLBACK, "toolName": "apply_patch", "toolArgs": MULTI_FILE_PATCH}
            return await apply_policy(client, payload, config=config)

    if outcome in {"allow", "deferred"}:
        assert asyncio.run(run()) == outcome
    else:
        with pytest.raises(Escalation if outcome == "escalate" else integration.PolicyDenial):
            asyncio.run(run())
    paths = [body["input"]["tool_input"]["file_path"] for body in received]
    # Later paths are judged first; a withheld one needs no judgment of the first path.
    later_deny = mode == "enforce" and further == "deny"
    assert paths == (["sub/.watcher-ignore"] if later_deny else ["sub/.watcher-ignore", "status.txt"])
    recorded = [body for body in received if body.get("ephemeral") is not True]
    assert unrecorded_reasons(config) == []
    [saved] = read_review_evidence(config, UUID(SESSION)).receipts
    assert (saved.tool_use_id, saved.stored_by, saved.decision_source) == ("patch-1", stored_by, source)
    strictest = first if stored_by == "gate" or source == "threshold" else further
    assert saved.judged_decision == strictest
    assert saved.decision == (strictest if mode == "enforce" else "deferred")
    # The receipt names the call as recorded, the first path's Edit, whichever path decided.
    name, arguments = submitted_call(
        PendingTool.model_validate({**CALLBACK, "toolName": "apply_patch", "toolArgs": MULTI_FILE_PATCH})
    )
    assert name == "Edit" and saved.call_hash == call_hash(name, arguments)
    if stored_by == "gate":
        assert [body["input"]["tool_use_id"] for body in recorded] == ["patch-1"]
        assert saved.decided_at is None
    else:
        assert recorded == [] and all("tool_use_id" not in body["input"] for body in received)
        assert saved.grade_ids == [] and saved.grade_ids_complete is True and saved.decided_at is not None
    assert escalated_calls(config, UUID(SESSION)) == ({"patch-1"} if outcome == "escalate" else set())


def test_an_escalation_is_distinguished_from_a_denial() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={**ALLOW, "decision": "escalate", "judged_decision": "escalate"})

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, PAYLOAD)

    with pytest.raises(Escalation):
        asyncio.run(run())


def test_reading_the_log_counts_against_the_gate_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WATCHER_TIMEOUT_SECONDS", "0.2")

    async def slow_context(pending, budget, *, deadline):
        time.sleep(0.3)
        return integration.GateContext(None, unrecorded="subagent_no_log")

    monkeypatch.setattr(integration, "gate_context", slow_context)
    with pytest.raises(TimeoutError):
        judged(PAYLOAD)


def test_a_large_pending_call_leaves_less_room_for_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    budgets: list[int] = []

    async def context(pending, budget, *, deadline):
        budgets.append(budget)
        return integration.GateContext(None, unrecorded="subagent_no_log")

    monkeypatch.setattr(integration, "gate_context", context)
    judged({**PAYLOAD, "toolName": "create", "toolArgs": {"path": "big.txt", "file_text": "x" * 100_000}})
    judged(PAYLOAD)
    assert budgets[1] - budgets[0] > 100_000
    assert budgets[1] < integration.MAX_CONTEXT_BYTES


def test_an_older_install_with_a_shorter_hook_timeout_gets_a_shorter_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json=ALLOW)

    async def run(hook_timeout: int) -> None:
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(slow))
        ) as client:
            await apply_policy(client, PAYLOAD, hook_timeout=hook_timeout)

    started = time.monotonic()
    with pytest.raises(TimeoutError):
        asyncio.run(run(61))
    assert time.monotonic() - started < 3
    with pytest.raises(ValueError, match="no time"):
        asyncio.run(run(60))


@pytest.mark.parametrize("decision", ["escalate", "deny", "allow"])
@pytest.mark.parametrize("too_large", [False, True])
def test_the_gate_remembers_only_the_calls_it_escalates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, decision: str, too_large: bool
) -> None:
    # Recording uploads a person's answer only for a call listed here, so a call
    # judged without storing, because the conversation is too large, still counts.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    config = tmp_path / "config" / "config.json"
    config.parent.mkdir()
    write_log(
        tmp_path,
        [
            {"type": "session.start", "data": {"sessionId": SESSION}},
            {"type": "user.message", "data": {"content": "x" * (3000 if too_large else 10)}},
            {
                "type": "assistant.message",
                "data": {
                    "content": "",
                    "toolRequests": [{"toolCallId": "c1", "name": "bash", "arguments": {"command": "pwd"}}],
                },
            },
            gate_hook("c1", "bash", {"command": "pwd"}),
        ],
    )
    if too_large:
        monkeypatch.setattr(integration, "MAX_CONTEXT_BYTES", 1500)

    def respond(request: httpx.Request) -> httpx.Response:
        tool_use_id = json.loads(request.content)["input"].get("tool_use_id")
        return httpx.Response(
            200, json={**ALLOW, "decision": decision, "judged_decision": decision, "tool_use_id": tool_use_id}
        )

    async def run():
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await apply_policy(client, CALLBACK, config=config)

    if decision == "allow":
        asyncio.run(run())
    else:
        with pytest.raises(PermissionError):
            asyncio.run(run())
    expected = {"c1"} if decision == "escalate" else set()
    assert escalated_calls(config, UUID(SESSION)) == expected
