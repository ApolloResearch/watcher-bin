from enum import Enum


class MonitorInfoRole(str, Enum):
    DEEP_REVIEW = "deep_review"
    GATEWAY = "gateway"
    SUMMARIZE = "summarize"
    TRIAGE = "triage"

    def __str__(self) -> str:
        return str(self.value)
