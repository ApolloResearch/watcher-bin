from enum import StrEnum


class SessionContentAccessRequestStatus(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"
    PENDING = "pending"
    REVOKED = "revoked"

    def __str__(self) -> str:
        return str(self.value)
