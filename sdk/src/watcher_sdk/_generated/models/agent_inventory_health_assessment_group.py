from enum import StrEnum


class AgentInventoryHealthAssessmentGroup(StrEnum):
    HEALTHY = "healthy"
    NEEDS_ATTENTION = "needs_attention"
    OFFLINE = "offline"

    def __str__(self) -> str:
        return str(self.value)
