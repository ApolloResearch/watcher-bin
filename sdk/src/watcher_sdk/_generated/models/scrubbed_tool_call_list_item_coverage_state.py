from enum import Enum


class ScrubbedToolCallListItemCoverageState(str, Enum):
    BYPASSED = "bypassed"
    DECIDED = "decided"
    GRADING_ERROR = "grading_error"
    NOT_EVALUATED = "not_evaluated"

    def __str__(self) -> str:
        return str(self.value)
