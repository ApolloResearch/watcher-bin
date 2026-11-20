from enum import StrEnum


class ToolCallRecordResultStatus(StrEnum):
    IGNORED_EXISTING = "ignored_existing"
    LINKED = "linked"
    STORED = "stored"

    def __str__(self) -> str:
        return str(self.value)
