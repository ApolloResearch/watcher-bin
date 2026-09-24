from enum import Enum


class OrgSettingsUpdateSettingsDistributionType0(str, Enum):
    MDM = "mdm"
    WATCHER = "watcher"

    def __str__(self) -> str:
        return str(self.value)
