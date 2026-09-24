from enum import Enum


class ContentImageDetail(str, Enum):
    AUTO = "auto"
    HIGH = "high"
    LOW = "low"
    ORIGINAL = "original"

    def __str__(self) -> str:
        return str(self.value)
