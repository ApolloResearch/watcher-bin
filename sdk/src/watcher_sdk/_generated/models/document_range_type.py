from enum import Enum


class DocumentRangeType(str, Enum):
    BLOCK = "block"
    CHAR = "char"
    PAGE = "page"

    def __str__(self) -> str:
        return str(self.value)
