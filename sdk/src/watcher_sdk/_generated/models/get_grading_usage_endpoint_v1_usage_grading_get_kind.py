from enum import Enum


class GetGradingUsageEndpointV1UsageGradingGetKind(str, Enum):
    ALL = "all"
    GATEWAY = "gateway"
    TRAILING = "trailing"
    TRIAGE = "triage"

    def __str__(self) -> str:
        return str(self.value)
