from enum import StrEnum


class AvailableToolCallListItemCoverageState(StrEnum):
    BYPASSED = "bypassed"
    DECIDED = "decided"
    GRADING_ERROR = "grading_error"
    NOT_EVALUATED = "not_evaluated"

    def __str__(self) -> str:
        return str(self.value)
