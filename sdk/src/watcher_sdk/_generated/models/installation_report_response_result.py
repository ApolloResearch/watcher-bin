from enum import StrEnum


class InstallationReportResponseResult(StrEnum):
    DUPLICATE = "duplicate"
    STORED = "stored"

    def __str__(self) -> str:
        return str(self.value)
