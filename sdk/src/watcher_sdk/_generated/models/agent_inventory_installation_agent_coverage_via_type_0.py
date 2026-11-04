from enum import StrEnum


class AgentInventoryInstallationAgentCoverageViaType0(StrEnum):
    BOTH = "both"
    CLIENT = "client"
    GATEWAY = "gateway"

    def __str__(self) -> str:
        return str(self.value)
