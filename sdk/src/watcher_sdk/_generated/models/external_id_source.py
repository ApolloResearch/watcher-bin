from enum import StrEnum


class ExternalIdSource(StrEnum):
    APERTURE = "aperture"
    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    GITHUB_COPILOT_CLI = "github_copilot_cli"
    OTHER = "other"

    def __str__(self) -> str:
        return str(self.value)
