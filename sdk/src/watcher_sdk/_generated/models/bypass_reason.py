from enum import Enum


class BypassReason(str, Enum):
    SNOOZE = "snooze"
    WATCHER_IGNORE = "watcher_ignore"

    def __str__(self) -> str:
        return str(self.value)
