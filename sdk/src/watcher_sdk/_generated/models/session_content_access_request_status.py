from enum import Enum


class SessionContentAccessRequestStatus(str, Enum):
    APPROVED = "approved"
    DENIED = "denied"
    PENDING = "pending"
    REVOKED = "revoked"

    def __str__(self) -> str:
        return str(self.value)
