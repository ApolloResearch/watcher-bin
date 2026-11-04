from enum import StrEnum


class ListAgentInventoryInstallationsEndpointV1AgentInventoryInstallationsGetCoverageType0(
    StrEnum
):
    GAP = "gap"
    MONITORED = "monitored"

    def __str__(self) -> str:
        return str(self.value)
