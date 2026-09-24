from enum import Enum


class UserFilterMode(str, Enum):
    EXCLUDE = "exclude"
    INCLUDE = "include"

    def __str__(self) -> str:
        return str(self.value)
