from enum import StrEnum


class AgentInventoryHealthConditionCode(StrEnum):
    AGENT_LOCKED_OFF = "agent_locked_off"
    AGENT_OFF = "agent_off"
    APPROVAL_BYPASS = "approval_bypass"
    ASLEEP = "asleep"
    DECISIONS_LOST = "decisions_lost"
    HEALTH_INCOMPLETE = "health_incomplete"
    HEALTH_STALE = "health_stale"
    HOOKS_MISSING = "hooks_missing"
    HOOKS_TURNED_OFF_IN_AGENT = "hooks_turned_off_in_agent"
    HOOKS_UNTRUSTED = "hooks_untrusted"
    INVENTORY_STALE = "inventory_stale"
    NOT_REPORTING = "not_reporting"
    NO_HEALTH = "no_health"
    NO_INVENTORY = "no_inventory"
    OBSERVE = "observe"
    OFFLINE = "offline"
    OFFLINE_LONG = "offline_long"
    PAUSED = "paused"
    REPORTS_MISSING = "reports_missing"
    SELF_CHECK = "self_check"
    SESSIONS_MISSING = "sessions_missing"
    SETUP_OUTDATED = "setup_outdated"
    SHUT_DOWN = "shut_down"
    SIGNED_OUT = "signed_out"
    SNOOZED = "snoozed"
    UNMONITORED_AGENTS = "unmonitored_agents"
    UPLOADS = "uploads"
    WATCHER_STOPPED = "watcher_stopped"

    def __str__(self) -> str:
        return str(self.value)
