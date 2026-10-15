from enum import StrEnum


class GradingFailureStageType0(StrEnum):
    GATEWAY = "gateway"
    TRIAGE = "triage"

    def __str__(self) -> str:
        return str(self.value)
