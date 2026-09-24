from enum import Enum


class EnforcementMode(str, Enum):
    ENFORCE = "enforce"
    OBSERVE = "observe"
    PAUSED = "paused"

    def __str__(self) -> str:
        return str(self.value)
