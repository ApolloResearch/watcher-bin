from enum import StrEnum


class SessionSearchFiltersGradingStatusesType0Item(StrEnum):
    CLEAN = "clean"
    ERROR = "error"
    FLAGGED = "flagged"
    UNGRADED = "ungraded"

    def __str__(self) -> str:
        return str(self.value)
