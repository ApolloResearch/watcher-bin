from enum import StrEnum


class AperturePreResponseResponseAction(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    MODIFY = "modify"

    def __str__(self) -> str:
        return str(self.value)
