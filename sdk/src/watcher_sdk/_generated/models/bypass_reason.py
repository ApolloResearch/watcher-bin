from enum import StrEnum


class BypassReason(StrEnum):
    SNOOZE = "snooze"
    WATCHER_IGNORE = "watcher_ignore"

    def __str__(self) -> str:
        return str(self.value)
