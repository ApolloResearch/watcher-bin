from enum import Enum


class PreToolUseHookRequestMode(str, Enum):
    FULL = "full"
    TRIAGE_ONLY = "triage_only"

    def __str__(self) -> str:
        return str(self.value)
