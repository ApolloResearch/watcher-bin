from enum import Enum


class AppliedDecision(str, Enum):
    ALLOW = "allow"
    DEFERRED = "deferred"
    DENY = "deny"
    ESCALATE = "escalate"
    NOT_EVALUATED = "not_evaluated"

    def __str__(self) -> str:
        return str(self.value)
