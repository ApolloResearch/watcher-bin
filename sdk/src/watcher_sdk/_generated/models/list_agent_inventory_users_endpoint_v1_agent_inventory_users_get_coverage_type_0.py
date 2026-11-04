from enum import StrEnum


class ListAgentInventoryUsersEndpointV1AgentInventoryUsersGetCoverageType0(StrEnum):
    GAP = "gap"
    MONITORED = "monitored"

    def __str__(self) -> str:
        return str(self.value)
