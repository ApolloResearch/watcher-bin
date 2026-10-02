"""Record compaction, truncation, aborts, subagents and binary content in stable, extending snapshots.

Event shapes mirror Copilot CLI 1.0.89 logs captured from real sessions.
"""

import asyncio
import base64
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import JsonValue
from watcher_github_copilot_cli import transcript as transcript_module
from watcher_github_copilot_cli.integration import observe_callback
from watcher_github_copilot_cli.transcript import (
    COMPACTION_NOTICE,
    MAX_TOOL_TEXT,
    SKIPPED_EVENT_NOTICE,
    TranscriptError,
    convert_session,
    is_subagent_stop,
    read_ended_session,
    read_transcript,
    wait_for_completed_session,
)

from watcher_sdk import AsyncWatcherClient

SESSION_ID = "4f3b0c9e-1c7d-4a47-9a0e-3a4e2f9b6c11"
AGENT_ID = "9f4f6f59-1ccc-4525-9350-ecda0ca083fd"
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nsynthetic").decode()

FIRST_TURN: list[dict[str, JsonValue]] = [
    {"type": "session.start", "data": {"sessionId": SESSION_ID}},
    {"type": "user.message", "data": {"content": "Read big.txt"}},
    {"type": "system.message", "data": {"role": "system", "content": "Instructions"}},
    {"type": "assistant.turn_start", "data": {"turnId": "0"}},
    {
        "type": "assistant.message",
        "data": {
            "content": "",
            "toolRequests": [{"toolCallId": "call_1", "name": "view", "arguments": {"path": "big.txt"}}],
        },
    },
    {
        "type": "tool.execution_complete",
        "data": {"toolCallId": "call_1", "success": True, "result": {"content": "x" * 50}},
    },
    {"type": "assistant.message", "data": {"content": "It is long."}},
    {"type": "assistant.turn_end", "data": {"turnId": "0"}},
]
COMPACTION: list[dict[str, JsonValue]] = [
    {"type": "session.compaction_start", "data": {"trigger": "manual", "currentTokens": 16474}},
    {"type": "model.turn_started", "data": {"kind": "compaction", "turn": 0}},
    {"type": "model.messages_snapshot", "data": {"kind": "messages_snapshot", "messages": [{"role": "user"}]}},
    {"type": "session.compaction_complete", "data": {"success": False, "error": "Compaction failed"}},
    {
        "type": "session.compaction_complete",
        "data": {"success": True, "summaryContent": "The user asked about big.txt.", "checkpointNumber": 1},
    },
]
EXPECTED_FIRST: list[dict[str, JsonValue]] = [
    {"role": "system", "content": "Instructions"},
    {"role": "user", "content": "Read big.txt"},
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "call_1", "function": "Read", "arguments": {"file_path": "big.txt"}}],
    },
    {"role": "tool", "tool_call_id": "call_1", "function": "Read", "content": "x" * 50},
    {"role": "assistant", "content": "It is long."},
]
EXPECTED_COMPACTION: list[dict[str, JsonValue]] = [
    {"role": "user", "content": "The user asked about big.txt."},
    {
        "role": "system",
        "content": COMPACTION_NOTICE,
        "metadata": {"compaction_boundary": {"harness": "github-copilot-cli", "window": 1}},
    },
]


def convert(events: list[dict[str, JsonValue]]) -> list[dict[str, JsonValue]]:
    return convert_session(events).messages


SKIPPED: dict[str, JsonValue] = {
    "role": "system",
    "content": SKIPPED_EVENT_NOTICE,
    "metadata": {"github_copilot_cli": {"skipped_events": True}},
}


@pytest.fixture
def transcript(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "session-state" / SESSION_ID / "events.jsonl"
    path.parent.mkdir(parents=True)
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    return path


def write_events(path: Path, events: list[dict[str, JsonValue]]) -> None:
    path.write_text("".join(json.dumps(event) + "\n" for event in events))


def test_compaction_extends_the_earlier_snapshot_with_summary_and_watcher_notice() -> None:
    later: list[dict[str, JsonValue]] = [
        {"type": "user.message", "data": {"content": "And now?"}},
        {"type": "assistant.message", "data": {"content": "Still long."}},
    ]
    before = convert(FIRST_TURN)
    after = convert([*FIRST_TURN, *COMPACTION, *later])
    assert before == EXPECTED_FIRST
    assert after == [
        *EXPECTED_FIRST,
        *EXPECTED_COMPACTION,
        {"role": "user", "content": "And now?"},
        {"role": "assistant", "content": "Still long."},
    ]


def test_compaction_notice_is_byte_identical_to_watchers() -> None:
    assert COMPACTION_NOTICE == (
        "[COMPACTION NOTICE]\nThe agent's earlier context was compacted at this point.\n[END NOTICE]"
    )


def test_successful_compaction_without_a_summary_is_skipped() -> None:
    assert convert([{"type": "session.compaction_complete", "data": {"success": True}}]) == [SKIPPED]


def test_truncation_records_what_left_the_models_context() -> None:
    assert convert(
        [
            *FIRST_TURN,
            {"type": "session.truncation", "data": {"messagesRemovedDuringTruncation": 5, "tokenLimit": 26000}},
        ]
    )[-1] == {
        "role": "system",
        "content": "[TRUNCATION NOTICE]\nCopilot removed 5 earlier messages from the agent's context at this point.\n"
        "[END NOTICE]",
        "metadata": {"github_copilot_cli": {"truncation": {"messages_removed": 5}}},
    }


INTERRUPTED: list[dict[str, JsonValue]] = [
    {"type": "user.message", "data": {"content": "Sleep"}},
    {
        "type": "assistant.message",
        "data": {
            "content": "",
            "toolRequests": [{"toolCallId": "call_sleep", "name": "bash", "arguments": {"command": "sleep 120"}}],
        },
    },
    {"type": "tool.execution_start", "data": {"toolCallId": "call_sleep"}},
    {"type": "assistant.turn_end", "data": {"turnId": "0"}},
    {"type": "abort", "data": {"reason": "user_initiated"}},
]


def test_abort_gives_open_calls_an_interrupted_result() -> None:
    interrupted_text = "The execution of this tool, or a previous tool was interrupted."
    assert convert([*INTERRUPTED, {"type": "user.message", "data": {"content": "Continue"}}])[2:] == [
        {
            "role": "tool",
            "tool_call_id": "call_sleep",
            "function": "Bash",
            "content": interrupted_text,
            "error": {"type": "unknown", "message": interrupted_text},
        },
        {"role": "user", "content": "Continue"},
    ]


def test_an_open_call_stays_unanswered_and_a_late_result_extends_the_snapshot() -> None:
    steering: dict[str, JsonValue] = {"type": "user.message", "data": {"content": "Steering"}}
    late: dict[str, JsonValue] = {
        "type": "tool.execution_complete",
        "data": {"toolCallId": "call_sleep", "success": True, "result": {"content": "slept"}},
    }
    before = convert([*INTERRUPTED[:-1], steering])
    after = convert([*INTERRUPTED[:-1], steering, late])
    assert [m["role"] for m in before] == ["user", "assistant", "user"]
    assert after[: len(before)] == before
    assert after[-1] == {"role": "tool", "tool_call_id": "call_sleep", "function": "Bash", "content": "slept"}


def test_a_result_after_its_interruption_keeps_the_interrupted_result() -> None:
    late: dict[str, JsonValue] = {
        "type": "tool.execution_complete",
        "data": {"toolCallId": "call_sleep", "success": True, "result": {"content": ""}},
    }
    assert convert([*INTERRUPTED, late]) == convert(INTERRUPTED)


def subagent_events(*, finished: bool) -> list[dict[str, JsonValue]]:
    """Parent delegation interleaved with the subagent's own events, as Copilot logs them."""
    child: dict[str, JsonValue] = {"agentId": AGENT_ID}
    events: list[dict[str, JsonValue]] = [
        {"type": "user.message", "data": {"content": "Delegate"}},
        {"type": "assistant.turn_start", "data": {"turnId": "0"}},
        {
            "type": "assistant.message",
            "data": {
                "content": "",
                "toolRequests": [{"toolCallId": "call_task", "name": "task", "arguments": {"prompt": "Read"}}],
            },
        },
        {"type": "subagent.started", **child, "data": {"toolCallId": "call_task", "agentName": "explore"}},
        {"type": "subagent.selected", **child, "data": {"agentName": "explore", "tools": ["view"]}},
        {"type": "session.model_change", **child, "data": {"newModel": "claude-sonnet-4-6"}},
        {"type": "user.message", **child, "data": {"content": "Read status.txt"}},
        {"type": "system.message", **child, "data": {"role": "system", "content": "Subagent instructions"}},
        {"type": "assistant.turn_start", **child, "data": {"turnId": "0", "parentToolCallId": "call_task"}},
        {
            "type": "assistant.message",
            **child,
            "data": {
                "content": "",
                "parentToolCallId": "call_task",
                "toolRequests": [{"toolCallId": "call_view", "name": "view", "arguments": {"path": "status.txt"}}],
            },
        },
        {
            "type": "tool.execution_complete",
            **child,
            "data": {"toolCallId": "call_view", "success": True, "result": {"content": "Status: ready"}},
        },
        {"type": "assistant.turn_end", **child, "data": {"turnId": "0", "parentToolCallId": "call_task"}},
        {
            "type": "tool.execution_complete",
            "data": {"toolCallId": "call_task", "success": True, "result": {"content": "ready"}},
        },
        {"type": "assistant.turn_end", "data": {"turnId": "0"}},
        {"type": "assistant.turn_start", "data": {"turnId": "1"}},
        {"type": "assistant.message", **child, "data": {"content": "ready", "parentToolCallId": "call_task"}},
    ]
    if finished:
        events.append({"type": "subagent.completed", **child, "data": {"toolCallId": "call_task", "totalToolCalls": 1}})
    events.extend(
        [
            {"type": "assistant.message", "data": {"content": "The subagent says ready."}},
            {"type": "assistant.turn_end", "data": {"turnId": "1"}},
        ]
    )
    return events


def test_subagent_events_stay_out_of_the_parent_and_are_returned_separately() -> None:
    session = convert_session(subagent_events(finished=True))
    assert session.messages == [
        {"role": "user", "content": "Delegate"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_task", "function": "Agent", "arguments": {"prompt": "Read"}}],
        },
        {
            "role": "tool",
            "tool_call_id": "call_task",
            "function": "Agent",
            "content": "ready",
            "metadata": {"github_copilot_cli": {"subagent_agent_id": AGENT_ID}},
        },
        {"role": "assistant", "content": "The subagent says ready."},
    ]
    [child] = session.subagents
    assert child.agent_id == AGENT_ID
    assert child.messages == [
        {"role": "system", "content": "Subagent instructions"},
        {"role": "user", "content": "Read status.txt"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_view", "function": "Read", "arguments": {"file_path": "status.txt"}}],
        },
        {"role": "tool", "tool_call_id": "call_view", "function": "Read", "content": "Status: ready"},
        {"role": "assistant", "content": "ready"},
    ]


def test_running_subagents_wait_for_their_end_or_the_sessions() -> None:
    events = subagent_events(finished=False)
    assert convert_session(events).subagents == []
    assert [child.agent_id for child in convert_session(events, final=True).subagents] == [AGENT_ID]


def test_parent_readiness_ignores_interleaved_subagent_turns(transcript: Path) -> None:
    events = subagent_events(finished=True)
    marker: dict[str, JsonValue] = {
        "type": "hook.start",
        "data": {
            "hookType": "agentStop",
            "input": {"sessionId": SESSION_ID, "transcriptPath": str(transcript), "timestamp": 7},
        },
    }
    write_events(transcript, [*events, marker])
    payload: dict[str, JsonValue] = {"sessionId": SESSION_ID, "transcriptPath": str(transcript), "timestamp": 7}
    session = asyncio.run(wait_for_completed_session(payload, 1))
    assert session.messages[-1] == {"role": "assistant", "content": "The subagent says ready."}
    assert len(session.subagents) == 1


def test_a_compact_only_turn_is_complete(transcript: Path) -> None:
    marker: dict[str, JsonValue] = {
        "type": "hook.start",
        "data": {
            "hookType": "agentStop",
            "input": {"sessionId": SESSION_ID, "transcriptPath": str(transcript), "timestamp": 9},
        },
    }
    write_events(transcript, [*FIRST_TURN, *COMPACTION, marker])
    payload: dict[str, JsonValue] = {"sessionId": SESSION_ID, "transcriptPath": str(transcript), "timestamp": 9}
    assert asyncio.run(wait_for_completed_session(payload, 1)).messages == [*EXPECTED_FIRST, *EXPECTED_COMPACTION]


def test_ended_session_records_open_calls_and_running_subagents(transcript: Path) -> None:
    open_call: dict[str, JsonValue] = {
        "type": "assistant.message",
        "data": {"content": "", "toolRequests": [{"toolCallId": "call_open", "name": "bash", "arguments": {}}]},
    }
    write_events(transcript, [*subagent_events(finished=False), open_call])
    session = asyncio.run(read_ended_session({"sessionId": SESSION_ID, "reason": "complete"}, 1))
    assert session.messages[-1]["tool_calls"] == [{"id": "call_open", "function": "Bash", "arguments": {}}]
    assert [child.agent_id for child in session.subagents] == [AGENT_ID]


def test_malformed_session_end_callback_is_refused() -> None:
    with pytest.raises(TranscriptError, match="^Malformed Copilot session-end callback$"):
        asyncio.run(read_ended_session({"sessionId": "PRIVATE"}, 1))


def test_attachments_are_recorded_as_copilots_descriptors_without_bytes() -> None:
    mention: dict[str, JsonValue] = {
        "type": "file",
        "path": "/work/status.txt",
        "displayName": "@status.txt",
        "mentionIndex": 27,
        "taggedFilesEntry": "* /work/status.txt (3 lines)",
    }
    image: dict[str, JsonValue] = {
        "type": "file",
        "path": "/work/red.png",
        "displayName": "red.png",
        "assetId": "sha256:red",
        "mimeType": "image/png",
        "byteLength": 17,
    }
    blob: dict[str, JsonValue] = {"type": "blob", "mimeType": "image/png", "data": PNG}
    asset: dict[str, JsonValue] = {
        "type": "session.binary_asset",
        "data": {"assetId": "sha256:red", "type": "image", "mimeType": "image/png", "byteLength": 17, "data": PNG},
    }
    user: dict[str, JsonValue] = {
        "type": "user.message",
        "data": {"content": "Look", "transformedContent": "Look (model)", "attachments": [mention, image, blob]},
    }
    messages = convert([asset, user])
    assert messages == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Look (model)"},
                {"type": "data", "data": mention},
                {"type": "data", "data": image},
                {
                    "type": "data",
                    "data": {
                        "type": "blob",
                        "mimeType": "image/png",
                        "assetId": "sha256:" + hashlib.sha256(base64.b64decode(PNG)).hexdigest(),
                        "byteLength": len(base64.b64decode(PNG)),
                    },
                },
            ],
        }
    ]
    assert PNG not in json.dumps(messages)


def test_binary_tool_results_and_citable_sources_are_recorded() -> None:
    reference: dict[str, JsonValue] = {
        "type": "image",
        "assetId": "sha256:shot",
        "mimeType": "image/png",
        "byteLength": 17,
    }
    call: dict[str, JsonValue] = {
        "type": "assistant.message",
        "data": {"content": "", "toolRequests": [{"toolCallId": "c", "name": "screenshot"}]},
    }
    result: dict[str, JsonValue] = {
        "type": "tool.execution_complete",
        "data": {
            "toolCallId": "c",
            "success": True,
            "result": {
                "content": "Captured",
                "binaryResultsForLlm": [reference],
                "citableSources": [{"url": "https://example.test"}],
            },
        },
    }
    assert convert([call, result])[-1]["content"] == [
        {"type": "text", "text": "Captured"},
        {"type": "data", "data": reference},
        {"type": "data", "data": {"citableSources": [{"url": "https://example.test"}]}},
    ]


def test_a_handoff_is_recorded_as_the_context_the_session_received() -> None:
    handoff: dict[str, JsonValue] = {
        "type": "session.handoff",
        "data": {
            "summary": "Fixed the parser.",
            "context": "Branch: fix-parser",
            "sourceType": "remote",
            "remoteSessionId": "r1",
        },
    }
    assert convert([handoff]) == [
        {
            "role": "user",
            "content": "Fixed the parser.\n\nBranch: fix-parser",
            "metadata": {"github_copilot_cli": {"handoff": {"source_type": "remote", "remote_session_id": "r1"}}},
        }
    ]


@pytest.mark.parametrize(
    "kind",
    ["auto_mode_switch.requested", "session.schedule_created", "workflow.run_settled", "mcp_app.tool_call_complete"],
)
def test_ui_and_lifecycle_events_add_nothing(kind: str) -> None:
    assert convert([{"type": kind, "data": {"prompt": "PRIVATE"}}]) == []


def test_session_end_waits_for_a_running_compaction(transcript: Path) -> None:
    write_events(transcript, [*FIRST_TURN, COMPACTION[0]])

    async def run() -> list[dict[str, JsonValue]]:
        reading = asyncio.create_task(read_ended_session({"sessionId": SESSION_ID, "reason": "complete"}, 1))
        await asyncio.sleep(0.3)
        assert not reading.done()
        write_events(transcript, [*FIRST_TURN, *COMPACTION])
        return (await reading).messages

    assert asyncio.run(run()) == [*EXPECTED_FIRST, *EXPECTED_COMPACTION]


def test_a_subagent_stop_tolerates_a_line_still_being_written(transcript: Path) -> None:
    write_events(transcript, subagent_events(finished=False))
    with transcript.open("a") as stream:
        stream.write('{"type": "assistant.message", "agentId": ')
    assert is_subagent_stop({"sessionId": AGENT_ID, "transcriptPath": str(transcript), "timestamp": 3})


@pytest.mark.parametrize(
    "event",
    [
        {"type": "abort"},
        {"type": "session.truncation", "data": {"messagesRemovedDuringTruncation": -1}},
        {"type": "subagent.completed", "data": {"toolCallId": "call"}},
    ],
)
def test_malformed_lifecycle_events_are_skipped(event: dict[str, JsonValue]) -> None:
    assert convert([event]) == [SKIPPED]


def test_model_telemetry_is_dropped_while_reading(transcript: Path) -> None:
    requests: list[JsonValue] = ["PRIVATE"] * 1000
    snapshot: dict[str, JsonValue] = {"type": "model.messages_snapshot", "data": {"messages": requests}}
    write_events(transcript, [*FIRST_TURN, snapshot])
    assert read_transcript({"sessionId": SESSION_ID, "transcriptPath": str(transcript)}) == EXPECTED_FIRST


def test_oversized_log_is_refused_rather_than_truncated(transcript: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_events(transcript, FIRST_TURN)
    monkeypatch.setattr(transcript_module, "MAX_TRANSCRIPT_BYTES", 100)
    with pytest.raises(TranscriptError, match="^Unsupported transcript path or size$"):
        read_transcript({"sessionId": SESSION_ID, "transcriptPath": str(transcript)})


def test_injected_context_reaches_the_transcript_as_the_model_saw_it() -> None:
    skill = "When invoked, read status.txt."
    content_id = "sha256:" + hashlib.sha256(skill.encode()).hexdigest()
    notification = (
        '<system_notification>\nAgent "bg" (task) has finished processing and is now idle.\n</system_notification>'
    )
    assert convert(
        [
            {"type": "skill.invoked", "data": {"name": "status-probe", "content": skill, "path": "/work/SKILL.md"}},
            {"type": "skill.invoked_ref", "data": {"contentId": content_id}},
            {
                "type": "skill.context_delivered_ref",
                "data": {
                    "contentId": content_id,
                    "prefix": '<skill-context name="status-probe">\n',
                    "suffix": "\n</skill-context>",
                },
            },
            {
                "type": "skill.context_delivered",
                "data": {"content": "<skill-context>inline</skill-context>", "source": "skill-x"},
            },
            {"type": "session.mode_notice_delivered", "data": {"mode": "plan", "content": "Plan mode is on."}},
            {
                "type": "system.notification",
                "data": {"content": notification, "kind": {"type": "agent_idle", "agentId": AGENT_ID}},
            },
        ]
    ) == [
        {"role": "user", "content": f'<skill-context name="status-probe">\n{skill}\n</skill-context>'},
        {"role": "user", "content": "<skill-context>inline</skill-context>"},
        {"role": "user", "content": "Plan mode is on."},
        {"role": "user", "content": notification, "metadata": {"github_copilot_cli": {"notification": "agent_idle"}}},
    ]


def test_skill_reference_without_its_content_is_skipped() -> None:
    reference: dict[str, JsonValue] = {"contentId": "sha256:gone", "prefix": "", "suffix": ""}
    assert convert([{"type": "skill.context_delivered_ref", "data": reference}]) == [SKIPPED]


def test_a_user_shell_command_is_recorded_as_the_model_sees_it() -> None:
    # Captured from Copilot 1.0.89 after `!echo hi-from-user-shell-4471`, with the
    # model request that followed.
    events: list[dict[str, JsonValue]] = [
        *FIRST_TURN,
        {
            "type": "tool.user_requested",
            "data": {
                "toolCallId": "925216f6",
                "toolName": "local_shell",
                "arguments": {"command": "echo hi-from-user-shell-4471", "description": "Execute shell command"},
            },
        },
        {
            "type": "tool.execution_complete",
            "data": {
                "toolCallId": "925216f6",
                "isUserRequested": True,
                "success": True,
                "shellExecution": {"exitCode": 0},
                "result": {"content": "hi-from-user-shell-4471"},
            },
        },
    ]
    assert convert(events) == [
        *EXPECTED_FIRST,
        {
            "role": "user",
            "content": "<user_shell_command_output>\nThe user executed a shell command directly in their terminal "
            "(exit code 0).\n\nCommand:\necho hi-from-user-shell-4471\n\nOutput:\nhi-from-user-shell-4471\n"
            "</user_shell_command_output>",
        },
    ]


def test_a_rewind_diverges_from_the_rewound_turn() -> None:
    # Copilot rewrites the log without the rewound turn, its prompt included, and
    # appends only this marker. The retry then extends the kept turns, so Watcher
    # stores it as a new branch of the history recorded before the rewind.
    rewound: list[dict[str, JsonValue]] = [
        {"type": "user.message", "data": {"content": "Read big.txt again"}},
        {"type": "assistant.message", "data": {"content": "Still long."}},
    ]
    marker: dict[str, JsonValue] = {
        "type": "session.info",
        "data": {"message": "Rewound the conversation. Your files were left unchanged.", "infoType": "rewind"},
    }
    retry: list[dict[str, JsonValue]] = [
        {"type": "user.message", "data": {"content": "Read small.txt instead"}},
        {"type": "assistant.message", "data": {"content": "Done."}},
    ]
    before = convert([*FIRST_TURN, *rewound])
    after = convert([*FIRST_TURN, marker, *retry])
    assert before[: len(EXPECTED_FIRST)] == after[: len(EXPECTED_FIRST)] == EXPECTED_FIRST
    assert after[len(EXPECTED_FIRST) :] == [
        {"role": "user", "content": "Read small.txt instead"},
        {"role": "assistant", "content": "Done."},
    ]


def test_a_subagents_agent_stop_is_recognised_and_skipped(transcript: Path) -> None:
    write_events(transcript, subagent_events(finished=False))
    subagent_stop: dict[str, JsonValue] = {"sessionId": AGENT_ID, "transcriptPath": str(transcript), "timestamp": 3}
    parent_stop: dict[str, JsonValue] = {"sessionId": SESSION_ID, "transcriptPath": str(transcript), "timestamp": 4}
    assert is_subagent_stop(subagent_stop)
    assert not is_subagent_stop(parent_stop)


def test_an_unrelated_session_id_with_a_transcript_is_refused(transcript: Path) -> None:
    write_events(transcript, FIRST_TURN)
    stranger: dict[str, JsonValue] = {"sessionId": AGENT_ID, "transcriptPath": str(transcript)}
    with pytest.raises(TranscriptError, match="does not match its transcript"):
        is_subagent_stop(stranger)


def test_an_abort_only_closes_calls_in_the_conversation_it_names() -> None:
    child: dict[str, JsonValue] = {"agentId": AGENT_ID}
    parent_call: dict[str, JsonValue] = {
        "type": "assistant.message",
        "data": {"content": "", "toolRequests": [{"toolCallId": "parent_call", "name": "task", "arguments": {}}]},
    }
    child_call: dict[str, JsonValue] = {
        "type": "assistant.message",
        **child,
        "data": {"content": "", "toolRequests": [{"toolCallId": "child_call", "name": "bash", "arguments": {}}]},
    }
    child_abort: dict[str, JsonValue] = {"type": "abort", **child, "data": {"reason": "user_initiated"}}
    parent_result: dict[str, JsonValue] = {
        "type": "tool.execution_complete",
        "data": {"toolCallId": "parent_call", "success": True, "result": {"content": "done"}},
    }
    session = convert_session([parent_call, child_call, child_abort, parent_result], final=True)
    assert session.messages[-1]["content"] == "done"
    [history] = session.subagents
    assert history.messages[-1]["tool_call_id"] == "child_call"
    assert history.messages[-1]["content"] == "The execution of this tool, or a previous tool was interrupted."


def test_a_parent_abort_leaves_a_subagents_open_call_unanswered() -> None:
    child: dict[str, JsonValue] = {"agentId": AGENT_ID}
    events: list[dict[str, JsonValue]] = [
        {
            "type": "assistant.message",
            "data": {"content": "", "toolRequests": [{"toolCallId": "p", "name": "task", "arguments": {}}]},
        },
        {
            "type": "assistant.message",
            **child,
            "data": {"content": "", "toolRequests": [{"toolCallId": "c", "name": "bash", "arguments": {}}]},
        },
        {"type": "abort", "data": {"reason": "user_initiated"}},
    ]
    session = convert_session(events, final=True)
    assert session.messages[-1]["tool_call_id"] == "p"
    assert session.subagents[0].messages[-1]["tool_calls"] == [{"id": "c", "function": "Bash", "arguments": {}}]


def test_nothing_is_recorded_at_session_end_before_the_first_reply(transcript: Path) -> None:
    write_events(transcript, FIRST_TURN[:3])
    payload: dict[str, JsonValue] = {"sessionId": SESSION_ID, "reason": "abort"}

    async def run() -> None:
        # The address is never contacted: nothing is recorded before the first reply.
        async with AsyncWatcherClient("http://unused.test/api", api_key="PRIVATE_KEY") as client:
            assert await observe_callback(client, payload, grade=True) is None

    asyncio.run(run())


def test_a_subagent_without_a_reply_is_not_recorded_even_at_session_end() -> None:
    child: dict[str, JsonValue] = {"agentId": AGENT_ID}
    events: list[dict[str, JsonValue]] = [
        {"type": "subagent.started", **child, "data": {"toolCallId": "call_task"}},
        {"type": "user.message", **child, "data": {"content": "Read status.txt"}},
    ]
    assert convert_session(events, final=True).subagents == []


def test_inline_binary_bytes_keep_copilots_content_identity() -> None:
    red, blue = base64.b64encode(b"red-png").decode(), base64.b64encode(b"blue-png").decode()
    call: dict[str, JsonValue] = {
        "type": "assistant.message",
        "data": {"content": "", "toolRequests": [{"toolCallId": "c", "name": "shot"}]},
    }
    result: dict[str, JsonValue] = {
        "type": "tool.execution_complete",
        "data": {
            "toolCallId": "c",
            "success": True,
            "result": {
                "content": "Two images",
                "binaryResultsForLlm": [
                    {"type": "image", "mimeType": "image/png", "data": red},
                    {"type": "image", "mimeType": "image/png", "data": blue},
                ],
            },
        },
    }
    content = convert([call, result])[-1]["content"]
    assert isinstance(content, list)
    assert content[1:] == [
        {
            "type": "data",
            "data": {
                "type": "image",
                "mimeType": "image/png",
                "assetId": "sha256:" + hashlib.sha256(b"red-png").hexdigest(),
                "byteLength": 7,
            },
        },
        {
            "type": "data",
            "data": {
                "type": "image",
                "mimeType": "image/png",
                "assetId": "sha256:" + hashlib.sha256(b"blue-png").hexdigest(),
                "byteLength": 8,
            },
        },
    ]


@pytest.mark.parametrize(
    "inline,expected",
    [
        (
            "\n".join(["cmVkLXBu", "Zw=="]),
            {"assetId": "sha256:" + hashlib.sha256(b"red-png").hexdigest(), "byteLength": 7},
        ),
        (
            "data:image/png;base64,cmVkLXBuZw==",
            {"assetId": "sha256:" + hashlib.sha256(b"red-png").hexdigest(), "byteLength": 7},
        ),
        ("not base64!", {"omittedReason": "undecodable"}),
    ],
)
def test_inline_bytes_are_parsed_liberally_and_never_block_recording(
    inline: str, expected: dict[str, JsonValue]
) -> None:
    user: dict[str, JsonValue] = {
        "type": "user.message",
        "data": {"content": "Look", "attachments": [{"type": "blob", "mimeType": "image/png", "data": inline}]},
    }
    [message] = convert([user])
    assert message["content"] == [
        {"type": "text", "text": "Look"},
        {"type": "data", "data": {"type": "blob", "mimeType": "image/png", **expected}},
    ]


def test_a_line_still_being_written_late_in_a_compaction_wait_is_retried(transcript: Path) -> None:
    write_events(transcript, [*FIRST_TURN, COMPACTION[0]])

    async def run() -> list[dict[str, JsonValue]]:
        reading = asyncio.create_task(
            read_ended_session({"sessionId": SESSION_ID, "reason": "complete"}, 0.2, compaction_seconds=2)
        )
        await asyncio.sleep(0.6)
        with transcript.open("a") as stream:
            stream.write('{"type": "session.compaction_complete", "data": {"success": tr')
        await asyncio.sleep(0.4)
        assert not reading.done()
        write_events(transcript, [*FIRST_TURN, *COMPACTION])
        return (await reading).messages

    assert asyncio.run(run()) == [*EXPECTED_FIRST, *EXPECTED_COMPACTION]


def test_a_compaction_left_by_an_earlier_invocation_is_not_awaited(transcript: Path) -> None:
    resumed: dict[str, JsonValue] = {"type": "session.resume", "data": {"eventCount": 9}}
    write_events(transcript, [*FIRST_TURN, COMPACTION[0], resumed])

    async def run() -> float:
        loop = asyncio.get_running_loop()
        started = loop.time()
        await read_ended_session({"sessionId": SESSION_ID, "reason": "complete"}, 1, compaction_seconds=5)
        return loop.time() - started

    assert asyncio.run(run()) < 1


def test_a_replayed_session_start_from_a_handoff_is_accepted() -> None:
    other: dict[str, JsonValue] = {"type": "session.start", "data": {"sessionId": AGENT_ID}}
    assert convert([*FIRST_TURN, other]) == EXPECTED_FIRST


def test_a_crashed_call_is_interrupted_when_the_session_resumes() -> None:
    crashed: list[dict[str, JsonValue]] = [
        {"type": "session.start", "data": {"sessionId": SESSION_ID}},
        {"type": "user.message", "data": {"content": "Run the steps"}},
        {
            "type": "assistant.message",
            "data": {"content": "", "toolRequests": [{"toolCallId": "step3", "name": "bash", "arguments": {}}]},
        },
        {"type": "subagent.started", "agentId": AGENT_ID, "data": {"toolCallId": "task"}},
        {"type": "user.message", "agentId": AGENT_ID, "data": {"content": "Help"}},
        {
            "type": "assistant.message",
            "agentId": AGENT_ID,
            "data": {"content": "", "toolRequests": [{"toolCallId": "child", "name": "view", "arguments": {}}]},
        },
    ]
    before = convert_session(crashed)
    assert before.messages[-1]["tool_calls"] == [{"id": "step3", "function": "Bash", "arguments": {}}]
    assert before.subagents == []
    resumed = convert_session([*crashed, {"type": "session.resume", "data": {"eventCount": 6}}])
    interrupted: dict[str, JsonValue] = {
        "role": "tool",
        "tool_call_id": "step3",
        "function": "Bash",
        "content": transcript_module.INTERRUPTED,
        "error": {"type": "unknown", "message": transcript_module.INTERRUPTED},
    }
    assert resumed.messages == [*before.messages, interrupted]
    [child] = resumed.subagents
    assert child.messages[-1] == {**interrupted, "tool_call_id": "child", "function": "Read"}


def test_a_failed_model_request_is_recorded_and_ends_the_first_turn() -> None:
    failed: list[dict[str, JsonValue]] = [
        {"type": "session.start", "data": {"sessionId": SESSION_ID}},
        {"type": "user.message", "data": {"content": "Hello"}},
        {
            "type": "session.error",
            "data": {"errorType": "query", "message": "PRIVATE provider text", "statusCode": 500},
        },
        {"type": "session.resume", "data": {"eventCount": 3}},
        {"type": "session.error", "data": {"errorType": "model-provider-labels", "message": "Not authenticated"}},
        {"type": "system.message", "data": {"role": "system", "content": "Instructions"}},
    ]
    session = convert_session(failed)
    assert session.replied
    assert session.messages == [
        {"role": "user", "content": "Hello"},
        {
            "role": "system",
            "content": "[ERROR NOTICE]\nCopilot reported an error (query, HTTP 500).\n[END NOTICE]",
            "metadata": {"github_copilot_cli": {"error": {"type": "query", "status_code": 500}}},
        },
        {"role": "system", "content": "Instructions"},
    ]
    assert "PRIVATE" not in json.dumps(session.messages)
    assert not convert_session(failed[:2]).replied


def test_a_large_tool_result_is_cut_at_a_fixed_length() -> None:
    big = "z" * (MAX_TOOL_TEXT + 10)
    events: list[dict[str, JsonValue]] = [
        *FIRST_TURN[:5],
        {
            "type": "tool.execution_complete",
            "data": {"toolCallId": "call_1", "success": True, "result": {"content": big}},
        },
    ]
    content = convert(events)[-1]["content"]
    assert isinstance(content, str) and content.startswith("z" * MAX_TOOL_TEXT)
    assert content.endswith(
        f"[Watcher recorded the first {MAX_TOOL_TEXT} of {MAX_TOOL_TEXT + 10} characters of this result.]"
    )


@pytest.mark.parametrize("joined", [{"alreadyInUse": True}, {"sessionWasActive": True}, {"continuePendingWork": True}])
def test_a_resume_that_joins_running_work_interrupts_nothing(joined: dict[str, JsonValue]) -> None:
    running: list[dict[str, JsonValue]] = [
        {"type": "user.message", "data": {"content": "Run the steps"}},
        {
            "type": "assistant.message",
            "data": {"content": "", "toolRequests": [{"toolCallId": "step", "name": "bash", "arguments": {}}]},
        },
        {"type": "session.resume", "data": {"eventCount": 2, **joined}},
        {
            "type": "tool.execution_complete",
            "data": {"toolCallId": "step", "success": True, "result": {"content": "ok"}},
        },
    ]
    assert convert(running)[-1] == {"role": "tool", "tool_call_id": "step", "function": "Bash", "content": "ok"}


def test_a_failed_or_cancelled_user_shell_command_is_recorded_as_the_model_sees_it() -> None:
    # Captured from Copilot 1.0.89 with the model requests that followed.
    events: list[dict[str, JsonValue]] = [
        {"type": "tool.user_requested", "data": {"toolCallId": "f", "arguments": {"command": "false"}}},
        {
            "type": "tool.execution_complete",
            "data": {
                "toolCallId": "f",
                "isUserRequested": True,
                "success": False,
                "shellExecution": {"exitCode": 1},
                "error": {"message": "out\nerr"},
            },
        },
        {"type": "tool.user_requested", "data": {"toolCallId": "s", "arguments": {"command": "sleep 30"}}},
        {
            "type": "tool.execution_complete",
            "data": {
                "toolCallId": "s",
                "isUserRequested": True,
                "success": False,
                "error": {"message": "Shell command canceled."},
            },
        },
    ]
    template = (
        "<user_shell_command_output>\nThe user executed a shell command directly in their terminal "
        "(non-zero exit code).\n\nCommand:\n{}\n\nOutput:\n{}\n</user_shell_command_output>"
    )
    assert convert(events) == [
        {"role": "user", "content": template.format("false", "out\nerr")},
        {"role": "user", "content": template.format("sleep 30", "Shell command canceled.")},
    ]


def test_the_latest_turn_starts_after_the_previous_final_answer() -> None:
    def call(identifier: str) -> list[dict[str, JsonValue]]:
        return [
            {
                "type": "assistant.message",
                "data": {"content": "", "toolRequests": [{"toolCallId": identifier, "name": "view", "arguments": {}}]},
            },
            {
                "type": "tool.execution_complete",
                "data": {"toolCallId": identifier, "success": True, "result": {"content": ""}},
            },
        ]

    events: list[dict[str, JsonValue]] = [
        {"type": "user.message", "data": {"content": "first"}},
        *call("done"),
        {"type": "assistant.message", "data": {"content": "First answer."}},
        {"type": "user.message", "data": {"content": "second"}},
        *call("before-steering"),
        {"type": "user.message", "data": {"content": "steering"}},
        *call("after-steering"),
        {"type": "assistant.message", "data": {"content": "Second answer."}},
    ]
    session = convert_session(events)
    later = session.messages[session.turn_start :]
    ids: list[JsonValue] = []
    for message in later:
        calls = message.get("tool_calls")
        if isinstance(calls, list):
            ids += [call["id"] for call in calls if isinstance(call, dict)]
    assert ids == ["before-steering", "after-steering"]
    assert later[0] == {"role": "user", "content": "second"}


def test_a_trailing_notice_does_not_hide_a_completed_turn(transcript: Path) -> None:
    write_events(transcript, [*FIRST_TURN, {"type": "future.lifecycle_event", "data": {}}])
    payload: dict[str, JsonValue] = {"sessionId": SESSION_ID, "transcriptPath": str(transcript)}
    messages = asyncio.run(wait_for_completed_session(payload, 1)).messages
    assert messages[: len(EXPECTED_FIRST)] == EXPECTED_FIRST
    assert "future.lifecycle_event" in str(messages[-1]["content"])


def test_nul_characters_are_removed_as_watcher_would_store_them() -> None:
    events: list[dict[str, JsonValue]] = [
        *FIRST_TURN[:5],
        {
            "type": "tool.execution_complete",
            "data": {"toolCallId": "call_1", "success": True, "result": {"content": "a\u0000b"}},
        },
    ]
    assert convert(events)[-1]["content"] == "ab"


def test_a_chunked_answer_ends_the_turn_only_at_its_last_chunk() -> None:
    events: list[dict[str, JsonValue]] = [
        {"type": "user.message", "data": {"content": "first"}},
        {"type": "assistant.message", "data": {"content": "First answer."}},
        {"type": "user.message", "data": {"content": "second"}},
        {
            "type": "assistant.message",
            "data": {"content": "", "toolRequests": [{"toolCallId": "call", "name": "view", "arguments": {}}]},
        },
        {"type": "tool.execution_complete", "data": {"toolCallId": "call", "success": True, "result": {"content": ""}}},
        {"type": "assistant.message", "data": {"content": "Part one.", "chunkIndex": 0, "chunkCount": 2}},
        {"type": "assistant.message", "data": {"content": "Part two.", "chunkIndex": 1, "chunkCount": 2}},
    ]
    session = convert_session(events)
    assert session.messages[session.turn_start] == {"role": "user", "content": "second"}
    # Chunk fields without a count cannot show which chunk is last, so the boundary stays.
    partial: list[dict[str, JsonValue]] = [
        event for event in events if event["type"] != "assistant.message" or "chunkIndex" not in json.dumps(event)
    ]
    chunks: list[dict[str, JsonValue]] = [
        {"type": "assistant.message", "data": {"content": "Part one.", "chunkIndex": 0}},
        {"type": "assistant.message", "data": {"content": "Part two.", "chunkIndex": 1}},
    ]
    unfinished = convert_session([*partial, *chunks])
    assert unfinished.messages[unfinished.turn_start] == {"role": "user", "content": "first"}
