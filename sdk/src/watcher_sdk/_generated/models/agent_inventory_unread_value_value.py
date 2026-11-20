from enum import StrEnum


class AgentInventoryUnreadValueValue(StrEnum):
    AGENTS = "agents"
    ENFORCEMENT_MODE = "enforcement_mode"
    HOOKS = "hooks"
    SELF_CHECK = "self_check"
    SETUP = "setup"
    SNOOZE = "snooze"
    UPLOADS = "uploads"

    def __str__(self) -> str:
        return str(self.value)
