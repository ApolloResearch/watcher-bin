from enum import StrEnum


class AgentInventoryInstallationRemovalResponseResult(StrEnum):
    ALREADY_REMOVED = "already_removed"
    REMOVED = "removed"

    def __str__(self) -> str:
        return str(self.value)
