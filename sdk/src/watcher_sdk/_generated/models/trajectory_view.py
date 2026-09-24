from enum import Enum


class TrajectoryView(str, Enum):
    EXTENDED = "extended"
    TRUNCATED = "truncated"

    def __str__(self) -> str:
        return str(self.value)
