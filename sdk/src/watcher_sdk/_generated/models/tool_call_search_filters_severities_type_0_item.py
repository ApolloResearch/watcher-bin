from enum import Enum


class ToolCallSearchFiltersSeveritiesType0Item(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    LOW = "low"
    MEDIUM = "medium"
    NOT_SCORED = "not_scored"

    def __str__(self) -> str:
        return str(self.value)
