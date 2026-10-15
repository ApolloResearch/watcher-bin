from enum import StrEnum


class SessionContentAccessRequestView(StrEnum):
    ACTIVE = "active"
    HISTORICAL = "historical"
    PENDING = "pending"

    def __str__(self) -> str:
        return str(self.value)
