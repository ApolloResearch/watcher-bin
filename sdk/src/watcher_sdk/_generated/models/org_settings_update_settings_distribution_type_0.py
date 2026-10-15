from enum import StrEnum


class OrgSettingsUpdateSettingsDistributionType0(StrEnum):
    MDM = "mdm"
    WATCHER = "watcher"

    def __str__(self) -> str:
        return str(self.value)
