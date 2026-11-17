from enum import StrEnum


class AvailableSessionDetailResponseTranscriptState(StrEnum):
    NOT_RECORDED = "not_recorded"
    RECORDED = "recorded"

    def __str__(self) -> str:
        return str(self.value)
