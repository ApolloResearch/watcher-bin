from enum import StrEnum


class AgentInventoryPresenceState(StrEnum):
    OFFLINE = "offline"
    ONLINE = "online"
    REPORTS_MISSING = "reports_missing"

    def __str__(self) -> str:
        return str(self.value)
