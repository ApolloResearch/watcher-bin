from enum import StrEnum


class RelatedSessionSummaryDeepReviewStatusType0(StrEnum):
    ERROR = "error"
    NOT_REVIEWED = "not_reviewed"
    PENDING = "pending"
    REVIEWED = "reviewed"
    STALE = "stale"

    def __str__(self) -> str:
        return str(self.value)
