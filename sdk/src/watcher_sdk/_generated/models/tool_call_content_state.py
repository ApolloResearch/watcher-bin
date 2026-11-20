from enum import StrEnum


class ToolCallContentState(StrEnum):
    LINKED = "linked"
    METADATA_ONLY = "metadata_only"

    def __str__(self) -> str:
        return str(self.value)
