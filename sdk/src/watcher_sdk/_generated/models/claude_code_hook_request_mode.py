from enum import Enum


class ClaudeCodeHookRequestMode(str, Enum):
    FULL = "full"
    TRIAGE_ONLY = "triage_only"

    def __str__(self) -> str:
        return str(self.value)
