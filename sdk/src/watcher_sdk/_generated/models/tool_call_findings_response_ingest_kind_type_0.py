from enum import StrEnum


class ToolCallFindingsResponseIngestKindType0(StrEnum):
    CLIENT = "client"
    GATEWAY = "gateway"
    OTHER = "other"
    SDK = "sdk"

    def __str__(self) -> str:
        return str(self.value)
