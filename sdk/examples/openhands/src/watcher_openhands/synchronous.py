"""Block OpenHands actions through its public event callback and conversation state.

EnforcementRecorder replaces the observation Recorder for LocalConversation.run.
Bind it before sending/running a prompt. It preserves native events for the same
independent completion observation used by integration.py.
"""

import asyncio
import json
from collections.abc import Callable

from openhands.sdk.conversation import LocalConversation
from openhands.sdk.event import ActionEvent

from watcher_openhands.enforcement import apply_policy
from watcher_openhands.integration import Recorder, convert
from watcher_sdk import AsyncWatcherClient


class EnforcementRecorder(Recorder):
    """Await approval in synchronous callbacks, then mark disallowed actions blocked.

    OpenHands partitions blocked actions before executing its tool batch. Binding
    is required because recording an event alone cannot stop execution. Use the
    synchronous conversation.run method, in a thread when called from async code.
    The synchronous callback itself holds dispatch while grading. An allow never
    changes blocked state, preserving refusals added before or during the wait.
    """

    def __init__(self, client_factory: Callable[[], AsyncWatcherClient]):
        super().__init__()
        self.client_factory = client_factory
        self.conversation: LocalConversation | None = None

    def bind(self, conversation: LocalConversation) -> None:
        """Bind once, immediately after creating the conversation and before any run."""
        if self.conversation is not None:
            raise ValueError("Recorder is already bound")
        self.conversation = conversation

    def __call__(self, event):
        conversation = self.conversation
        if conversation is None:
            raise RuntimeError("Bind the enforcement recorder before running")
        if not isinstance(event, ActionEvent) or event.action is None:
            super().__call__(event)
            return
        state = conversation.state

        async def approve():
            call = {
                "id": event.tool_call_id,
                "function": event.tool_call.name,
                "arguments": json.loads(event.tool_call.arguments),
            }
            async with self.client_factory() as client:
                await apply_policy(client, str(conversation.id), convert(self.messages), call)

        try:
            super().__call__(event)
            asyncio.run(approve())
        except Exception:
            with state:
                if event.id not in state.blocked_actions:
                    state.block_action(event.id, "Watcher did not confirm approval")
