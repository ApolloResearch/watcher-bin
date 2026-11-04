"""The fixed system notice reaches every request once, after the client's own instructions."""

from typing import Any

import pytest
from test_callback import USER, _proxy_data
from watcher_litellm.callback import WatcherCallback
from watcher_litellm.system_notice import SYSTEM_NOTICE, system_notice_fields

_BLOCK = {"type": "text", "text": SYSTEM_NOTICE}
_DEVELOPER = {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": SYSTEM_NOTICE}]}


@pytest.mark.parametrize(
    ("system", "expected"),
    [
        (None, [_BLOCK]),
        ("", [_BLOCK]),
        ("Be brief.", [{"type": "text", "text": "Be brief."}, _BLOCK]),
        (
            [{"type": "text", "text": "Be brief.", "cache_control": {"type": "ephemeral"}}],
            [{"type": "text", "text": "Be brief.", "cache_control": {"type": "ephemeral"}}, _BLOCK],
        ),
    ],
)
def test_messages_notice_is_the_last_system_block_without_a_cache_breakpoint(system: Any, expected: Any) -> None:
    body = {"messages": [{"role": "user", "content": "hi"}]} | ({"system": system} if system is not None else {})

    assert system_notice_fields("messages", body) == {"system": expected}


def test_chat_notice_follows_the_leading_instruction_messages() -> None:
    messages = [
        {"role": "developer", "content": "Rules."},
        {"role": "system", "content": "More rules."},
        {"role": "user", "content": "hi"},
        {"role": "system", "content": "A later system message stays where it is."},
    ]

    fields = system_notice_fields("chat_completions", {"messages": messages})

    assert fields == {"messages": [*messages[:2], {"role": "system", "content": SYSTEM_NOTICE}, *messages[2:]]}
    assert len(messages) == 4


def test_responses_notice_follows_leading_developer_items_and_wraps_string_input() -> None:
    items = [
        {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "Codex prompt"}]},
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]},
    ]

    assert system_notice_fields("responses", {"input": items}) == {"input": [items[0], _DEVELOPER, items[1]]}
    assert system_notice_fields("responses", {"input": "hi", "instructions": "Be brief."}) == {
        "input": [_DEVELOPER, {"role": "user", "content": "hi"}]
    }


@pytest.mark.parametrize(
    ("api", "body"),
    [
        ("messages", {"system": [{"type": "text", "text": f"Managed settings: {SYSTEM_NOTICE}"}]}),
        ("chat_completions", {"messages": [{"role": "system", "content": SYSTEM_NOTICE}, {"role": "user"}]}),
        ("responses", {"input": [_DEVELOPER, {"role": "user", "content": "hi"}]}),
        ("messages", {"system": 7}),
        ("chat_completions", {}),
        ("responses", {"input": {"role": "user"}}),
    ],
    ids=["messages-present", "chat-present", "responses-present", "messages-shape", "chat-missing", "responses-shape"],
)
def test_requests_that_carry_the_notice_or_cannot_take_it_are_unchanged(api: Any, body: dict[str, Any]) -> None:
    assert system_notice_fields(api, body) == {}


def test_a_later_user_message_quoting_the_notice_does_not_count_as_present() -> None:
    messages = [{"role": "user", "content": SYSTEM_NOTICE}]

    assert system_notice_fields("chat_completions", {"messages": messages}) == {
        "messages": [{"role": "system", "content": SYSTEM_NOTICE}, *messages]
    }


async def test_pre_call_adds_the_notice_to_the_provider_arguments_and_the_request_snapshot_once() -> None:
    body = {"model": "m", "input": "hi"}
    data: dict[str, Any] = {**_proxy_data("/v1/responses", body, {"x-watcher-session-id": "conversation"}), **body}
    callback = WatcherCallback()

    assert await callback.async_pre_call_hook(USER, None, data, "responses") is data
    expected = [_DEVELOPER, {"role": "user", "content": "hi"}]
    assert data["input"] == expected
    assert data["proxy_server_request"]["body"] == {"model": "m", "input": expected}
    assert body == {"model": "m", "input": "hi"}

    await callback.async_pre_call_hook(USER, None, data, "responses")
    assert data["input"] == expected
