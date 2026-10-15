from enum import StrEnum


class GetGradingUsageEndpointV1UsageGradingGetBucket(StrEnum):
    DAY = "day"
    WEEK = "week"

    def __str__(self) -> str:
        return str(self.value)
