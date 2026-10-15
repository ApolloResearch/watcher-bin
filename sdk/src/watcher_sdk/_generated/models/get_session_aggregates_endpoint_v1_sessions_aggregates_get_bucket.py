from enum import StrEnum


class GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket(StrEnum):
    DAY = "day"
    WEEK = "week"

    def __str__(self) -> str:
        return str(self.value)
