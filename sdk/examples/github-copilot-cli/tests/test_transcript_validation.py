"""Refuse incomplete or unsupported native histories without exposing their contents."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import JsonValue
from watcher_github_copilot_cli.integration import further_path_checks
from watcher_github_copilot_cli.transcript import (
    SKIPPED_EVENT_NOTICE,
    TranscriptError,
    UnsupportedTranscriptError,
    convert_session,
    policy_call,
    read_transcript,
)


def convert(events: list[dict[str, JsonValue]]) -> list[dict[str, JsonValue]]:
    return convert_session(events).messages


SKIPPED: dict[str, JsonValue] = {
    "role": "system",
    "content": SKIPPED_EVENT_NOTICE,
    "metadata": {"github_copilot_cli": {"skipped_events": True}},
}


@pytest.mark.parametrize("kind", ["assistant.unknown_content", "tool.unknown_result", "custom.content"])
def test_unknown_events_are_marked_where_they_occurred_without_their_content(kind: str) -> None:
    messages = convert(
        [
            {"type": "user.message", "data": {"content": "first"}},
            {"type": kind, "data": {"content": "PRIVATE native content"}},
            {"type": kind, "data": {"content": "PRIVATE native content"}},
            {"type": "assistant.message", "data": {"content": "answer"}},
        ]
    )
    assert messages == [
        {"role": "user", "content": "first"},
        {
            "role": "system",
            "content": f"[UNSUPPORTED EVENT NOTICE]\nCopilot recorded {kind} events from here on, "
            "which this integration does not record.\n[END NOTICE]",
            "metadata": {"github_copilot_cli": {"unsupported_event": kind}},
        },
        {"role": "assistant", "content": "answer"},
    ]
    assert "PRIVATE" not in json.dumps(messages)


def test_provider_content_blocks_are_refused() -> None:
    event: dict[str, JsonValue] = {
        "type": "assistant.message",
        "data": {"content": "Visible answer", "providerContentBlocks": [{"type": "PRIVATE native content"}]},
    }
    with pytest.raises(UnsupportedTranscriptError, match="^Unsupported Copilot content$"):
        convert([event])


def test_readable_reasoning_is_recorded_before_the_assistant_text() -> None:
    signature = "PRIVATE anthropic signature"
    assert convert(
        [
            {"type": "user.message", "data": {"content": "Update the status."}},
            {
                "type": "assistant.message",
                "data": {
                    "content": "",
                    "reasoningText": "I should read the file first.",
                    "reasoningOpaque": signature,
                    "reasoningBlocks": {
                        "provider": "anthropic-messages",
                        "blocks": [
                            {"type": "thinking", "thinking": "I should read the file first.", "signature": signature}
                        ],
                    },
                    "toolRequests": [{"toolCallId": "toolu_1", "name": "view", "arguments": {"path": "status.txt"}}],
                },
            },
            {"type": "assistant.reasoning_delta", "data": {"reasoningId": "r1", "deltaContent": "I should"}},
            {"type": "assistant.reasoning", "data": {"reasoningId": "r1", "content": "I should read the file first."}},
            {
                "type": "tool.execution_complete",
                "data": {"toolCallId": "toolu_1", "success": True, "result": {"content": "Status: pending"}},
            },
            {
                "type": "assistant.message",
                "data": {"content": "The status is pending.", "reasoningText": "The file is short."},
            },
        ]
    ) == [
        {"role": "user", "content": "Update the status."},
        {
            "role": "assistant",
            "content": [
                {"type": "reasoning", "reasoning": "", "summary": "I should read the file first.", "redacted": True}
            ],
            "tool_calls": [{"id": "toolu_1", "function": "Read", "arguments": {"file_path": "status.txt"}}],
        },
        {"role": "tool", "tool_call_id": "toolu_1", "function": "Read", "content": "Status: pending"},
        {
            "role": "assistant",
            "content": [
                {"type": "reasoning", "reasoning": "", "summary": "The file is short.", "redacted": True},
                {"type": "text", "text": "The status is pending."},
            ],
        },
    ]


def test_encrypted_reasoning_is_not_recorded() -> None:
    ciphertext = "PRIVATE encrypted reasoning"
    messages = convert(
        [
            {
                "type": "assistant.message",
                "data": {
                    "content": "Status: complete",
                    "phase": "final_answer",
                    "serverTools": {"provider": "openai-responses"},
                    "reasoningOpaque": "rs_native",
                    "reasoningText": "",
                    "encryptedContent": ciphertext,
                    "reasoningBlocks": {
                        "provider": "openai-responses",
                        "blocks": [
                            {
                                "id": "rs_native",
                                "type": "reasoning",
                                "content": [],
                                "encrypted_content": ciphertext,
                                "summary": [],
                            }
                        ],
                    },
                },
            }
        ]
    )
    assert messages == [{"role": "assistant", "content": "Status: complete"}]
    assert ciphertext not in json.dumps(messages)


def test_freeform_patch_is_recorded_as_an_edit_keeping_its_raw_input() -> None:
    patch = "*** Begin Patch\n*** Update File: status.txt\n@@\n-Status: pending\n+Status: complete\n*** End Patch\n"
    assert convert(
        [
            {
                "type": "assistant.message",
                "data": {
                    "content": "",
                    "toolRequests": [
                        {"toolCallId": "custom_call_1", "name": "apply_patch", "arguments": patch, "type": "custom"}
                    ],
                },
            },
            {
                "type": "tool.execution_complete",
                "data": {"toolCallId": "custom_call_1", "success": True, "result": {"content": "Modified 1 file(s)"}},
            },
        ]
    ) == [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "custom_call_1",
                    "function": "Edit",
                    "arguments": {"file_path": "status.txt", "input": patch},
                    "type": "custom",
                }
            ],
        },
        {"role": "tool", "tool_call_id": "custom_call_1", "function": "Edit", "content": "Modified 1 file(s)"},
    ]


@pytest.mark.parametrize(
    "name,arguments,expected",
    [
        (
            "write_bash",
            {"shellId": "0", "input": "rm -rf build\n", "delay": 5},
            ("Bash", {"command": "rm -rf build\n", "shellId": "0", "delay": 5}),
        ),
        ("write_bash", {"shellId": "0", "input": ["not", "text"]}, None),
        ("write_bash", {"shellId": "0"}, None),
        (
            "apply_patch",
            {"input": "*** Begin Patch\n*** Add File: notes.txt\n+hi\n*** End Patch\n"},
            (
                "Write",
                {"file_path": "notes.txt", "input": "*** Begin Patch\n*** Add File: notes.txt\n+hi\n*** End Patch\n"},
            ),
        ),
        (
            "apply_patch",
            {"input": "*** Begin Patch\n*** Delete File: old.txt\n*** End Patch\n"},
            ("Edit", {"file_path": "old.txt", "input": "*** Begin Patch\n*** Delete File: old.txt\n*** End Patch\n"}),
        ),
        ("apply_patch", {"input": "not a patch"}, None),
        ("apply_patch", {"input": 7}, None),
    ],
)
def test_policy_call_maps_typed_shell_input_and_patches(
    name: str, arguments: dict[str, JsonValue], expected: tuple[str, dict[str, JsonValue]] | None
) -> None:
    assert policy_call(name, arguments) == (expected or (name, arguments))


def judged_patch_paths(patch: str) -> list[tuple[str, str]]:
    """Each ``(tool, path)`` the gate judges for an ``apply_patch`` call: its own call, then each further path."""
    name, arguments = policy_call("apply_patch", {"input": patch})
    further = further_path_checks("apply_patch", {"input": patch})
    paths = [(name, arguments["file_path"])] if "file_path" in arguments else [(name, "")]
    for check in further:
        tool_input = check["tool_input"]
        assert isinstance(check["tool_name"], str) and isinstance(tool_input, dict)
        assert isinstance(tool_input["file_path"], str)
        paths.append((check["tool_name"], tool_input["file_path"]))
    return paths


# Copilot's own patch parser (its native patchParse, in 1.0.89 and 1.0.91) splits
# lines at LF, CR and CRLF, then trims each line before it reads a header, and the
# path after it, as JavaScript's String.prototype.trim does. Each patch here names
# the files that parser finds, under the tool that writes or changes them.
@pytest.mark.parametrize(
    "patch,expected",
    [
        ("*** Begin Patch\n  *** Add File: evil.sh\n+x\n*** End Patch\n", [("Write", "evil.sh")]),
        ("*** Begin Patch\n\t*** Add File: evil.sh\n+x\n*** End Patch\n", [("Write", "evil.sh")]),
        ("*** Begin Patch\n\u00a0*** Add File: evil.sh\n+x\n*** End Patch\n", [("Write", "evil.sh")]),
        ("*** Begin Patch\n\u2003*** Delete File: a.txt\n*** End Patch\n", [("Edit", "a.txt")]),
        ("*** Begin Patch\r\n*** Add File: evil.sh\r\n+x\r\n*** End Patch\r\n", [("Write", "evil.sh")]),
        ("*** Begin Patch\n*** Add File:   evil.sh  \n+x\n*** End Patch\n", [("Write", "evil.sh")]),
        (
            "*** Begin Patch\n*** Add File: a.txt\n+x\n  *** Add File: evil.sh\n+y\n*** End Patch\n",
            [("Write", "a.txt"), ("Write", "evil.sh")],
        ),
        (
            "*** Begin Patch\n*** Update File: a.txt\n*** Move to: evil.sh\n@@\n-a\n+b\n*** End Patch\n",
            [("Edit", "a.txt"), ("Write", "evil.sh")],
        ),
        (
            "*** Begin Patch\r\n*** Update File: a.txt\r\n  *** Move to: evil.sh\u00a0\r\n@@\r\n-a\r\n+b\r\n*** End Patch\r\n",
            [("Edit", "a.txt"), ("Write", "evil.sh")],
        ),
        # Copilot rejects these markers, so judging their lines too only adds checks.
        (
            "*** Begin Patch\n*** Update File: a.txt\n@@\n-a\n+b\n   *** Add File: b.txt\n+x\n*** End Patch\n",
            [("Edit", "a.txt"), ("Write", "b.txt")],
        ),
        ("*** Begin Patch\n*** Add File:evil.sh\n+x\n*** End Patch\n", [("Write", "evil.sh")]),
        ("*** Begin Patch\n\ufeff*** Add File: secret.txt\n+x\n*** End Patch\n", [("Write", "secret.txt")]),
        (
            "*** Begin Patch\n*** Update File: a.txt\n\ufeff*** Move to: secret.txt\n@@\n-a\n+b\n*** End Patch\n",
            [("Edit", "a.txt"), ("Write", "secret.txt")],
        ),
        ("*** Begin Patch\n*** Add File: \ufeffsecret.txt\n+x\n*** End Patch\n", [("Write", "secret.txt")]),
        ("*** Begin Patch\n*** Add File: a.txt\x85\n+x\n*** End Patch\n", [("Write", "a.txt\x85")]),
        ("*** Begin Patch\n*** Add File: a.txt\x1f\n+x\n*** End Patch\n", [("Write", "a.txt\x1f")]),
        (
            "*** Begin Patch\n*** Add File: a.txt\n+x\r*** Add File: evil.sh\n+y\n*** End Patch\n",
            [("Write", "a.txt"), ("Write", "evil.sh")],
        ),
        (
            "*** Begin Patch\n*** Add File: ok.txt\n+a\n\ufeff*** Add File: evil.sh\n+b\n*** End Patch",
            [("Write", "ok.txt"), ("Write", "evil.sh")],
        ),
        (
            "*** Begin Patch\n*** Update File: a.txt\r*** Move to: evil.sh\n@@\n-x\n+y\n*** End Patch",
            [("Edit", "a.txt"), ("Write", "evil.sh")],
        ),
        ("*** Begin Patch\r*** Add File: evil.sh\r+echo pwned\r*** End Patch", [("Write", "evil.sh")]),
        ("*** Begin Patch\r*** Delete File: evil.sh\r*** End Patch", [("Edit", "evil.sh")]),
        ("*** Begin Patch\n*** Add File: evil\ufeff.sh\n+x\n*** End Patch", [("Write", "evil\ufeff.sh")]),
    ],
    ids=[
        "indented",
        "tab",
        "no-break-space",
        "em-space",
        "crlf",
        "padded-path",
        "indented-second-header",
        "move-target",
        "indented-crlf-move-target",
        "context-line-like-a-header",
        "no-space-after-colon",
        "byte-order-mark-before-header",
        "byte-order-mark-before-move-target",
        "byte-order-mark-before-path",
        "next-line-kept",
        "unit-separator-kept",
        "carriage-return-starts-a-line",
        "second-header-after-a-byte-order-mark",
        "move-target-after-a-carriage-return",
        "carriage-return-line-endings",
        "carriage-return-delete",
        "byte-order-mark-inside-a-path",
    ],
)
def test_patch_headers_are_read_as_copilots_own_parser_reads_them(patch: str, expected: list[tuple[str, str]]) -> None:
    assert judged_patch_paths(patch) == expected


@pytest.mark.parametrize(
    "patch",
    [
        "*** Begin Patch\n*** End Patch\n",
        "*** Begin Patch\n\u200b*** Add File: evil.sh\n+x\n*** End Patch\n",
    ],
    ids=["no-header", "zero-width-space"],
)
def test_a_patch_without_a_readable_header_is_judged_as_an_edit(patch: str) -> None:
    # The native name would fall outside every Edit and Write rule and threshold.
    assert policy_call("apply_patch", {"input": patch}) == ("Edit", {"input": patch})
    assert further_path_checks("apply_patch", {"input": patch}) == []


def test_multi_file_patch_lists_every_path_including_move_destinations() -> None:
    patch = (
        "*** Begin Patch\n*** Update File: src/a.py\n@@\n-x\n+y\n*** Move to: src/b.py\n"
        "*** Add File: sub/.watcher-ignore\n+skip\n*** End Patch\n"
    )
    assert policy_call("apply_patch", {"input": patch}) == (
        "Edit",
        {"file_path": "src/a.py", "file_paths": ["src/a.py", "src/b.py", "sub/.watcher-ignore"], "input": patch},
    )


def test_model_supplied_keys_never_replace_the_translated_ones() -> None:
    typed: dict[str, JsonValue] = {"shellId": "0", "input": "rm -rf build\n", "command": "git status"}
    assert policy_call("write_bash", typed) == ("Bash", {"command": "rm -rf build\n", "shellId": "0"})
    patch = "*** Begin Patch\n*** Add File: protected/new.txt\n+x\n*** Add File: b.txt\n+y\n*** End Patch\n"
    supplied = {"input": patch, "file_path": "harmless.txt", "file_paths": ["harmless.txt"]}
    assert policy_call("apply_patch", supplied) == (
        "Write",
        {"file_path": "protected/new.txt", "file_paths": ["protected/new.txt", "b.txt"], "input": patch},
    )
    single = "*** Begin Patch\n*** Add File: protected/new.txt\n+x\n*** End Patch\n"
    assert policy_call("apply_patch", {"input": single, "file_paths": ["harmless.txt"]}) == (
        "Write",
        {"file_path": "protected/new.txt", "input": single},
    )
    typed_powershell: dict[str, JsonValue] = {"shellId": "0", "input": "Remove-Item build", "command": "Get-Date"}
    assert policy_call("write_powershell", typed_powershell) == (
        "PowerShell",
        {"command": "Remove-Item build", "shellId": "0"},
    )
    editor: dict[str, JsonValue] = {
        "command": "create",
        "path": ".github/workflows/ci.yml",
        "file_path": "harmless.txt",
        "file_text": "x",
    }
    assert policy_call("str_replace_editor", editor) == (
        "Write",
        {"command": "create", "file_path": ".github/workflows/ci.yml", "file_text": "x"},
    )
    assert policy_call("view", {"path": "/etc/shadow", "file_path": "harmless.txt"}) == (
        "Read",
        {"file_path": "/etc/shadow"},
    )
    assert policy_call("lsp", {"operation": "hover", "file": "src/a.py", "filePath": "harmless.py"}) == (
        "LSP",
        {"operation": "hover", "filePath": "src/a.py"},
    )


@pytest.mark.parametrize(
    "name,arguments,expected",
    [
        ("local_shell", {"command": "rm -rf build"}, ("Bash", {"command": "rm -rf build"})),
        (
            "powershell",
            {"command": "Remove-Item -Recurse build", "description": "x", "mode": "sync", "shellId": "s"},
            (
                "PowerShell",
                {"command": "Remove-Item -Recurse build", "description": "x", "mode": "sync", "shellId": "s"},
            ),
        ),
        (
            "write_powershell",
            {"shellId": "0", "input": "Remove-Item build\n", "delay": 5},
            ("PowerShell", {"command": "Remove-Item build\n", "shellId": "0", "delay": 5}),
        ),
        ("write_powershell", {"shellId": "0", "input": ["not", "text"]}, None),
        ("write_powershell", {"shellId": "0"}, None),
        ("web_search", {"query": "pydantic release notes"}, ("WebSearch", {"query": "pydantic release notes"})),
        (
            "str_replace_editor",
            {"command": "view", "path": "a.txt", "view_range": [1, 5], "forceReadLargeFiles": True},
            ("Read", {"command": "view", "file_path": "a.txt", "view_range": [1, 5], "forceReadLargeFiles": True}),
        ),
        (
            "str_replace_editor",
            {"command": "create", "path": "a.txt", "file_text": "hi"},
            ("Write", {"command": "create", "file_path": "a.txt", "file_text": "hi"}),
        ),
        (
            "str_replace_editor",
            {"command": "str_replace", "path": "a.txt", "old_str": "a", "new_str": "b"},
            ("Edit", {"command": "str_replace", "file_path": "a.txt", "old_str": "a", "new_str": "b"}),
        ),
        (
            "str_replace_editor",
            {"command": "insert", "path": "a.txt", "insert_line": 2, "new_str": "b"},
            ("Edit", {"command": "insert", "file_path": "a.txt", "insert_line": 2, "new_str": "b"}),
        ),
        (
            "str_replace_editor",
            {"command": "create", "path": 7, "file_text": "hi"},
            ("Write", {"command": "create", "path": 7, "file_text": "hi"}),
        ),
        ("str_replace_editor", {"command": "undo_edit", "path": "a.txt"}, None),
        ("str_replace_editor", {"command": ["view"], "path": "a.txt"}, None),
        ("str_replace_editor", {"path": "a.txt"}, None),
        (
            "lsp",
            {"operation": "workspaceSymbol", "query": "Session", "language": "python"},
            ("LSP", {"operation": "workspaceSymbol", "query": "Session", "language": "python"}),
        ),
        ("lsp", {"operation": "hover", "file": 7}, ("LSP", {"operation": "hover", "file": 7})),
        ("lsp", {"operation": "rename", "file": "src/a.py", "line": 3, "character": 5, "newName": "b"}, None),
        ("lsp", {"operation": ["hover"], "file": "src/a.py"}, None),
        ("lsp", {"file": "src/a.py"}, None),
        ("list_bash", {}, None),
        ("sql", {"description": "x", "query": "DROP TABLE todos"}, None),
    ],
)
def test_policy_call_maps_shells_editors_search_and_reading_lsp(
    name: str, arguments: dict[str, JsonValue], expected: tuple[str, dict[str, JsonValue]] | None
) -> None:
    assert policy_call(name, arguments) == (expected or (name, arguments))


@pytest.mark.parametrize(
    "operation",
    [
        "goToDefinition",
        "findReferences",
        "hover",
        "documentSymbol",
        "workspaceSymbol",
        "goToImplementation",
        "incomingCalls",
        "outgoingCalls",
    ],
)
def test_every_reading_lsp_operation_becomes_lsp(operation: str) -> None:
    arguments: dict[str, JsonValue] = {"operation": operation, "file": "src/a.py", "line": 3, "character": 5}
    assert policy_call("lsp", arguments) == (
        "LSP",
        {"operation": operation, "line": 3, "character": 5, "filePath": "src/a.py"},
    )


def test_new_mappings_are_recorded_under_the_names_the_gate_submits() -> None:
    requests: list[JsonValue] = [
        {"toolCallId": "c1", "name": "local_shell", "arguments": {"command": "ls"}},
        {"toolCallId": "c2", "name": "str_replace_editor", "arguments": {"command": "view", "path": "a.txt"}},
        {"toolCallId": "c3", "name": "lsp", "arguments": {"operation": "rename", "file": "a.py", "newName": "b"}},
    ]
    messages = convert(
        [
            {"type": "assistant.message", "data": {"content": "", "toolRequests": requests}},
            *(
                {
                    "type": "tool.execution_complete",
                    "data": {"toolCallId": call_id, "success": True, "result": {"content": "ok"}},
                }
                for call_id in ("c1", "c2", "c3")
            ),
        ]
    )
    assert messages[0]["tool_calls"] == [
        {"id": "c1", "function": "Bash", "arguments": {"command": "ls"}},
        {"id": "c2", "function": "Read", "arguments": {"command": "view", "file_path": "a.txt"}},
        {"id": "c3", "function": "lsp", "arguments": {"operation": "rename", "file": "a.py", "newName": "b"}},
    ]
    assert [(message["tool_call_id"], message["function"]) for message in messages[1:]] == [
        ("c1", "Bash"),
        ("c2", "Read"),
        ("c3", "lsp"),
    ]


@pytest.mark.parametrize(
    "first,expected",
    [("Add File: protected/new.txt\n+secret", "Write"), ("Update File: protected/new.txt\n@@\n-a\n+b", "Edit")],
)
def test_a_multi_file_patch_is_named_after_its_first_paths_own_operation(first: str, expected: str) -> None:
    patch = f"*** Begin Patch\n*** {first}\n*** Add File: public.txt\n+hi\n*** End Patch\n"
    assert policy_call("apply_patch", {"input": patch}) == (
        expected,
        {"file_path": "protected/new.txt", "file_paths": ["protected/new.txt", "public.txt"], "input": patch},
    )


@pytest.mark.parametrize(
    "request_fields",
    [
        {"arguments": "PRIVATE raw input", "type": "function"},
        {"arguments": "PRIVATE raw input"},
        {"arguments": {"input": "PRIVATE raw input"}, "type": "custom"},
    ],
)
def test_a_tool_input_that_does_not_match_its_tool_type_is_skipped(request_fields: dict[str, JsonValue]) -> None:
    request: dict[str, JsonValue] = {"toolCallId": "call", "name": "apply_patch", **request_fields}
    assert convert([{"type": "assistant.message", "data": {"content": "", "toolRequests": [request]}}]) == [SKIPPED]


@pytest.mark.parametrize(
    "block",
    [
        {"type": "thinking", "thinking": "PRIVATE reasoning", "signature": "signature"},
        {"type": "reasoning", "summary": [{"type": "summary_text", "text": "PRIVATE reasoning"}]},
        {"type": "reasoning", "content": [{"type": "reasoning_text", "text": "PRIVATE reasoning"}]},
    ],
)
def test_reasoning_only_in_provider_blocks_is_refused(block: dict[str, JsonValue]) -> None:
    data: dict[str, JsonValue] = {
        "content": "Answer",
        "reasoningText": " ",
        "reasoningBlocks": {"provider": "native", "blocks": [block]},
    }
    with pytest.raises(UnsupportedTranscriptError, match="^Unsupported Copilot content$"):
        convert([{"type": "assistant.message", "data": data}])


def test_blank_reasoning_text_adds_no_reasoning_block() -> None:
    assert convert([{"type": "assistant.message", "data": {"content": "Answer", "reasoningText": "  \n"}}]) == [
        {"role": "assistant", "content": "Answer"}
    ]


@pytest.mark.parametrize(
    "data",
    [
        {"content": "Answer", "reasoningText": ["PRIVATE reasoning"]},
        {"content": "Answer", "encryptedContent": {"PRIVATE": "reasoning"}},
        {"content": "Answer", "reasoningBlocks": {"blocks": ["PRIVATE reasoning"]}},
    ],
)
def test_malformed_reasoning_fields_are_skipped(data: dict[str, JsonValue]) -> None:
    assert convert([{"type": "assistant.message", "data": data}]) == [SKIPPED]


@pytest.mark.parametrize("kind", ["user.message", "assistant.message", "assistant.turn_start"])
def test_an_event_with_a_blank_subagent_identity_is_skipped(kind: str) -> None:
    session = convert_session([{"type": kind, "agentId": "", "data": {"content": "Subagent text"}}])
    assert session.messages == [SKIPPED] and session.subagents == []


def test_provider_tool_content_is_not_mistaken_for_an_empty_provider_marker() -> None:
    with pytest.raises(UnsupportedTranscriptError, match="^Unsupported Copilot content$"):
        convert(
            [
                {
                    "type": "assistant.message",
                    "data": {
                        "content": "Visible answer",
                        "serverTools": {"provider": "openai-responses", "toolCalls": [{"id": "hosted-call"}]},
                    },
                }
            ]
        )


@pytest.mark.parametrize(
    "data",
    [
        {"content": "PRIVATE native content", "transformedContent": None},
        {"content": ["PRIVATE native content"]},
        {"content": "PRIVATE native content", "parentToolCallId": 123},
    ],
)
def test_malformed_native_fields_are_skipped_without_their_content(data: dict[str, JsonValue]) -> None:
    assert convert([{"type": "user.message", "data": data}]) == [SKIPPED]


def test_system_block_mismatch_is_not_recorded_as_complete() -> None:
    with pytest.raises(UnsupportedTranscriptError, match="System content blocks do not match"):
        convert(
            [
                {
                    "type": "system.message",
                    "data": {"role": "system", "content": "First", "contentBlocks": [{"content": "Different"}]},
                }
            ]
        )


def test_current_native_metadata_preserves_supported_content() -> None:
    assert convert(
        [
            {"type": "user.message", "data": {"content": "Task", "parentAgentTaskId": "root-task"}},
            {
                "type": "system.message",
                "data": {
                    "role": "system",
                    "content": "First\n\nSecond",
                    "contentBlocks": [{"content": "First", "isStatic": True}, {"content": "Second"}],
                },
            },
            {"type": "assistant.turn_start", "data": {"turnId": "0"}},
            {
                "type": "assistant.message",
                "data": {
                    "content": "Working",
                    "serverTools": {"provider": "openai-responses"},
                    "toolRequests": [
                        {
                            "toolCallId": "native-call",
                            "name": "bash",
                            "arguments": {"command": "false", "options": {"quiet": False}, "timeout": 0},
                            "type": "function",
                            "toolTitle": "Run a command",
                        }
                    ],
                },
            },
            {
                "type": "tool.execution_complete",
                "data": {"toolCallId": "native-call", "success": False, "error": {"message": "Exited with code 1"}},
            },
            {"type": "assistant.message", "data": {"content": "The command failed."}},
            {"type": "assistant.turn_end", "data": {"turnId": "0"}},
        ]
    ) == [
        {"role": "system", "content": "First\n\nSecond"},
        {"role": "user", "content": "Task"},
        {
            "role": "assistant",
            "content": "Working",
            "tool_calls": [
                {
                    "id": "native-call",
                    "function": "Bash",
                    "arguments": {"command": "false", "options": {"quiet": False}, "timeout": 0},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "native-call",
            "function": "Bash",
            "content": "Exited with code 1",
            "error": {"type": "unknown", "message": "Exited with code 1"},
        },
        {"role": "assistant", "content": "The command failed."},
    ]


def test_a_call_that_never_returned_stays_unanswered() -> None:
    assert convert(
        [
            {
                "type": "assistant.message",
                "data": {"content": "", "toolRequests": [{"toolCallId": "pending", "name": "bash"}]},
            },
            {"type": "assistant.message", "data": {"content": "Finished"}},
        ]
    ) == [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "pending", "function": "Bash", "arguments": {}}]},
        {"role": "assistant", "content": "Finished"},
    ]


def test_recording_warning_does_not_prevent_later_replay() -> None:
    assert convert(
        [
            {"type": "user.message", "data": {"content": "Read the status."}},
            {"type": "assistant.message", "data": {"content": "The status is ready."}},
            {
                "type": "session.warning",
                "data": {"warningType": "hook", "message": "Watcher recording was not confirmed."},
            },
        ]
    ) == [
        {"role": "user", "content": "Read the status."},
        {"role": "assistant", "content": "The status is ready."},
    ]


def test_nonfinite_tool_arguments_are_skipped() -> None:
    assert convert(
        [
            {
                "type": "assistant.message",
                "data": {
                    "content": "",
                    "toolRequests": [{"toolCallId": "pending", "name": "bash", "arguments": {"timeout": float("nan")}}],
                },
            }
        ]
    ) == [SKIPPED]


def test_transcript_cannot_impersonate_the_callbacks_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = str(uuid4())
    path = tmp_path / "session-state" / session_id / "events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"type": "session.start", "data": {"sessionId": str(uuid4())}}))
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    with pytest.raises(TranscriptError, match="session does not match the callback"):
        read_transcript({"sessionId": session_id, "transcriptPath": str(path)})


def test_malformed_callback_error_does_not_echo_values() -> None:
    with pytest.raises(TranscriptError, match="^Malformed Copilot turn-completion callback$"):
        read_transcript({"sessionId": "PRIVATE bad session", "transcriptPath": "/PRIVATE/path"})
