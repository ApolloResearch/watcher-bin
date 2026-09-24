from enum import Enum


class GetSessionAggregatesEndpointV1SessionsAggregatesGetBucket(str, Enum):
    DAY = "day"
    WEEK = "week"

    def __str__(self) -> str:
        return str(self.value)
