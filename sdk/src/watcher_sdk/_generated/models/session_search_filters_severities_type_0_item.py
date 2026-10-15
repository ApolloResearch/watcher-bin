from enum import StrEnum


class SessionSearchFiltersSeveritiesType0Item(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    LOW = "low"
    MEDIUM = "medium"

    def __str__(self) -> str:
        return str(self.value)
