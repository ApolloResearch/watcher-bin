"""A native partial-text reply does not become an executable proposal."""

import pytest
from haystack.dataclasses import ChatMessage
from watcher_haystack.native import MonitoredGenerator


class TextGenerator:
    """Return native text with the provider finish reason retained in metadata."""

    async def run_async(self, messages, tools=None):
        return {"replies": [ChatMessage.from_assistant("Partial text", meta={"finish_reason": "length"})]}


class NoExecutableProposal:
    """Reject a mistaken attempt to grade text as a tool call."""

    async def before(self, *args):
        raise AssertionError("A text reply has no executable proposal")


@pytest.mark.asyncio
async def test_partial_text_remains_deliverable():
    result = await MonitoredGenerator(TextGenerator(), NoExecutableProposal()).run_async(
        [ChatMessage.from_user("Tell me something")]
    )
    assert result["replies"][0].text == "Partial text"
    assert result["replies"][0].meta["finish_reason"] == "length"
