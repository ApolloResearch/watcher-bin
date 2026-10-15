from enum import StrEnum


class ContentVideoFormat(StrEnum):
    MOV = "mov"
    MP4 = "mp4"
    MPEG = "mpeg"

    def __str__(self) -> str:
        return str(self.value)
