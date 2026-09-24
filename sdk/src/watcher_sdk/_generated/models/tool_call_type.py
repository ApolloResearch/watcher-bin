from enum import Enum


class ToolCallType(str, Enum):
    CUSTOM = "custom"
    FUNCTION = "function"

    def __str__(self) -> str:
        return str(self.value)
