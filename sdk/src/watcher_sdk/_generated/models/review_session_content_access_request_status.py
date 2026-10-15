from enum import StrEnum


class ReviewSessionContentAccessRequestStatus(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"

    def __str__(self) -> str:
        return str(self.value)
