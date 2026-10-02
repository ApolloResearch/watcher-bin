"""Text-only truncated replies remain deliverable without an executable proposal."""

import pytest
from camel.models.stub_model import StubModel
from camel.types import ModelType
from openai.types.chat import ChatCompletion
from watcher_camel.native import MonitoredModel


class TextModel(StubModel):
    """Return a native partial-text response without contacting a provider."""

    def __init__(self, reason):
        super().__init__(ModelType.STUB)
        self.reason = reason

    async def _arun(self, messages, response_format=None, tools=None):
        return ChatCompletion.model_validate(
            {
                "id": "partial",
                "object": "chat.completion",
                "model": "fixture",
                "created": 0,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": self.reason,
                        "message": {"role": "assistant", "content": "Partial text"},
                    }
                ],
            }
        )


class NoExecutableProposal:
    """Reject a mistaken attempt to grade text as a tool call."""

    async def before(self, *args):
        raise AssertionError("A text reply has no executable proposal")


@pytest.mark.parametrize("reason", ["length", "content_filter"])
@pytest.mark.asyncio
async def test_partial_text_remains_deliverable(reason):
    response = await MonitoredModel(TextModel(reason), NoExecutableProposal()).arun(
        [{"role": "user", "content": "Tell me something"}]
    )
    assert isinstance(response, ChatCompletion)
    assert response.choices[0].message.content == "Partial text"
    assert response.choices[0].finish_reason == reason
