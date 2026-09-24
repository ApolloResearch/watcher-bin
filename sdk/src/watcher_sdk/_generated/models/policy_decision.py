from enum import Enum


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"
    NOT_EVALUATED = "not_evaluated"

    def __str__(self) -> str:
        return str(self.value)
