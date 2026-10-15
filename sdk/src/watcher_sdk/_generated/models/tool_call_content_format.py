from enum import StrEnum


class ToolCallContentFormat(StrEnum):
    MARKDOWN = "markdown"
    TEXT = "text"

    def __str__(self) -> str:
        return str(self.value)
