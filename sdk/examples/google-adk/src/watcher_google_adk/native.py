"""Preserve resolved ADK instructions alongside native events for Watcher.

Create one ConversationHistory per session, register its before-model callback,
and share it with the before-tool callback and final transcript submission.
"""

from copy import deepcopy

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.sessions.session import Session
from google.genai import types


class ConversationHistory:
    """Retain resolved text instructions that ADK does not persist in session events.

    Register before_model_callback last among callbacks that modify the model
    request. Reuse this object for one session with its full, unmodified event
    history. Instruction changes are retained at model-request boundaries,
    preserving earlier instructions for historical tool decisions. This object
    is process-local; persist its output if it must survive a restart.
    """

    def __init__(self):
        self._session_id: str | None = None
        self._event_ids: list[str] = []
        self._messages: list[types.Content] = []
        self._instruction = ""
        self._captured = False

    def before_model_callback(self, callback_context: CallbackContext, llm_request: LlmRequest) -> None:
        """Capture ADK's resolved system text without changing the model request.

        The callback returns None so ADK still calls its configured model. Only
        text system instructions are supported, consistent with this example's
        transcript converter; unsupported content raises before model execution.
        """
        self._check_session(callback_context.session)
        instruction = llm_request.config.system_instruction
        if instruction is not None and not isinstance(instruction, str):
            raise ValueError("Only text system instructions are supported")
        instruction = instruction or ""
        if self._captured:
            self.messages(callback_context.session)
        if instruction != self._instruction:
            self._messages.append(types.Content(role="system", parts=[types.Part(text=instruction)]))
            self._instruction = instruction
        self._captured = True
        self.messages(callback_context.session)

    def _check_session(self, session: Session) -> None:
        """Reject reuse or truncated events before changing the retained transcript."""
        if self._session_id is not None and self._session_id != session.id:
            raise ValueError("Create one ConversationHistory per ADK session")
        if self._event_ids != [event.id for event in session.events[: len(self._event_ids)]]:
            raise ValueError("The complete, unchanged ADK event history is required")
        self._session_id = session.id

    def messages(self, session: Session) -> list[types.Content]:
        """Copy instructions and all native events for a pending call or final record.

        The before-model callback must have run first. Calling this after a turn
        retains its tool results and answer; callers can mutate the returned copy
        without changing the retained context used for later decisions.
        """
        if not self._captured:
            raise ValueError("Register ConversationHistory.before_model_callback before monitoring tools")
        self._check_session(session)
        for event in session.events[len(self._event_ids) :]:
            self._event_ids.append(event.id)
            if event.content is not None:
                self._messages.append(event.content.model_copy(deep=True))
        return deepcopy(self._messages)


def before_tool_callback(monitor, history: ConversationHistory):
    """Gate each native call using the same captured instructions as final recording.

    Register history.before_model_callback on the agent as well. Returning None
    preserves normal execution after Watcher allows, defers, or the application
    confirms human approval; a rejected decision propagates before execution.
    """

    async def before(tool, args, tool_context):
        await monitor.before(history.messages(tool_context.session), tool_context.function_call_id, tool.name, args)
        return None

    return before
