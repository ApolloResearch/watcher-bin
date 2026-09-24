from enum import Enum


class ChatMessageUserSourceType0(str, Enum):
    GENERATE = "generate"
    INPUT = "input"
    OPERATOR = "operator"

    def __str__(self) -> str:
        return str(self.value)
