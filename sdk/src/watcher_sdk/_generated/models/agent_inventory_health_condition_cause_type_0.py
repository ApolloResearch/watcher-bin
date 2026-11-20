from enum import StrEnum


class AgentInventoryHealthConditionCauseType0(StrEnum):
    CLIENT_TOO_OLD = "client_too_old"
    HEALTH_READ_FAILING = "health_read_failing"
    WATCHER_MAY_HAVE_STOPPED = "watcher_may_have_stopped"
    WATCHER_RUNNING = "watcher_running"

    def __str__(self) -> str:
        return str(self.value)
