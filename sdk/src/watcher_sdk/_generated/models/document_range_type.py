from enum import StrEnum


class DocumentRangeType(StrEnum):
    BLOCK = "block"
    CHAR = "char"
    PAGE = "page"

    def __str__(self) -> str:
        return str(self.value)
