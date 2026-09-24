from enum import Enum


class JudgedDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"

    def __str__(self) -> str:
        return str(self.value)
