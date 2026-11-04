from enum import StrEnum


class AperturePreRequestResponseAction(StrEnum):
    ALLOW = "allow"
    MODIFY = "modify"

    def __str__(self) -> str:
        return str(self.value)
