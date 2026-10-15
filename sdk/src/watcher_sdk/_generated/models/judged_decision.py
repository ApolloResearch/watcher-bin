from enum import StrEnum


class JudgedDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"

    def __str__(self) -> str:
        return str(self.value)
