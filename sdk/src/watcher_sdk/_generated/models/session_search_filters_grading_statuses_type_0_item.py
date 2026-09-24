from enum import Enum


class SessionSearchFiltersGradingStatusesType0Item(str, Enum):
    CLEAN = "clean"
    ERROR = "error"
    FLAGGED = "flagged"
    UNGRADED = "ungraded"

    def __str__(self) -> str:
        return str(self.value)
