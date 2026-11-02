from enum import StrEnum


class GatewayAction(StrEnum):
    BLOCKED = "blocked"
    CANCELLED = "cancelled"

    def __str__(self) -> str:
        return str(self.value)
