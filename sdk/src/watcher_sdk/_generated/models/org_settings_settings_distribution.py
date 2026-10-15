from enum import StrEnum


class OrgSettingsSettingsDistribution(StrEnum):
    MDM = "mdm"
    WATCHER = "watcher"

    def __str__(self) -> str:
        return str(self.value)
