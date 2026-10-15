from enum import StrEnum


class SessionAggregatesResponseSeverityThreshold(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    LOW = "low"
    MEDIUM = "medium"

    def __str__(self) -> str:
        return str(self.value)
