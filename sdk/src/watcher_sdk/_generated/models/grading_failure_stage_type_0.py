from enum import Enum


class GradingFailureStageType0(str, Enum):
    GATEWAY = "gateway"
    TRIAGE = "triage"

    def __str__(self) -> str:
        return str(self.value)
