from enum import StrEnum


class SessionSearchParamsSortBy(StrEnum):
    DECISIONS = "decisions"
    ENDED_AT = "ended_at"
    GRADING_STATUS = "grading_status"
    MAX_SEVERITY = "max_severity"
    MESSAGE_COUNT = "message_count"
    STARTED_AT = "started_at"

    def __str__(self) -> str:
        return str(self.value)
