"""Conversation identity and delivery provenance shared by integrations and Watcher.

Conversation identity selects a session; capture source describes an accepted
delivery. Neither establishes ownership or grants access. Keeping these values
separate lets integrations share a native conversation without sharing a name.
"""

import json
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ConversationNamespace = Literal["other", "claude_code", "codex", "opencode"]
CaptureKind = Literal["client", "gateway", "sdk", "other"]


def validate_conversation_id(value: object, *, max_length: int) -> str:
    """Validate an opaque ID without echoing untrusted values in errors."""
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > max_length
        or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)
    ):
        raise ValueError("invalid_conversation_identity")
    return value


class ConversationIdentity(BaseModel):
    """One authoritative session-matching identity, without additional aliases.

    Native Codex IDs and Claude root IDs are normalized UUIDs. Claude children use
    the transcript uploader's ``subagent:[root_uuid, agent_id]`` encoding. Custom
    IDs belong to ``other`` and keep any integration namespace supplied by their
    adapter. The larger wire limit accommodates JSON-escaped child identifiers;
    individual native identifiers remain bounded at 1,024 characters.
    """

    model_config = ConfigDict(extra="forbid")

    namespace: ConversationNamespace
    id: Annotated[str, Field(min_length=1, max_length=8192)]

    @model_validator(mode="after")
    def _canonical_identity(self) -> Self:
        """Canonicalize native IDs so equivalent spellings cannot fork a session."""
        if self.namespace == "claude_code" and self.id.startswith("subagent:"):
            try:
                parts = json.loads(self.id.removeprefix("subagent:"))
                if not isinstance(parts, list) or len(parts) != 2:
                    raise ValueError
                root = str(UUID(validate_conversation_id(parts[0], max_length=1024)))
                child = validate_conversation_id(parts[1], max_length=1024)
            except ValueError:
                raise ValueError("invalid_native_conversation_identity") from None
            self.id = "subagent:" + json.dumps([root, child], separators=(",", ":"))
        elif self.namespace in {"claude_code", "codex"}:
            try:
                self.id = str(UUID(self.id))
            except ValueError:
                raise ValueError("invalid_native_conversation_identity") from None
        else:
            # Custom adapters can prefix a 1,024-character client ID.
            validate_conversation_id(self.id, max_length=2048 if self.namespace == "other" else 1024)
        return self


class CaptureSource(BaseModel, frozen=True):
    """An integration that delivered a conversation, independent of its identity.

    ``name`` is an optional stable integration identifier, not a hostname, user,
    model or credential. An unnamed source preserves a known delivery category
    when historical data cannot establish the particular integration.
    """

    model_config = ConfigDict(extra="forbid")

    type: CaptureKind
    name: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")] | None = None
