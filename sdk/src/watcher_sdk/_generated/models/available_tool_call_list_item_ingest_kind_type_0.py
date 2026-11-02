from enum import StrEnum


class AvailableToolCallListItemIngestKindType0(StrEnum):
    CLIENT = "client"
    GATEWAY = "gateway"
    OTHER = "other"
    SDK = "sdk"

    def __str__(self) -> str:
        return str(self.value)
