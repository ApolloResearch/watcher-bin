from enum import StrEnum


class ManagedSettingsSourceErrorKindType0(StrEnum):
    FILE_MISSING = "file_missing"
    FILE_UNREADABLE = "file_unreadable"
    INVALID_CONTENT = "invalid_content"

    def __str__(self) -> str:
        return str(self.value)
