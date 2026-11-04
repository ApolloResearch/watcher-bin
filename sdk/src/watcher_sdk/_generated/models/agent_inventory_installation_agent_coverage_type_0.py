from enum import StrEnum


class AgentInventoryInstallationAgentCoverageType0(StrEnum):
    GAP = "gap"
    MONITORED = "monitored"
    NOT_SUPPORTED = "not_supported"

    def __str__(self) -> str:
        return str(self.value)
