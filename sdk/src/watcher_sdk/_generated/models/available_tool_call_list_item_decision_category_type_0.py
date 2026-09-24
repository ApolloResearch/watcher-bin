from enum import Enum


class AvailableToolCallListItemDecisionCategoryType0(str, Enum):
    AUTO_DENIED = "auto_denied"
    CLEARED = "cleared"
    HUMAN_ALLOWED = "human_allowed"
    HUMAN_DENIED = "human_denied"
    WOULD_DENIED = "would_denied"
    WOULD_ESCALATED = "would_escalated"

    def __str__(self) -> str:
        return str(self.value)
