"""Hermes session exports convert to the Inspect messages Watcher grades and stores."""

import asyncio
import json
from pathlib import Path

import pytest
from watcher_hermes import transcript
from watcher_hermes.transcript import convert, decode_arguments, export_session, external_ids, with_pending_call

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    """Load one captured Hermes fixture by file name."""
    return json.loads((FIXTURES / name).read_text())


def export_line(session: dict) -> str:
    """Render a session the way ``hermes sessions export -`` prints it: one JSON line."""
    return json.dumps(session) + "\n"


def test_real_export_keeps_calls_results_and_order():
    """A captured terminal + read_file session converts with native IDs, decoded arguments and results."""
    session = load("session-terminal-read.json")
    messages = convert(session["messages"])
    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "assistant", "tool", "assistant"]
    first_call = messages[1]["tool_calls"][0]
    assert first_call["function"] == "terminal"
    assert first_call["arguments"] == {"command": "ls /tmp | head -3", "workdir": "/tmp", "timeout": 30}
    assert first_call["id"] == session["messages"][1]["tool_calls"][0]["id"]
    assert messages[2] == {
        "role": "tool",
        "content": session["messages"][2]["content"],
        "tool_call_id": first_call["id"],
        "function": "terminal",
    }
    assert messages[4]["function"] == "read_file"
    assert messages[-1]["content"] == [{"type": "text", "text": "DONE"}]
    assert all("message_uid" not in m and "timestamp" not in m for m in messages)


def test_escalation_session_records_both_human_outcomes_as_results():
    """The captured session with an approved and a denied escalation keeps both results under their calls."""
    messages = convert(load("session-escalations.json")["messages"])
    calls = [c for m in messages for c in m.get("tool_calls", [])]
    results = {m["tool_call_id"]: m["content"] for m in messages if m["role"] == "tool"}
    assert len(calls) == 2 and set(results) == {c["id"] for c in calls}
    assert "BLOCKED" in results[calls[1]["id"]] or "denied" in results[calls[1]["id"]].lower()


def test_source_rows_are_not_modified():
    rows = load("session-terminal-read.json")["messages"]
    before = json.dumps(rows, sort_keys=True)
    convert(rows)
    assert json.dumps(rows, sort_keys=True) == before


def test_only_rows_the_model_sees_are_kept():
    """Rewinds and compaction retire rows; only active rows (or unflagged in-memory rows) stay."""
    rows = [
        {"role": "user", "content": "kept", "active": 1, "compacted": 0},
        {"role": "user", "content": "archived", "active": 0, "compacted": 1},
        {"role": "user", "content": "rewound", "active": 0, "compacted": 0},
        {"role": "user", "content": "in memory"},
    ]
    assert [m["content"] for m in convert(rows)] == ["kept", "in memory"]


def test_content_parts_reasoning_and_system_rows():
    rows = [
        {"role": "system", "content": "ignored"},
        {"role": "user", "content": [{"type": "text", "text": "look"}, {"type": "image_url", "image_url": {}}, "raw"]},
        {"role": "assistant", "content": None, "reasoning": "thinking", "tool_calls": []},
    ]
    assert convert(rows) == [
        {"role": "user", "content": "look\n[image_url omitted]\nraw"},
        {"role": "assistant", "content": [{"type": "reasoning", "reasoning": "thinking"}]},
    ]


@pytest.mark.parametrize(
    "rows",
    [
        [{"role": "tool", "tool_call_id": "missing", "content": "x"}],
        [{"role": "narrator", "content": "x"}],
        ["not a row"],
        [{"role": "user", "content": 7}],
        [{"role": "user", "content": [7]}],
        [{"role": "assistant", "tool_calls": [{"id": "", "function": {"name": "terminal"}}]}],
        [{"role": "assistant", "tool_calls": [{"id": "c", "function": "terminal"}]}],
        [{"role": "assistant", "tool_calls": [{"id": "c", "function": {"name": "t", "arguments": 7}}]}],
    ],
)
def test_unsupported_rows_fail_visibly(rows):
    with pytest.raises(ValueError):
        convert(rows)


@pytest.mark.parametrize(
    "value,expected",
    [
        ('{"a": 1}', {"a": 1}),
        ({"a": 1}, {"a": 1}),
        ("", {}),
        (None, {}),
        ("not json", {"_raw_arguments": "not json"}),
        ("[1, 2]", {"_raw_arguments": "[1, 2]"}),
    ],
)
def test_decode_arguments(value, expected):
    assert decode_arguments(value) == expected


def test_call_id_falls_back_to_call_id_key():
    rows = [{"role": "assistant", "tool_calls": [{"call_id": "c1", "function": {"name": "t", "arguments": "{}"}}]}]
    assert convert(rows)[0]["tool_calls"] == [{"id": "c1", "function": "t", "arguments": {}}]


CALL = {"id": "c1", "function": "terminal", "arguments": {"command": "ls"}}


def test_pending_call_already_stored_is_unchanged():
    messages = [{"role": "assistant", "content": [], "tool_calls": [dict(CALL)]}]
    assert with_pending_call(messages, CALL) == messages


def test_pending_call_missing_from_history_is_refused():
    """A call absent from the export (e.g. a background review agent's) cannot be graded in context."""
    with pytest.raises(ValueError):
        with_pending_call([{"role": "user", "content": "go"}], CALL)


def bridge(arguments):
    return [
        {"role": "assistant", "tool_calls": [{"id": "b1", "function": {"name": "tool_call", "arguments": arguments}}]}
    ]


@pytest.mark.parametrize(
    "arguments",
    [
        json.dumps({"calls": [{"name": "mcp_files_read", "arguments": {"path": "a"}}]}),
        json.dumps({"calls": json.dumps([{"name": "mcp_files_read", "arguments": '{"path": "a"}'}])}),
        json.dumps({"calls": {"name": "mcp_files_read", "arguments": {"path": "a"}}}),
        json.dumps({"name": " mcp_files_read ", "arguments": {"path": "a"}}),
        json.dumps({"calls": None, "name": "mcp_files_read", "arguments": {"path": "a"}}),
    ],
)
def test_single_bridge_call_becomes_the_underlying_tool(arguments):
    """Hermes passes pre_tool_call the tool the bridge runs; the transcript must name the same call."""
    (message,) = convert(bridge(arguments))
    assert message["tool_calls"] == [{"id": "b1", "function": "mcp_files_read", "arguments": {"path": "a"}}]
    pending = {"id": "b1", "function": "mcp_files_read", "arguments": {"path": "a"}}
    assert with_pending_call([message], pending) == [message]


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_bridge_blank_arguments_mean_no_arguments(blank):
    (message,) = convert(bridge(json.dumps({"calls": [{"name": "mcp_ping", "arguments": blank}]})))
    assert message["tool_calls"] == [{"id": "b1", "function": "mcp_ping", "arguments": {}}]


def test_malformed_bridge_history_does_not_block_later_calls():
    """A stored bridge call with invalid nested arguments converts as-is, and a later call is still gated."""
    rows = [
        *bridge(json.dumps({"calls": [{"name": "mcp_files_read", "arguments": []}]})),
        {"role": "tool", "tool_call_id": "b1", "content": "error"},
        {
            "role": "assistant",
            "tool_calls": [{"id": "c1", "function": {"name": "terminal", "arguments": '{"command": "ls"}'}}],
        },
    ]
    messages = convert(rows)
    assert messages[0]["tool_calls"][0]["function"] == "tool_call"
    assert with_pending_call(messages, CALL) == messages


@pytest.mark.parametrize(
    "arguments",
    [
        json.dumps({"calls": [{"name": "a", "arguments": {}}, {"name": "b", "arguments": {}}]}),
        json.dumps({"calls": "not json"}),
        json.dumps({"calls": []}),
        json.dumps({"calls": [{"name": ""}]}),
        json.dumps({"calls": ["x"]}),
        json.dumps({"other": 1}),
        json.dumps({"calls": [{"name": "connectors__github__list_issues", "arguments": {}}]}),
        json.dumps({"calls": [{"name": "mcp_files_read", "arguments": 7}]}),
    ],
)
def test_other_bridge_shapes_stay_as_stored(arguments):
    (message,) = convert(bridge(arguments))
    assert message["tool_calls"][0]["function"] == "tool_call"


@pytest.mark.parametrize(
    "messages",
    [
        [{"role": "assistant", "tool_calls": [{**CALL, "arguments": {"command": "rm"}}]}],
        [{"role": "assistant", "tool_calls": [{**CALL, "function": "write_file"}]}],
        [{"role": "assistant", "tool_calls": [CALL, CALL]}],
        [
            {"role": "assistant", "tool_calls": [CALL]},
            {"role": "tool", "tool_call_id": "c1", "content": "done", "function": "terminal"},
        ],
    ],
)
def test_pending_call_that_disagrees_or_ran_is_refused(messages):
    with pytest.raises(ValueError):
        with_pending_call(messages, CALL)


def test_external_ids_name_the_session():
    assert external_ids("s1") == {"other": "hermes:s1"}
    with pytest.raises(ValueError):
        external_ids("")


def test_export_reads_the_named_session(fake_hermes, tmp_path):
    session = load("session-terminal-read.json")
    hermes = fake_hermes(export_line({"id": "other"}) + export_line(session))
    rows = asyncio.run(export_session(session["id"], hermes_bin=hermes))
    assert rows == session["messages"]
    assert json.loads((tmp_path / "argv.json").read_text()) == [
        "sessions",
        "export",
        "-",
        "--session-id",
        session["id"],
    ]


@pytest.mark.parametrize(
    "output,returncode",
    [("", 0), (export_line({"id": "s"}), 3), (export_line({"id": "s", "messages": "x"}), 0), ("[]\n", 0)],
)
def test_export_failures_raise(fake_hermes, output, returncode):
    with pytest.raises(ValueError):
        asyncio.run(export_session("s", hermes_bin=fake_hermes(output, returncode=returncode)))


def test_export_deadline_kills_the_child(fake_hermes, monkeypatch):
    monkeypatch.setattr(transcript, "EXPORT_TIMEOUT_SECONDS", 0.2)
    with pytest.raises(TimeoutError):
        asyncio.run(export_session("s", hermes_bin=fake_hermes("", sleep=30)))


def test_missing_hermes_command(monkeypatch):
    monkeypatch.setattr(transcript.shutil, "which", lambda name: None)
    with pytest.raises(FileNotFoundError):
        transcript.hermes_command(None)
    assert transcript.hermes_command("/opt/hermes") == "/opt/hermes"
