"""Watcher's notice texts: the system notice's placement and the bounds on client-visible notices."""

import json

import pytest
from watcher_agent_router.exchange import Denial
from watcher_agent_router.notices import SYSTEM_NOTICE, denial_notice, stop_notice, with_system_notice

USER = {"role": "user", "content": "hi"}
NOTICE = {"role": "system", "content": SYSTEM_NOTICE}


@pytest.mark.parametrize(
    "messages,expected",
    [
        ([USER], [NOTICE, USER]),
        (
            [{"role": "system", "content": "a"}, {"role": "developer", "content": "b"}, USER],
            [{"role": "system", "content": "a"}, {"role": "developer", "content": "b"}, NOTICE, USER],
        ),
        ([USER, {"role": "system", "content": "late"}], [NOTICE, USER, {"role": "system", "content": "late"}]),
    ],
)
def test_system_notice_follows_the_leading_instructions(messages, expected):
    request = {"model": "m", "messages": messages, "tool_choice": "auto"}
    noticed = with_system_notice(request)
    assert noticed["messages"] == expected and noticed["tool_choice"] == "auto"
    assert request["messages"] == messages, "the client's request is not modified"


@pytest.mark.parametrize(
    "leading",
    [
        [NOTICE],
        [{"role": "system", "content": [{"type": "text", "text": "managed: " + SYSTEM_NOTICE}]}],
    ],
)
def test_system_notice_is_added_only_once(leading):
    request = {"model": "m", "messages": [*leading, USER]}
    assert with_system_notice(request) is request
    assert with_system_notice(with_system_notice({"model": "m", "messages": [USER]}))["messages"].count(NOTICE) == 1


def test_long_arguments_and_reasons_are_shortened_in_the_notice():
    big = Denial(
        tool_use_id="a", tool_name="t", tool_input={"text": "é" * 20_000}, reason="r" * 9000, is_escalation=False
    )
    notice = denial_notice([big], [])
    assert len(notice) < 9000 and "… (arguments shortened)" in notice and "r" * 4096 + "." in notice


def test_notice_counts_calls_past_its_size_limit():
    denials = [
        Denial(tool_use_id=f"id-{index}", tool_name="t", tool_input={"x": "y" * 3000}, reason="no", is_escalation=False)
        for index in range(40)
    ]
    notice = denial_notice(denials, [("s", {"i": index}) for index in range(150)])
    assert len(notice.encode()) <= 64 * 1024
    assert notice.endswith("more refused calls and 150 more withheld calls did not run.")


def test_withheld_sibling_lines_count_toward_the_size_limit():
    denial = Denial(tool_use_id="a", tool_name="rm", tool_input={}, reason="no", is_escalation=False)
    notice = denial_notice([denial], [("s", {"x": "y" * 4000}) for _ in range(100)])
    assert len(notice.encode()) <= 64 * 1024
    assert notice.endswith(": 0 more refused calls and 85 more withheld calls did not run.")
    wide = denial_notice([denial], [("s", {"x": "😀" * 4000}) for _ in range(100)])
    shown = wide.count("did not run because Watcher refused another call")
    assert len(wide.encode()) <= 64 * 1024
    assert wide.endswith(f": 0 more refused calls and {100 - shown} more withheld calls did not run.")


def test_each_refused_call_gets_one_attributed_line():
    denials = [
        Denial(tool_use_id="a", tool_name="rm", tool_input={"p": 1}, reason="Destructive", is_escalation=False),
        Denial(
            tool_use_id="b",
            tool_name="deploy",
            tool_input={},
            reason="Review",
            is_escalation=True,
            user_can_approve=True,
        ),
    ]
    lines = denial_notice(denials, [("ls", {})]).split("\n\n")
    assert lines == [
        'WATCHER NOTICE (added by Watcher, not written by the assistant): Watcher blocked `rm {"p": 1}`. '
        "Reason: Destructive. The call did not run.",
        "WATCHER ESCALATION (added by Watcher, not written by the assistant): `deploy {}` needs the user's decision "
        "before it can run. Reason: Review. The call did not run.",
        "WATCHER NOTICE (added by Watcher, not written by the assistant): `ls {}` did not run because Watcher "
        "refused another call in the same response.",
    ]


def test_stop_notice_offers_approval_only_when_every_escalation_allows_it():
    graded = Denial(
        tool_use_id="a", tool_name="t", tool_input={}, reason="r", is_escalation=True, user_can_approve=True
    )
    held = graded.model_copy(update={"user_can_approve": False})
    denied = graded.model_copy(update={"is_escalation": False, "user_can_approve": False})
    assert "Reply A to allow" in stop_notice([graded, denied])
    assert "Reply A to skip it" in stop_notice([graded, held])
    assert "three proposals in a row" in stop_notice([denied])
    assert json.dumps(SYSTEM_NOTICE).count("work around") == 0
