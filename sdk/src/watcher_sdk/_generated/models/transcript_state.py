from enum import StrEnum


class TranscriptState(StrEnum):
    NOT_RECORDED = "not_recorded"
    RECORDED = "recorded"
    SCRUBBED = "scrubbed"

    def __str__(self) -> str:
        return str(self.value)
