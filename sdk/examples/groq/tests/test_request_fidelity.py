"""Reject partial executable output without attempting transcript conversion."""

import pytest
from watcher_groq.raw import inventory, validate_request

from tests.support import CALLS, reply


@pytest.mark.parametrize("finish", ["length", "content_filter", None])
def test_partial_generation_cannot_be_released(finish):
    body = reply(calls=CALLS)
    body["choices"][0]["finish_reason"] = finish
    with pytest.raises(ValueError):
        inventory(body, "chat_completions")


def test_duplicate_native_ids_rejected():
    with pytest.raises(ValueError):
        inventory(reply(calls=[*CALLS, CALLS[0]]), "chat_completions")


@pytest.mark.parametrize(
    "option", [{"stream": True}, {"n": 2}, {"previous_response_id": "hidden"}, {"tools": [{"type": "web_search"}]}]
)
def test_unsupported_request_rejected_before_generation(option):
    with pytest.raises(ValueError):
        validate_request(option, "chat_completions")
