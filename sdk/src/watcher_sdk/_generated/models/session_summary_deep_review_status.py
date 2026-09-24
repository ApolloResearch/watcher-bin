from enum import Enum


class SessionSummaryDeepReviewStatus(str, Enum):
    ERROR = "error"
    NOT_REVIEWED = "not_reviewed"
    PENDING = "pending"
    REVIEWED = "reviewed"
    STALE = "stale"

    def __str__(self) -> str:
        return str(self.value)
