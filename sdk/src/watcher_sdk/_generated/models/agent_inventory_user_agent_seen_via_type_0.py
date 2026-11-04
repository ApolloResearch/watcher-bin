from enum import StrEnum


class AgentInventoryUserAgentSeenViaType0(StrEnum):
    BOTH = "both"
    CLIENT = "client"
    GATEWAY = "gateway"

    def __str__(self) -> str:
        return str(self.value)
