from enum import StrEnum


class AgentInventoryActivityEventKind(StrEnum):
    AGENT_TURNED_OFF = "agent_turned_off"
    AGENT_TURNED_ON = "agent_turned_on"
    CLIENT_UPDATED = "client_updated"
    HEALTH_COMPLETE = "health_complete"
    HEALTH_INCOMPLETE = "health_incomplete"
    HEALTH_MISSING = "health_missing"
    HEALTH_RESUMED = "health_resumed"
    HOOKS_MISSING = "hooks_missing"
    HOOKS_NOT_RUNNING = "hooks_not_running"
    HOOKS_RESTORED = "hooks_restored"
    INVENTORY_RESUMED = "inventory_resumed"
    INVENTORY_STOPPED = "inventory_stopped"
    MODE_CHANGED = "mode_changed"
    SELF_CHECK_CLEARED = "self_check_cleared"
    SELF_CHECK_FLAGGED = "self_check_flagged"
    SETUP_OUTDATED = "setup_outdated"
    SETUP_UPDATED = "setup_updated"
    SNOOZE_ENDED = "snooze_ended"
    SNOOZE_STARTED = "snooze_started"
    UPLOADS_BACKING_UP = "uploads_backing_up"
    UPLOADS_CAUGHT_UP = "uploads_caught_up"
    WENT_OFFLINE = "went_offline"

    def __str__(self) -> str:
        return str(self.value)
