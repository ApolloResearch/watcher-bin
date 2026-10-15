from enum import StrEnum


class OrgSettingsSlackAlertDetail(StrEnum):
    FINDINGS_ONLY = "findings_only"
    FULL = "full"

    def __str__(self) -> str:
        return str(self.value)
