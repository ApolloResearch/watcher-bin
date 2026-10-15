from enum import StrEnum


class TrajectoryView(StrEnum):
    EXTENDED = "extended"
    TRUNCATED = "truncated"

    def __str__(self) -> str:
        return str(self.value)
