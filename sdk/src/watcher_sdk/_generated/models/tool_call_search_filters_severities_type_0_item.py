from enum import StrEnum


class ToolCallSearchFiltersSeveritiesType0Item(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    LOW = "low"
    MEDIUM = "medium"
    NOT_SCORED = "not_scored"

    def __str__(self) -> str:
        return str(self.value)
