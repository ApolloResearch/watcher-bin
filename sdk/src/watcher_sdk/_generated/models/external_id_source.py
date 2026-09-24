from enum import Enum


class ExternalIdSource(str, Enum):
    APERTURE = "aperture"
    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    OTHER = "other"

    def __str__(self) -> str:
        return str(self.value)
