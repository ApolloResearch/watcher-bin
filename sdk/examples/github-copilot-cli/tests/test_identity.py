"""Link a preToolUse callback to a native call only when exactly one call matches it."""

import asyncio
import io
import json
import os
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import BinaryIO, TextIO, cast
from uuid import UUID

import httpx
import pytest
from pydantic import JsonValue
from watcher_github_copilot_cli import identity
from watcher_github_copilot_cli.identity import PendingTool, Resolution, resolve_pending, submitted_call
from watcher_github_copilot_cli.recording import record_session
from watcher_github_copilot_cli.transcript import convert_session

from watcher_sdk import AsyncWatcherClient, WatcherError

SESSION = UUID("4f3b0c9e-1c7d-4a47-9a0e-3a4e2f9b6c11")
STAMP = "2026-09-30T12:00:00.000Z"
MILLIS = 1790769600000
ARGS: dict[str, JsonValue] = {"command": "touch PRIVATE_MARKER"}


def hook_start(
    tools: list[JsonValue], *, agent: str | None = None, invocation: str = "invocation", stamp: str = STAMP
) -> dict[str, JsonValue]:
    """Copilot's record of one preToolUse hook invocation, as it writes it before running the hook."""
    return {
        "type": "hook.start",
        "timestamp": stamp,
        "agentId": agent,
        "data": {
            "hookType": "preToolUse",
            "hookInvocationId": invocation,
            "input": {"sessionId": agent or str(SESSION), "cwd": "/workspace", "toolCalls": tools},
        },
    }


def native_events(
    *, agent: str | None = None, duplicate: bool = False, name: str = "bash", arguments: JsonValue = None
) -> list[dict[str, JsonValue]]:
    """A session whose model asked for one call (two identical ones with ``duplicate``) now awaiting the gate."""
    arguments = ARGS if arguments is None else arguments
    calls: list[JsonValue] = [{"toolCallId": "native-call", "name": name, "arguments": arguments}]
    tools: list[JsonValue] = [{"id": "native-call", "name": name, "args": arguments}]
    if duplicate:
        calls.append({"toolCallId": "identical-call", "name": name, "arguments": arguments})
        tools.append({"id": "identical-call", "name": name, "args": arguments})
    return [
        {"type": "session.start", "data": {"sessionId": str(SESSION)}},
        {"type": "user.message", "agentId": agent, "data": {"content": "Run the command"}},
        {"type": "assistant.message", "agentId": agent, "data": {"content": "", "toolRequests": calls}},
        hook_start(tools, agent=agent),
    ]


def pending(agent: str | None = None, *, name: str = "bash", arguments: JsonValue = None) -> PendingTool:
    return PendingTool.model_validate(
        {
            "sessionId": agent or str(SESSION),
            "timestamp": MILLIS,
            "cwd": "/workspace",
            "toolName": name,
            "toolArgs": ARGS if arguments is None else arguments,
        }
    )


def write_log(root: Path, events: list[dict[str, JsonValue]], *, session: UUID = SESSION) -> Path:
    path = root / "session-state" / str(session) / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(event) + "\n" for event in events))
    return path


def resolve(callback: PendingTool, seconds: float = 1) -> Resolution:
    return asyncio.run(resolve_pending(callback, deadline=time.monotonic() + seconds))


@pytest.fixture(autouse=True)
def short_identity_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    # A callback whose call never appears waits for the log to catch up; keep that short here.
    monkeypatch.setattr(identity, "IDENTITY_WAIT_SECONDS", 0.2)


@pytest.mark.parametrize("agent", [None, "worker-1"], ids=["root", "subagent"])
def test_a_linked_call_has_the_prefix_and_identity_recording_uses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, agent: str | None
) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    events = native_events(agent=agent)
    write_log(tmp_path, events)

    result = resolve(pending(agent))

    assert result.call is not None and result.reason is None
    assert result.call.tool_use_id == "native-call" and result.call.session == SESSION
    assert result.call.agent_id == agent
    completed = convert_session(
        [*events, {"type": "assistant.message", "agentId": agent, "data": {"content": "Done"}}], final=True
    )
    messages = completed.subagents[0].messages if agent else completed.messages
    assert messages[: len(result.call.messages)] == result.call.messages
    # The recorded call carries the Claude Code name the gate submits, never Copilot's own.
    assert result.call.messages[-1]["tool_calls"] == [{"id": "native-call", "function": "Bash", "arguments": ARGS}]
    assert result.call.identity == (
        f"github-copilot-cli:{SESSION}:agent:worker-1" if agent else f"github-copilot-cli:{SESSION}"
    )


def test_the_identity_names_the_session_recording_stores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Recording names each conversation by the same external ID, so a stored judgment
    # and the later recording land in one Watcher session.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    events = native_events(agent="worker-1")
    events.insert(1, {"type": "user.message", "data": {"content": "Delegate"}})
    events.insert(2, {"type": "assistant.message", "data": {"content": "Delegating"}})
    write_log(tmp_path, events)
    result = resolve(pending("worker-1"))
    assert result.call is not None
    identities: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        identities.append(json.loads(request.content)["external_ids"]["other"])
        return httpx.Response(400, json={"error": {"message": "stop after naming the session"}})

    async def run() -> None:
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond))
        ) as client:
            await record_session(client, SESSION, convert_session(events, final=True), timeout_seconds=1)

    with pytest.raises(WatcherError):
        asyncio.run(run())
    assert identities == [f"github-copilot-cli:{SESSION}"]
    assert result.call.identity == f"{identities[0]}:agent:worker-1"


@pytest.mark.parametrize(
    "name,arguments,recorded_name,recorded_arguments",
    [
        ("view", {"path": "notes.txt"}, "Read", {"file_path": "notes.txt"}),
        ("write_bash", {"shellId": "0", "input": "ls\n"}, "Bash", {"command": "ls\n", "shellId": "0"}),
        (
            "apply_patch",
            "*** Begin Patch\n*** Add File: new.txt\n+hi\n*** End Patch\n",
            "Write",
            {"file_path": "new.txt", "input": "*** Begin Patch\n*** Add File: new.txt\n+hi\n*** End Patch\n"},
        ),
        ("local_shell", {"command": "ls"}, "Bash", {"command": "ls"}),
        ("powershell", {"command": "Get-ChildItem"}, "PowerShell", {"command": "Get-ChildItem"}),
        (
            "write_powershell",
            {"shellId": "0", "input": "Get-ChildItem\n"},
            "PowerShell",
            {"command": "Get-ChildItem\n", "shellId": "0"},
        ),
        (
            "str_replace_editor",
            {"command": "str_replace", "path": "notes.txt", "old_str": "a", "new_str": "b"},
            "Edit",
            {"command": "str_replace", "file_path": "notes.txt", "old_str": "a", "new_str": "b"},
        ),
        (
            "str_replace_editor",
            {"command": "undo_edit", "path": "a"},
            "str_replace_editor",
            {"command": "undo_edit", "path": "a"},
        ),
        ("web_search", {"query": "release notes"}, "WebSearch", {"query": "release notes"}),
        (
            "lsp",
            {"operation": "hover", "file": "a.py", "line": 1, "character": 2},
            "LSP",
            {"operation": "hover", "filePath": "a.py", "line": 1, "character": 2},
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
def test_mapped_and_unmapped_tools_link_under_the_names_the_gate_submits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    arguments: JsonValue,
    recorded_name: str,
    recorded_arguments: dict[str, JsonValue],
) -> None:
    # Watcher refuses a stored gate request whose call differs from the same call in
    # its transcript, so the linked conversation must hold exactly what the gate sends.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    events = native_events(name=name, arguments=arguments)
    if isinstance(arguments, str):
        assistant = events[2]["data"]
        assert isinstance(assistant, dict) and isinstance(assistant["toolRequests"], list)
        request = assistant["toolRequests"][0]
        assert isinstance(request, dict)
        request["type"] = "custom"
    write_log(tmp_path, events)
    callback = pending(name=name, arguments=arguments)

    result = resolve(callback)

    assert submitted_call(callback) == (recorded_name, recorded_arguments)
    assert result.call is not None, result.reason
    [recorded] = [
        call
        for message in result.call.messages
        for call in cast(list[dict[str, JsonValue]], message.get("tool_calls", []))
    ]
    assert (recorded["function"], recorded["arguments"]) == (recorded_name, recorded_arguments)


@pytest.mark.parametrize(
    "damage,reason",
    [
        ("duplicate", "tool_call_ambiguous"),
        ("closed", "tool_call_ambiguous"),
        ("no-assistant", "tool_call_id_not_found"),
        ("wrong-arguments", "tool_call_id_not_found"),
        ("wrong-session", "transcript_unsupported"),
        ("no-session-start", "transcript_unsupported"),
        ("wrong-cwd", "tool_call_id_not_found"),
        ("wrong-timestamp", "tool_call_id_not_found"),
        ("answered", "tool_call_id_not_found"),
        ("no-timestamp", "tool_call_id_not_found"),
        ("no-cwd", "tool_call_id_not_found"),
        ("no-session", "subagent_no_log"),
    ],
)
def test_unlinkable_calls_never_receive_an_invented_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str, reason: str
) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    events = native_events(duplicate=damage == "duplicate")
    callback = pending()
    if damage == "closed":
        events.append({"type": "hook.end", "data": {"hookInvocationId": "invocation"}})
    if damage == "no-assistant":
        del events[2]
    if damage == "wrong-session":
        events[0] = {"type": "session.start", "data": {"sessionId": str(UUID(int=1))}}
    if damage == "no-session-start":
        del events[0]
    if damage == "wrong-arguments":
        callback.toolArgs = {"command": "different"}
    if damage == "wrong-cwd":
        callback.cwd = "/elsewhere"
    if damage == "wrong-timestamp":
        callback.timestamp = MILLIS + 1_001
    if damage == "answered":
        output: dict[str, JsonValue] = {"content": "done"}
        events.insert(
            3,
            {
                "type": "tool.execution_complete",
                "data": {"toolCallId": "native-call", "success": True, "result": output},
            },
        )
    if damage == "no-timestamp":
        callback.timestamp = None
    if damage == "no-cwd":
        callback.cwd = None
    if damage == "no-session":
        callback.sessionId = None
    write_log(tmp_path, events)

    result = resolve(callback)

    assert result.call is None and result.reason == reason


@pytest.mark.parametrize("offset", [-1_001, -1, 1, 1_001])
def test_the_callback_clock_must_be_within_a_second_of_the_hook_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offset: int
) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    write_log(tmp_path, native_events())
    callback = pending()
    callback.timestamp = MILLIS + offset
    assert (resolve(callback).call is not None) is (abs(offset) <= 1_000)


def test_parallel_distinct_calls_and_resumed_history_keep_native_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    events = native_events()
    events.insert(1, {"type": "session.resume", "data": {"resumeTime": STAMP}})
    assistant, hook = events[3]["data"], events[4]["data"]
    assert isinstance(assistant, dict) and isinstance(hook, dict) and isinstance(hook["input"], dict)
    calls, tools = assistant["toolRequests"], hook["input"]["toolCalls"]
    assert isinstance(calls, list) and isinstance(tools, list)
    calls.append({"toolCallId": "other-call", "name": "bash", "arguments": {"command": "pwd"}})
    tools.append({"id": "other-call", "name": "bash", "args": {"command": "pwd"}})
    write_log(tmp_path, events)

    result = resolve(pending())

    assert result.call is not None and result.call.tool_use_id == "native-call"


def test_identical_parallel_calls_in_separate_hooks_stay_unlinked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Order never decides identity: neither the newest nor the first unanswered call is chosen.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    events = native_events(duplicate=True)
    events[-1] = hook_start([{"id": "native-call", "name": "bash", "args": ARGS}], invocation="first")
    events.append(hook_start([{"id": "identical-call", "name": "bash", "args": ARGS}], invocation="second"))
    write_log(tmp_path, events)

    result = resolve(pending())

    assert result.call is None and result.reason == "tool_call_ambiguous"


@pytest.mark.parametrize(
    "ended_at,linked",
    [
        # The gate's own invocation cannot have ended while it runs, so an ended
        # matching record inside the clock window may be the real one, closed by an
        # appended hook.end to point the decision at another call.
        (STAMP, False),
        # An identical call whose hook ended before the window was an earlier call.
        ("2026-09-30T11:59:58.000Z", True),
    ],
    ids=["ended-inside-the-window", "ended-before-the-window"],
)
def test_an_identical_call_whose_hook_ended_inside_the_window_keeps_the_call_unlinked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ended_at: str, linked: bool
) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    events = native_events(duplicate=True)
    events[-1] = hook_start(
        [{"id": "identical-call", "name": "bash", "args": ARGS}], invocation="first", stamp=ended_at
    )
    events.append({"type": "hook.end", "data": {"hookInvocationId": "first"}})
    events.append(hook_start([{"id": "native-call", "name": "bash", "args": ARGS}], invocation="second"))
    write_log(tmp_path, events)

    result = resolve(pending())

    if linked:
        assert result.call is not None and result.call.tool_use_id == "native-call"
    else:
        assert result.call is None and result.reason == "tool_call_ambiguous"


def test_overlapping_identical_hooks_are_ambiguous_even_when_one_lacks_its_assistant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    events = native_events()
    unmatched = hook_start(
        [{"id": "no-assistant", "name": "bash", "args": ARGS}],
        invocation="overlapping",
        stamp="2026-09-30T12:00:00.001Z",
    )
    events.insert(2, unmatched)
    write_log(tmp_path, events)

    result = resolve(pending())

    assert result.call is None and result.reason == "tool_call_ambiguous"


def test_a_delayed_hook_record_is_found_while_the_callback_waits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    monkeypatch.setattr(identity, "IDENTITY_WAIT_SECONDS", 2)
    events = native_events()
    path = write_log(tmp_path, events[:-1])

    async def run() -> Resolution:
        task = asyncio.create_task(resolve_pending(pending(), deadline=time.monotonic() + 3))
        await asyncio.sleep(0.2)
        with path.open("a") as output:
            output.write(json.dumps(events[-1]) + "\n")
        return await task

    result = asyncio.run(run())

    assert result.call is not None and result.call.tool_use_id == "native-call"


def test_a_partial_tail_can_finish_while_the_callback_waits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    monkeypatch.setattr(identity, "IDENTITY_WAIT_SECONDS", 2)
    events = native_events()
    path = write_log(tmp_path, events[:-1])
    line = json.dumps(events[-1])
    with path.open("a") as output:
        output.write(line[:10])

    async def run() -> Resolution:
        task = asyncio.create_task(resolve_pending(pending(), deadline=time.monotonic() + 3))
        await asyncio.sleep(0.2)
        with path.open("a") as output:
            output.write(line[10:] + "\n")
        return await task

    result = asyncio.run(run())

    assert result.call is not None and result.call.tool_use_id == "native-call"


def second_open_hook(actor: str | None) -> dict[str, JsonValue]:
    return hook_start([{"id": "another-call", "name": "bash", "args": ARGS}], agent=actor, invocation="another")


@pytest.mark.parametrize("actor", [None, "worker-1"], ids=["root", "subagent"])
@pytest.mark.parametrize("tail,reason", [("intact", "tool_call_ambiguous"), ("partial", "transcript_unsupported")])
def test_a_partial_final_hook_cannot_hide_a_second_identical_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, actor: str | None, tail: str, reason: str
) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    path = write_log(tmp_path, native_events(agent=actor))
    extra = json.dumps(second_open_hook(actor))
    with path.open("a") as output:
        output.write(extra + "\n" if tail == "intact" else extra[: len(extra) // 2])

    result = resolve(pending(actor))

    assert result.call is None and result.reason == reason


class ObservedPartialRead(io.BufferedReader):
    """A log reader that signals once it has read an unfinished final line."""

    def __init__(self, path: Path, consumed: threading.Event) -> None:
        super().__init__(io.FileIO(path, "r"))
        self.consumed = consumed

    def readline(self, size: int | None = -1, /) -> bytes:
        line = super().readline(size)
        if line and not line.endswith(b"\n"):
            self.consumed.set()
        return line


@pytest.mark.parametrize("actor", [None, "worker-1"], ids=["root", "subagent"])
def test_a_partial_final_hook_is_read_again_once_it_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, actor: str | None
) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    monkeypatch.setattr(identity, "IDENTITY_WAIT_SECONDS", 2)
    path = write_log(tmp_path, native_events(agent=actor))
    extra = json.dumps(second_open_hook(actor))
    middle = len(extra) // 2
    with path.open("a") as output:
        output.write(extra[:middle])
    consumed = threading.Event()
    original_open = Path.open

    def observed_open(
        selected: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> BinaryIO | TextIO:
        if selected == path and mode == "rb":
            return ObservedPartialRead(selected, consumed)
        return cast(BinaryIO | TextIO, original_open(selected, mode, buffering, encoding, errors, newline))

    monkeypatch.setattr(Path, "open", observed_open)

    async def run() -> Resolution:
        task = asyncio.create_task(resolve_pending(pending(actor), deadline=time.monotonic() + 3))
        assert await asyncio.wait_for(asyncio.to_thread(consumed.wait, 1), timeout=1.5)
        with original_open(path, "a") as output:
            output.write(extra[middle:] + "\n")
        return await task

    result = asyncio.run(run())

    assert result.call is None and result.reason == "tool_call_ambiguous"


def test_an_unreadable_line_in_the_session_log_keeps_the_call_unlinked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Recording skips an unreadable line, but the gate cannot know it was not a
    # second matching hook record, so it stores nothing rather than guess.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    path = write_log(tmp_path, native_events())
    lines = path.read_text().splitlines()
    lines.insert(2, '{"unfinished":')
    path.write_text("\n".join(lines) + "\n")

    result = resolve(pending())

    assert result.call is None and result.reason == "transcript_unsupported"


@pytest.mark.parametrize("damage", ["tool-without-id", "no-timestamp", "invalid-timestamp", "naive-timestamp"])
def test_a_malformed_hook_record_keeps_the_call_unlinked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    events = native_events()
    broken = deepcopy(second_open_hook(None))
    data = broken["data"]
    assert isinstance(data, dict) and isinstance(data["input"], dict)
    if damage == "tool-without-id":
        data["input"]["toolCalls"] = [{"name": "bash", "args": ARGS}]
    if damage == "no-timestamp":
        del broken["timestamp"]
    if damage == "invalid-timestamp":
        broken["timestamp"] = "yesterday"
    if damage == "naive-timestamp":
        broken["timestamp"] = "2026-09-30T12:00:00"
    events.append(broken)
    write_log(tmp_path, events)

    result = resolve(pending())

    assert result.call is None and result.reason == "transcript_unsupported"


def damaged_line(damage: str) -> str:
    """One damaged log line: unreadable, or a record whose damage could hide or reopen a candidate."""
    if damage == "unreadable":
        return '{"unfinished":'
    if damage == "hook-end":
        return json.dumps({"type": "hook.end", "data": {}})
    broken = deepcopy(second_open_hook(None))
    data = broken["data"]
    assert isinstance(data, dict) and isinstance(data["input"], dict)
    if damage == "hook-without-id":
        data["input"]["toolCalls"] = [{"name": "bash", "args": ARGS}]
    if damage == "naive-hook":
        broken["timestamp"] = "2026-09-30T11:59:00"
    return json.dumps(broken)


@pytest.mark.parametrize("damage", ["unreadable", "hook-end", "hook-without-id", "naive-hook"])
@pytest.mark.parametrize(
    "followed_by,linked",
    [
        # Copilot appends in time order, so a line followed by an event from well
        # before the callback was written before any candidate could be.
        ("2026-09-30T11:59:50.000Z", True),
        # An event within the candidate window and its slack proves nothing.
        ("2026-09-30T11:59:59.000Z", False),
        ("2026-09-30T11:59:58.000Z", False),
        (None, False),
    ],
    ids=["old", "near-window", "at-slack-edge", "untimed"],
)
def test_only_damage_written_around_the_callback_keeps_the_call_unlinked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str, followed_by: str | None, linked: bool
) -> None:
    # One broken line, appended by the agent or left by a crash, must not stop
    # decisions being stored for the rest of the session, yet a broken line written
    # when the call's hook record was could be a second candidate.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    start, user, assistant, hook = native_events()
    user = {**user, "timestamp": followed_by} if followed_by is not None else user
    path = write_log(tmp_path, [start, user, assistant, hook])
    lines = path.read_text().splitlines()
    lines.insert(1, damaged_line(damage))
    path.write_text("\n".join(lines) + "\n")

    result = resolve(pending())

    # This damaged record keeps its timestamp from the candidate window, so an older
    # event after it is a step back in time, and nothing after that step settles.
    linked = linked and damage != "hook-without-id"
    if linked:
        assert result.call is not None and result.call.tool_use_id == "native-call", result.reason
        if damage == "unreadable":
            # Recording marks the skipped line where it was, so the stored prefix still matches.
            assert result.call.messages[0]["metadata"] == {"github_copilot_cli": {"skipped_events": True}}
    else:
        assert result.call is None and result.reason == "transcript_unsupported"


def test_an_old_dated_event_after_damage_does_not_settle_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Copilot appends in time order, so an event dated before the one ahead of it
    # was appended out of order and proves nothing about the damage it follows.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    start, user, assistant, hook = native_events()
    user = {**user, "timestamp": "2026-09-30T11:59:59.500Z"}
    old: dict[str, JsonValue] = {"type": "session.info", "timestamp": "2026-09-30T11:59:00.000Z", "data": {}}
    path = write_log(tmp_path, [start, user, old, assistant, hook])
    lines = path.read_text().splitlines()
    lines.insert(2, damaged_line("unreadable"))
    path.write_text("\n".join(lines) + "\n")

    result = resolve(pending())

    assert result.call is None and result.reason == "transcript_unsupported"


def test_old_damage_in_a_recent_neighbor_log_does_not_block_a_subagent_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    clean = write_log(tmp_path, native_events(agent="worker-1"))
    os.utime(clean, (MILLIS / 1000, MILLIS / 1000))
    damaged = tmp_path / "session-state" / str(UUID(int=99)) / "events.jsonl"
    damaged.parent.mkdir()
    old = {"type": "user.message", "timestamp": "2026-09-30T11:59:00.000Z", "data": {"content": "x"}}
    damaged.write_text('{"unfinished":\n' + json.dumps(old) + "\n")
    os.utime(damaged, (MILLIS / 1000 + 1, MILLIS / 1000 + 1))

    result = resolve(pending("worker-1"))

    assert result.call is not None and result.call.agent_id == "worker-1", result.reason


def test_an_oversized_event_keeps_the_call_unlinked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    monkeypatch.setattr(identity, "MAX_HOOK_EVENT_BYTES", 1024)
    events = native_events()
    events.insert(1, {"type": "model.test", "data": {"content": "x" * 2048}})
    write_log(tmp_path, events)

    result = resolve(pending())

    assert result.call is None and result.reason == "transcript_unsupported"


def test_an_unsupported_conversation_keeps_the_call_unlinked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    events = native_events()
    hosted = {"content": "", "serverTools": {"provider": "openai", "toolCalls": [{"id": "hosted"}]}}
    events.insert(1, {"type": "assistant.message", "data": hosted})
    write_log(tmp_path, events)

    result = resolve(pending())

    assert result.call is None and result.reason == "transcript_unsupported"


def write_neighbor(
    root: Path, events: list[dict[str, JsonValue]], *, session: UUID, directory: str | None = None
) -> Path:
    path = root / "session-state" / (directory or str(session)) / "events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(event) + "\n" for event in events))
    os.utime(path, (MILLIS / 1000 + 1, MILLIS / 1000 + 1))
    return path


def neighbor_events(agent: str, session: UUID) -> list[dict[str, JsonValue]]:
    events = native_events(agent=agent)
    events[0] = {"type": "session.start", "data": {"sessionId": str(session)}}
    return events


@pytest.mark.parametrize(
    "neighbor", ["valid-unrelated", "missing-start", "wrong-start", "invalid-directory", "malformed-hook"]
)
def test_a_subagent_call_is_found_in_its_parent_log_beside_unrelated_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, neighbor: str
) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    selected = write_log(tmp_path, native_events(agent="worker-1"))
    os.utime(selected, (MILLIS / 1000, MILLIS / 1000))
    other = UUID(int=99)
    events = neighbor_events("unrelated-worker", UUID(int=100) if neighbor == "wrong-start" else other)
    if neighbor == "missing-start":
        del events[0]
    if neighbor == "malformed-hook":
        data = events[-1]["data"]
        assert isinstance(data, dict) and isinstance(data["input"], dict)
        data["input"]["toolCalls"] = [{"name": "bash", "args": {"command": "unrelated"}}]
    write_neighbor(
        tmp_path, events, session=other, directory="not-a-session" if neighbor == "invalid-directory" else None
    )

    result = resolve(pending("worker-1"))

    assert result.call is not None, result.reason
    assert result.call.session == SESSION and result.call.agent_id == "worker-1"
    assert result.call.tool_use_id == "native-call"


def test_a_subagent_in_two_parent_logs_stays_unlinked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    first = write_log(tmp_path, native_events(agent="worker-1"))
    os.utime(first, (MILLIS / 1000, MILLIS / 1000))
    write_neighbor(tmp_path, neighbor_events("worker-1", UUID(int=99)), session=UUID(int=99))

    result = resolve(pending("worker-1"))

    assert result.call is None and result.reason == "tool_call_ambiguous"


@pytest.mark.parametrize(
    "contents",
    [
        '{"unfinished":\n',
        '{"type":"user.message","agentId":"unrelated-worker","data":{"content":"x"}}\n{"unfinished":\n',
        '{"type":"hook.start","data":{"input":{"sessionId":""}}}\n{"unfinished":\n',
    ],
)
def test_a_damaged_recent_log_keeps_a_subagent_call_unlinked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contents: str
) -> None:
    # A damaged line in any recently written log could be this subagent's hook record.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    clean = write_log(tmp_path, native_events(agent="worker-1"))
    os.utime(clean, (MILLIS / 1000, MILLIS / 1000))
    damaged = tmp_path / "session-state" / str(UUID(int=99)) / "events.jsonl"
    damaged.parent.mkdir()
    damaged.write_text(contents)
    os.utime(damaged, (MILLIS / 1000 + 1, MILLIS / 1000 + 1))

    result = resolve(pending("worker-1"))

    assert result.call is None and result.reason == "transcript_unsupported"


def test_an_old_damaged_log_does_not_block_a_subagent_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Only logs written within seconds of the callback can hold its hook record.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    clean = write_log(tmp_path, native_events(agent="worker-1"))
    os.utime(clean, (MILLIS / 1000, MILLIS / 1000))
    damaged = tmp_path / "session-state" / str(UUID(int=99)) / "events.jsonl"
    damaged.parent.mkdir()
    damaged.write_text('{"unfinished":\n')
    os.utime(damaged, (MILLIS / 1000 - 60, MILLIS / 1000 - 60))

    result = resolve(pending("worker-1"))

    assert result.call is not None and result.call.agent_id == "worker-1"


def test_a_subagent_no_recent_log_names_has_no_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    unrelated = write_log(tmp_path, native_events(agent="unrelated-worker"))
    os.utime(unrelated, (MILLIS / 1000, MILLIS / 1000))

    result = resolve(pending("worker-1"))

    assert result.call is None and result.reason == "subagent_no_log"


def test_a_subagent_named_like_a_session_is_still_found_in_its_parent_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Copilot's subagent IDs can be UUIDs; a UUID with no log of its own is searched for.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    agent = "3e91782e-35a1-4b0c-9f38-0a4b0e3c5d21"
    path = write_log(tmp_path, native_events(agent=agent))
    os.utime(path, (MILLIS / 1000, MILLIS / 1000))

    result = resolve(pending(agent))

    assert result.call is not None and result.call.session == SESSION and result.call.agent_id == agent


def write_large_log(root: Path) -> None:
    """A session log too long to read within the gate's deadline or the identity wait."""
    path = root / "session-state" / str(SESSION) / "events.jsonl"
    path.parent.mkdir(parents=True)
    with path.open("wb") as output:
        output.write(json.dumps({"type": "session.start", "data": {"sessionId": str(SESSION)}}).encode() + b"\n")
        output.write(b'{"type":"model.test","data":{"probe":"synthetic"}}\n' * 2_000_000)


@pytest.mark.timeout(10)
def test_reading_a_large_log_stops_at_the_gate_deadline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    write_large_log(tmp_path)
    started = time.monotonic()

    with pytest.raises(TimeoutError):
        resolve(pending(), 0.05)

    assert time.monotonic() - started < 2


@pytest.mark.timeout(10)
def test_a_log_not_read_within_the_identity_wait_leaves_the_call_unlinked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The identity wait ends before the gate's deadline, so the gate still answers,
    # judging the call without storing it.
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    write_large_log(tmp_path)
    started = time.monotonic()

    result = resolve(pending(), 5)

    assert result.call is None and result.reason == "transcript_unsupported"
    assert time.monotonic() - started < 2
