from enum import StrEnum


class AgentInventoryHealthConditionReasonsItem(StrEnum):
    CALL_RECORDS = "call_records"
    GAVE_UP = "gave_up"
    WAITING = "waiting"

    def __str__(self) -> str:
        return str(self.value)
