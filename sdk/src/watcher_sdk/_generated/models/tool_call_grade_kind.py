from enum import StrEnum


class ToolCallGradeKind(StrEnum):
    POLICY_GATEWAY = "policy_gateway"
    POLICY_TRIAGE = "policy_triage"

    def __str__(self) -> str:
        return str(self.value)
