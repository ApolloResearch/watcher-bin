from enum import Enum


class ReviewSessionContentAccessRequestStatus(str, Enum):
    APPROVED = "approved"
    DENIED = "denied"

    def __str__(self) -> str:
        return str(self.value)
