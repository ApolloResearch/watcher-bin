from enum import StrEnum


class ToolCallType(StrEnum):
    CUSTOM = "custom"
    FUNCTION = "function"

    def __str__(self) -> str:
        return str(self.value)
