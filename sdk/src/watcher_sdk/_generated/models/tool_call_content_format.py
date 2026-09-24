from enum import Enum


class ToolCallContentFormat(str, Enum):
    MARKDOWN = "markdown"
    TEXT = "text"

    def __str__(self) -> str:
        return str(self.value)
