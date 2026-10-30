from enum import StrEnum


class IngestResultStatus(StrEnum):
    ALREADY_STORED = "already_stored"
    PARTIALLY_STORED = "partially_stored"
    STORED = "stored"

    def __str__(self) -> str:
        return str(self.value)
