from enum import StrEnum


class GradingFailureCode(StrEnum):
    ALLOWANCE_EXHAUSTED = "allowance_exhausted"
    AT_CAPACITY = "at_capacity"
    GRADER_FAILED = "grader_failed"
    NO_RESULT = "no_result"
    TIMEOUT = "timeout"

    def __str__(self) -> str:
        return str(self.value)
