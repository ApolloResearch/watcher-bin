from enum import StrEnum


class MonitorInfoRole(StrEnum):
    DEEP_REVIEW = "deep_review"
    GATEWAY = "gateway"
    SUMMARIZE = "summarize"
    TRIAGE = "triage"

    def __str__(self) -> str:
        return str(self.value)
