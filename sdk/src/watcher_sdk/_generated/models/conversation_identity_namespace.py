from enum import StrEnum


class ConversationIdentityNamespace(StrEnum):
    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    OPENCODE = "opencode"
    OTHER = "other"

    def __str__(self) -> str:
        return str(self.value)
