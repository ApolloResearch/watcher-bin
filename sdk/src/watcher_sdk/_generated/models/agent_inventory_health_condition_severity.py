from enum import StrEnum


class AgentInventoryHealthConditionSeverity(StrEnum):
    NOTE = "note"
    PROBLEM = "problem"
    WARNING = "warning"

    def __str__(self) -> str:
        return str(self.value)
