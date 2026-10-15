from enum import StrEnum


class ActivatedMonitorsResponseDistribution(StrEnum):
    MDM = "mdm"
    WATCHER = "watcher"

    def __str__(self) -> str:
        return str(self.value)
