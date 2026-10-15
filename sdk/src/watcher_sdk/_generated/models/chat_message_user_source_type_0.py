from enum import StrEnum


class ChatMessageUserSourceType0(StrEnum):
    GENERATE = "generate"
    INPUT = "input"
    OPERATOR = "operator"

    def __str__(self) -> str:
        return str(self.value)
