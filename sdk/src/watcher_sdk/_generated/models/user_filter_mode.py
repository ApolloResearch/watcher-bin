from enum import StrEnum


class UserFilterMode(StrEnum):
    EXCLUDE = "exclude"
    INCLUDE = "include"

    def __str__(self) -> str:
        return str(self.value)
