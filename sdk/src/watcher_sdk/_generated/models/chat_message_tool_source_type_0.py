from enum import Enum


class ChatMessageToolSourceType0(str, Enum):
    GENERATE = "generate"
    INPUT = "input"
    OPERATOR = "operator"

    def __str__(self) -> str:
        return str(self.value)
