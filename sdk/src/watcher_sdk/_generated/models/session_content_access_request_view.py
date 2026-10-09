from enum import Enum


class SessionContentAccessRequestView(str, Enum):
    ACTIVE = "active"
    HISTORICAL = "historical"
    PENDING = "pending"

    def __str__(self) -> str:
        return str(self.value)
