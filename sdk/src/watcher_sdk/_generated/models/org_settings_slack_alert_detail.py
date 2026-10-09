from enum import Enum


class OrgSettingsSlackAlertDetail(str, Enum):
    FINDINGS_ONLY = "findings_only"
    FULL = "full"

    def __str__(self) -> str:
        return str(self.value)
