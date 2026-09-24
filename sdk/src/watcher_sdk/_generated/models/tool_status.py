from enum import Enum


class ToolStatus(str, Enum):
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    PENDING = "pending"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return str(self.value)
