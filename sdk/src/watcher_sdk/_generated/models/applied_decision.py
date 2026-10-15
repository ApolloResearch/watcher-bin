from enum import StrEnum


class AppliedDecision(StrEnum):
    ALLOW = "allow"
    DEFERRED = "deferred"
    DENY = "deny"
    ESCALATE = "escalate"
    NOT_EVALUATED = "not_evaluated"

    def __str__(self) -> str:
        return str(self.value)
