from enum import StrEnum


class GetGradingUsageEndpointV1UsageGradingGetKind(StrEnum):
    ALL = "all"
    GATEWAY = "gateway"
    TRAILING = "trailing"
    TRIAGE = "triage"

    def __str__(self) -> str:
        return str(self.value)
