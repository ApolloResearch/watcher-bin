from enum import StrEnum


class EnforcementMode(StrEnum):
    ENFORCE = "enforce"
    OBSERVE = "observe"
    PAUSED = "paused"

    def __str__(self) -> str:
        return str(self.value)
