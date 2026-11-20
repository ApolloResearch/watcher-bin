from enum import StrEnum


class AgentInventoryActivityEventSignedOffWithType0(StrEnum):
    GOING_TO_SLEEP = "going_to_sleep"
    SIGNING_OUT = "signing_out"
    STOPPED_BY_USER = "stopped_by_user"
    STOPPING = "stopping"
    WOKE = "woke"

    def __str__(self) -> str:
        return str(self.value)
