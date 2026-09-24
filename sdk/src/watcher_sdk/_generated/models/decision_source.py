from enum import Enum


class DecisionSource(str, Enum):
    BYPASS = "bypass"
    GRADING_ERROR = "grading_error"
    NOT_EVALUATED = "not_evaluated"
    POLICY_GATEWAY = "policy_gateway"
    RULE = "rule"
    THRESHOLD = "threshold"
    TRIAGE = "triage"

    def __str__(self) -> str:
        return str(self.value)
