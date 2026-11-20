from enum import StrEnum


class AgentInventoryActivityEventGapCauseType0(StrEnum):
    ASLEEP = "asleep"
    MACHINE_RESTARTED = "machine_restarted"
    NOT_DELIVERED = "not_delivered"
    WATCHER_NOT_RUNNING = "watcher_not_running"

    def __str__(self) -> str:
        return str(self.value)
