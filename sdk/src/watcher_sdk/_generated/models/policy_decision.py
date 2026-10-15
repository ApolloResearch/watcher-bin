from enum import StrEnum


class PolicyDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"
    NOT_EVALUATED = "not_evaluated"

    def __str__(self) -> str:
        return str(self.value)
