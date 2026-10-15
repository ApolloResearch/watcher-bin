from enum import StrEnum


class ContentImageDetail(StrEnum):
    AUTO = "auto"
    HIGH = "high"
    LOW = "low"
    ORIGINAL = "original"

    def __str__(self) -> str:
        return str(self.value)
