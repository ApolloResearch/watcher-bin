from enum import StrEnum


class GetSessionAggregatesEndpointV1SessionsAggregatesGetSeverityThreshold(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    LOW = "low"
    MEDIUM = "medium"

    def __str__(self) -> str:
        return str(self.value)
