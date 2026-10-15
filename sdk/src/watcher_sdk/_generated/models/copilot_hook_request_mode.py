from enum import StrEnum


class CopilotHookRequestMode(StrEnum):
    FULL = "full"
    TRIAGE_ONLY = "triage_only"

    def __str__(self) -> str:
        return str(self.value)
